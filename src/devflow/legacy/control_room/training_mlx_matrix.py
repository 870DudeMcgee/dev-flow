from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from devflow.legacy.control_room.paths import relative_path
from devflow.legacy.control_room.persistence import atomic_write_text
from devflow.legacy.control_room.training_mlx_runner import model_slug


DEFAULT_MODEL_SPECS: tuple[dict[str, Any], ...] = (
    {
        "model": "lmstudio-community/Qwen3.6-27B-MLX-4bit",
        "runtime_family": "mlx_lm",
        "training_surface": "mlx_lm_text_trainable",
        "claim_basis": "default_matrix_seed",
        "input_modalities": ["text"],
    },
    {
        "model": "lmstudio-community/Qwen3.6-27B-MLX-8bit",
        "runtime_family": "mlx_lm",
        "training_surface": "mlx_lm_text_trainable",
        "claim_basis": "default_matrix_seed",
        "input_modalities": ["text"],
    },
    {
        "model": "mlx-community/Qwen3.6-27B-OptiQ-4bit",
        "runtime_family": "mlx_lm",
        "training_surface": "mlx_lm_text_trainable",
        "claim_basis": "default_matrix_seed",
        "input_modalities": ["text"],
    },
    {
        "model": "mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit",
        "runtime_family": "mlx_lm",
        "training_surface": "mlx_lm_text_trainable",
        "claim_basis": "default_matrix_seed",
        "input_modalities": ["text"],
    },
    {
        "model": "mlx-community/gemma-4-e4b-it-OptiQ-4bit",
        "runtime_family": "mlx_lm",
        "training_surface": "mlx_lm_text_trainable",
        "claim_basis": "default_text_only_gemma4",
        "input_modalities": ["text"],
        "notes": "Gemma 4 text-only MLX-LM smoke; multimodal VLM rows must declare non-text modalities",
    },
    {
        "model": "mlx-community/gemma-4-12B-it-OptiQ-4bit",
        "runtime_family": "mlx_lm",
        "training_surface": "mlx_lm_text_trainable",
        "claim_basis": "default_text_only_gemma4",
        "input_modalities": ["text"],
        "notes": "Gemma 4 text-only MLX-LM smoke; multimodal VLM rows must declare non-text modalities",
    },
)


