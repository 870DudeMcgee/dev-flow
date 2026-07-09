from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from devflow.legacy.control_room.paths import relative_path
from devflow.legacy.control_room.persistence import atomic_write_text
from devflow.legacy.control_room.training_dataset import (
    DEFAULT_MAX_EXAMPLES,
    _collect_examples,
    _redaction_report,
)


DEFAULT_MLX_RUN_ID = "mlx-local-trainability-20260701"

Runner = Callable[..., subprocess.CompletedProcess[str]]


def prepare_mlx_training_data(
    root: Path,
    *,
    run_id: str = DEFAULT_MLX_RUN_ID,
    max_examples: int = DEFAULT_MAX_EXAMPLES,
) -> dict[str, Any]:
    repo_root = root.resolve()
    run_dir = _run_dir(repo_root, run_id)
    data_dir = run_dir / "data"
    train_path = data_dir / "train.jsonl"

    examples = _collect_examples(repo_root)
    if max_examples >= 0:
        examples = examples[:max_examples]

    lines = [json.dumps({"text": _mlx_text(row)}, sort_keys=True) for row in examples]
    train_body = "".join(f"{line}\n" for line in lines)
    redaction = _redaction_report(train_body)
    atomic_write_text(train_path, train_body)

    return {
        "run_id": run_id,
        "example_count": len(examples),
        "redaction": redaction,
        "output_paths": {
            "data_dir": relative_path(repo_root, data_dir),
            "train_jsonl": relative_path(repo_root, train_path),
        },
    }


def model_slug(model: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-") or "model"
    digest = hashlib.sha1(model.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"


def build_mlx_load_smoke_argv(model: str) -> list[str]:
    return [
        "uvx",
        "--python",
        "3.12",
        "--from",
        "mlx-lm[train]",
        "mlx_lm.generate",
        "--model",
        model,
        "--prompt",
        "Reply with exactly: mlx load ok",
        "--max-tokens",
        "8",
    ]


def build_mlx_lora_smoke_argv(
    model: str,
    *,
    run_dir: Path,
    iters: int,
) -> list[str]:
    adapter_path = _adapter_path(run_dir, model)
    return [
        "uvx",
        "--python",
        "3.12",
        "--from",
        "mlx-lm[train]",
        "mlx_lm.lora",
        "--model",
        model,
        "--train",
        "--data",
        str(run_dir / "data"),
        "--iters",
        str(iters),
        "--batch-size",
        "1",
        "--num-layers",
        "2",
        "--max-seq-length",
        "512",
        "--grad-checkpoint",
        "--steps-per-report",
        "1",
        "--save-every",
        "1",
        "--adapter-path",
        str(adapter_path),
    ]


def build_mlx_lora_reload_smoke_argv(
    model: str,
    *,
    run_dir: Path,
) -> list[str]:
    return [
        "uvx",
        "--python",
        "3.12",
        "--from",
        "mlx-lm[train]",
        "mlx_lm.generate",
        "--model",
        model,
        "--prompt",
        "Reply with exactly: mlx lora reload ok",
        "--max-tokens",
        "8",
        "--adapter-path",
        str(_adapter_path(run_dir, model)),
    ]


def run_load_smoke(
    root: Path,
    *,
    model: str,
    run_id: str = DEFAULT_MLX_RUN_ID,
    dry_run: bool = True,
    runner: Runner = subprocess.run,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    repo_root = root.resolve()
    run_dir = _run_dir(repo_root, run_id)
    argv = build_mlx_load_smoke_argv(model)
    return _run_smoke(
        repo_root,
        run_dir=run_dir,
        model=model,
        smoke_name="load-smoke",
        argv=argv,
        dry_run=dry_run,
        runner=runner,
        timeout_seconds=timeout_seconds,
    )


def run_lora_smoke(
    root: Path,
    *,
    model: str,
    iters: int = 1,
    run_id: str = DEFAULT_MLX_RUN_ID,
    dry_run: bool = True,
    runner: Runner = subprocess.run,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    repo_root = root.resolve()
    run_dir = _run_dir(repo_root, run_id)
    adapter_path = _adapter_path(run_dir, model)
    argv = build_mlx_lora_smoke_argv(model, run_dir=run_dir, iters=iters)
    payload = _run_smoke(
        repo_root,
        run_dir=run_dir,
        model=model,
        smoke_name="lora-smoke",
        argv=argv,
        dry_run=dry_run,
        runner=runner,
        adapter_path=adapter_path,
        timeout_seconds=timeout_seconds,
    )
    if dry_run or payload["status"] != "success":
        return payload
    model_dir = run_dir / "models" / model_slug(model)
    evidence_path = model_dir / "lora-smoke.json"

    if not _has_adapter_artifacts(adapter_path):
        payload["status"] = "failed"
        payload["failure_reason"] = (
            "missing expected adapter files "
            f"adapters.safetensors and adapter_config.json in {relative_path(root, adapter_path)}"
        )
        atomic_write_text(evidence_path, _payload_json(payload))
        return payload

    reload_payload = _run_smoke(
        repo_root,
        run_dir=run_dir,
        model=model,
        smoke_name="lora-smoke-reload",
        argv=build_mlx_lora_reload_smoke_argv(model, run_dir=run_dir),
        dry_run=False,
        runner=runner,
        adapter_path=adapter_path,
        timeout_seconds=timeout_seconds,
    )

    payload["commands"] = [payload["command"], reload_payload["command"]]
    payload["reload_status"] = reload_payload["status"]
    payload["reload_exit_code"] = reload_payload.get("exit_code")
    payload["reload_failure_reason"] = reload_payload.get("failure_reason")

    if reload_payload["status"] != "success":
        payload["status"] = "failed"
        payload["exit_code"] = reload_payload["exit_code"]
        payload["failure_reason"] = (
            reload_payload.get("failure_reason")
            if reload_payload.get("failure_reason")
            else payload.get("failure_reason")
        )
    atomic_write_text(evidence_path, _payload_json(payload))
    return payload


def _run_dir(root: Path, run_id: str) -> Path:
    return root / ".devflow" / "training" / run_id


def _adapter_path(run_dir: Path, model: str) -> Path:
    return run_dir / "models" / model_slug(model) / "adapters"


def _has_adapter_artifacts(adapter_path: Path) -> bool:
    if not adapter_path.exists():
        return False
    if not adapter_path.is_dir():
        return False
    return (adapter_path / "adapters.safetensors").is_file() and (adapter_path / "adapter_config.json").is_file()


def _payload_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _mlx_text(row: dict[str, Any]) -> str:
    messages = row.get("messages") if isinstance(row, dict) else None
    if not isinstance(messages, list):
        return ""
    chunks: list[str] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role and content:
            chunks.append(f"{role}: {content}")
    return "\n\n".join(chunks)


def _run_smoke(
    root: Path,
    *,
    run_dir: Path,
    model: str,
    smoke_name: str,
    argv: list[str],
    dry_run: bool,
    runner: Runner,
    adapter_path: Path | None = None,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    model_dir = run_dir / "models" / model_slug(model)
    artifact_name = f"{smoke_name}.dry-run" if dry_run else smoke_name
    log_path = model_dir / f"{artifact_name}.log"
    evidence_path = model_dir / f"{artifact_name}.json"

    payload: dict[str, Any] = {
        "run_id": run_dir.name,
        "model": model,
        "model_slug": model_slug(model),
        "smoke_name": smoke_name,
        "dry_run": dry_run,
        "command": argv,
        "log_path": relative_path(root, log_path),
        "evidence_path": relative_path(root, evidence_path),
    }
    if adapter_path is not None:
        payload["adapter_path"] = relative_path(root, adapter_path)

    if dry_run:
        payload["status"] = "dry_run"
        payload["duration_seconds"] = 0.0
        atomic_write_text(log_path, "dry-run\n" + " ".join(argv) + "\n")
        atomic_write_text(evidence_path, _payload_json(payload))
        return payload

    started_at = time.perf_counter()
    try:
        completed = runner(
            argv,
            capture_output=True,
            text=True,
            check=False,
            **({"timeout": timeout_seconds} if timeout_seconds is not None else {}),
        )
    except subprocess.TimeoutExpired as exc:
        duration_seconds = round(time.perf_counter() - started_at, 6)
        payload.update(
            duration_seconds=duration_seconds,
            exit_code=None,
            status="failed",
            failure_reason=f"timed out after {timeout_seconds} seconds",
        )
        atomic_write_text(log_path, _process_text(exc.stdout) + _process_text(exc.stderr))
        atomic_write_text(evidence_path, _payload_json(payload))
        return payload
    duration_seconds = round(time.perf_counter() - started_at, 6)
    log_body = (completed.stdout or "") + (completed.stderr or "")
    atomic_write_text(log_path, log_body)

    payload["duration_seconds"] = duration_seconds
    payload["exit_code"] = completed.returncode
    payload["status"] = "success" if completed.returncode == 0 else "failed"
    if completed.returncode != 0:
        payload["failure_reason"] = _failure_reason(completed)

    atomic_write_text(evidence_path, _payload_json(payload))
    return payload


def _failure_reason(completed: subprocess.CompletedProcess[str]) -> str:
    for value in (completed.stderr, completed.stdout):
        text = (value or "").strip()
        if text:
            return text
    return f"command exited with code {completed.returncode}"


def _process_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