def write_trainability_matrix(
    root: Path,
    run_id: str,
    models: list[str | dict[str, Any]] | None = None,
    manifest_path: str | Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    repo_root = root.resolve()
    run_dir = repo_root / ".devflow" / "training" / run_id
    matrix_path = run_dir / "trainability-matrix.json"
    result_path = run_dir / "result.md"

    if manifest_path is not None:
        manifest_path = repo_root / manifest_path if not Path(manifest_path).is_absolute() else manifest_path
    specs = _normalize_specs(models=models, manifest_path=manifest_path)
    rows = [_build_row(repo_root, run_dir, spec) for spec in specs]
    payload = {
        "run_id": run_id,
        "dry_run": dry_run,
        "row_count": len(rows),
        "model_test_order": [row["model"] for row in rows],
        "rows": rows,
        "warnings": [
            "Smoke evidence only proves basic model load and bounded adapter trainability checks.",
            "This matrix does not prove model quality, convergence, or production readiness.",
        ],
    }

    if not dry_run:
        atomic_write_text(matrix_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        atomic_write_text(result_path, _render_result_markdown(run_id, rows))

    return {
        "run_id": run_id,
        "dry_run": dry_run,
        "row_count": len(rows),
        "model_test_order": payload["model_test_order"],
        "matrix_path": relative_path(repo_root, matrix_path),
        "result_path": relative_path(repo_root, result_path),
        "warnings": payload["warnings"],
        "rows": rows,
    }


def _normalize_specs(
    *,
    models: list[str | dict[str, Any]] | None,
    manifest_path: str | Path | None,
) -> list[dict[str, Any]]:
    if models is not None and manifest_path is not None:
        raise ValueError("Pass models or manifest_path, not both")
    if models is not None:
        raw_models: Any = models
    elif manifest_path is not None:
        raw_models = _load_manifest(Path(manifest_path))
    else:
        raw_models = list(DEFAULT_MODEL_SPECS)
    return [_normalize_spec(item) for item in raw_models]


def _load_manifest(path: Path) -> list[Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("models"), list):
        return payload["models"]
    raise ValueError("Model manifest must be a list or an object with a models list")


def _normalize_spec(item: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, str):
        data: dict[str, Any] = {"model": item}
    elif isinstance(item, dict):
        data = dict(item)
    else:
        raise ValueError(f"Unsupported model spec: {item!r}")

    model = str(data.get("model") or "").strip()
    if not model:
        raise ValueError("Model spec is missing model")

    runtime_family = str(data.get("runtime_family") or _infer_runtime_family(model)).strip()
    explicit_surface = data.get("training_surface")
    modalities = _normalize_modalities(data.get("input_modalities"))
    training_surface, claim_basis = _resolve_training_surface(
        runtime_family=runtime_family,
        training_surface=explicit_surface,
        claim_basis=data.get("claim_basis"),
        input_modalities=modalities,
    )

    return {
        "model": model,
        "slug": model_slug(model),
        "runtime_family": runtime_family,
        "training_surface": training_surface,
        "claim_basis": claim_basis,
        "input_modalities": modalities,
        "notes": data.get("notes"),
    }


def _infer_runtime_family(model: str) -> str:
    lowered = model.lower()
    if lowered.startswith("ollama/") or "gguf" in lowered or lowered.endswith(".gguf"):
        return "ollama" if lowered.startswith("ollama/") else "gguf"
    return "mlx_lm"


def _normalize_modalities(value: Any) -> list[str]:
    if value is None:
        return ["text"]
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        raise ValueError(f"Unsupported input_modalities: {value!r}")
    normalized = [str(item).strip().lower() for item in items if str(item).strip()]
    return normalized or ["text"]


def _resolve_training_surface(
    *,
    runtime_family: str,
    training_surface: Any,
    claim_basis: Any,
    input_modalities: list[str],
) -> tuple[str, str]:
    if runtime_family in {"ollama", "gguf"}:
        return "inference_only", "runtime_family_guardrail"
    if any(modality != "text" for modality in input_modalities):
        return "mlx_vlm_load_smoke_only", "multimodal_guardrail"
    if training_surface:
        return str(training_surface), str(claim_basis or "manifest")
    return "mlx_lm_text_trainable", str(claim_basis or "default_text_only_mlx_lm")


def _build_row(root: Path, run_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    model_dir = run_dir / "models" / spec["slug"]
    load_path = model_dir / "load-smoke.json"
    lora_path = model_dir / "lora-smoke.json"
    reload_path = model_dir / "lora-smoke-reload.json"
    load_data = _read_json_if_present(load_path)
    lora_data = _read_json_if_present(lora_path)
    reload_data = _read_json_if_present(reload_path)

    lora_applicable = spec["training_surface"] not in {"inference_only", "mlx_vlm_load_smoke_only"}
    load_smoke = _smoke_status(load_data, missing="missing")
    lora_smoke = _smoke_status(lora_data, missing="missing" if lora_applicable else "not_applicable")
    adapter_reload_smoke = _reload_smoke_status(
        lora_data,
        reload_data,
        missing="missing" if lora_applicable else "not_applicable",
    )
    evidence_paths = [
        relative_path(root, path)
        for path in (load_path, lora_path, reload_path)
        if path.exists()
    ]

    adapter_path = None
    if isinstance(lora_data, dict) and lora_data.get("adapter_path"):
        adapter_path = str(lora_data["adapter_path"])

    commands = _merge_commands(load_data, lora_data, reload_data)
    duration_seconds = _sum_duration_seconds(load_data, lora_data, reload_data)
    exit_code = _primary_value(reload_data, lora_data, load_data, key="exit_code")
    failure_reason = _primary_failure_reason(reload_data, lora_data, load_data)

    return {
        "model": spec["model"],
        "slug": spec["slug"],
        "runtime_family": spec["runtime_family"],
        "training_surface": spec["training_surface"],
        "claim_basis": spec["claim_basis"],
        "load_smoke": load_smoke,
        "lora_smoke": lora_smoke,
        "adapter_reload_smoke": adapter_reload_smoke,
        "adapter_path": adapter_path,
        "commands": commands,
        "duration_seconds": duration_seconds,
        "exit_code": exit_code,
        "failure_reason": failure_reason,
        "evidence_paths": evidence_paths,
    }


def _read_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _smoke_status(payload: dict[str, Any] | None, *, missing: str) -> str:
    if payload is None:
        return missing
    status = payload.get("status")
    if isinstance(status, str) and status.strip():
        lowered = status.strip().lower()
        if lowered in {"pass", "passed", "ok", "success"}:
            return "pass"
        if lowered in {"fail", "failed", "error"}:
            return "fail"
    exit_code = payload.get("exit_code")
    failure_reason = payload.get("failure_reason")
    if exit_code == 0 and not failure_reason:
        return "pass"
    if exit_code not in (None, 0) or failure_reason:
        return "fail"
    return "recorded"


def _reload_smoke_status(
    lora_payload: dict[str, Any] | None,
    reload_payload: dict[str, Any] | None,
    *,
    missing: str,
) -> str:
    if reload_payload is not None:
        return _smoke_status(reload_payload, missing=missing)
    if lora_payload is None:
        return missing
    reload_status = lora_payload.get("reload_status")
    if isinstance(reload_status, str) and reload_status.strip():
        lowered = reload_status.strip().lower()
        if lowered in {"pass", "passed", "ok", "success"}:
            return "pass"
        if lowered in {"fail", "failed", "error"}:
            return "fail"
        return "recorded"
    if "reload_exit_code" in lora_payload or "reload_failure_reason" in lora_payload:
        return _smoke_status(
            {
                "exit_code": lora_payload.get("reload_exit_code"),
                "failure_reason": lora_payload.get("reload_failure_reason"),
            },
            missing=missing,
        )
    return missing


def _collect_commands(payload: dict[str, Any] | None) -> list[Any]:
    if payload is None:
        return []
    raw = payload.get("commands")
    if isinstance(raw, list):
        values = [_command_value(item) for item in raw]
        values = [item for item in values if item]
        if values:
            return values
    single = payload.get("command")
    value = _command_value(single)
    if value:
        return [value]
    return []


def _merge_commands(*payloads: dict[str, Any] | None) -> list[Any]:
    merged: list[Any] = []
    for payload in payloads:
        for command in _collect_commands(payload):
            if command not in merged:
                merged.append(command)
    return merged


def _command_value(value: Any) -> Any:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _sum_duration_seconds(*payloads: dict[str, Any] | None) -> float | int | None:
    values: list[float] = []
    for payload in payloads:
        if payload is None:
            continue
        value = payload.get("duration_seconds")
        if isinstance(value, (int, float)):
            values.append(float(value))
    if not values:
        return None
    total = sum(values)
    return int(total) if total.is_integer() else total


def _primary_value(*payloads: dict[str, Any] | None, key: str) -> Any:
    for payload in payloads:
        if payload is not None and key in payload:
            return payload[key]
    return None


def _primary_failure_reason(
    *payloads: dict[str, Any] | None,
) -> str | None:
    value = _primary_value(*payloads, key="failure_reason")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _render_result_markdown(run_id: str, rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# MLX Trainability Matrix: {run_id}",
        "",
        "Smoke evidence here only proves bounded model load and minimal trainability checks.",
        "It does not prove training quality, convergence, benchmark quality, or production readiness.",
        "",
        "| Model | Surface | Load | LoRA | Reload | Exit | Failure | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        evidence = ", ".join(row["evidence_paths"]) if row["evidence_paths"] else "missing"
        exit_code = row["exit_code"] if row["exit_code"] is not None else "missing"
        failure = row["failure_reason"] or ""
        lines.append(
            f"| {row['model']} | {row['training_surface']} | {row['load_smoke']} | "
            f"{row['lora_smoke']} | {row['adapter_reload_smoke']} | {exit_code} | {failure} | {evidence} |"
        )
    lines.append("")
    return "\n".join(lines)
