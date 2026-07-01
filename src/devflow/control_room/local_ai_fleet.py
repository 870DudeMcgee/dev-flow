from __future__ import annotations

import json
import secrets
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml

from devflow.control_room import local_model_server
from devflow.control_room.local_model_readiness import (
    ExpectedLocalModelLane,
    LocalModelExpectedProfilesManifest,
    load_expected_local_model_manifest,
)
from devflow.control_room.local_model_runtime_lock import list_local_model_runtime_status
from devflow.control_room.paths import relative_path
from devflow.control_room.task_packet import TaskPacket, build_task_packet, render_task_packet_text
from devflow.control_room.task_packet_context import is_path_excluded


DEFAULT_LOCAL_AI_PACKET_MAX_CHARS = 200_000
DEFAULT_SCOUT_CAPACITY_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_SCOUT_CAPACITY_BASE_URL_WITH_V1 = f"{DEFAULT_SCOUT_CAPACITY_BASE_URL}/v1"
DEFAULT_SCOUT_CAPACITY_MODEL = "gemma4-e4b:latest"
DEFAULT_SCOUT_CAPACITY_CANDIDATES = (1, 2, 3)
DEFAULT_SCOUT_CAPACITY_PASSES = 2
DEFAULT_SCOUT_CAPACITY_WARMUP = 1
DEFAULT_SCOUT_CAPACITY_TIMEOUT_SECONDS = 120.0
SCOUT_CAPACITY_REPORT_DIR = Path(".devflow") / "local-ai" / "scout-capacity"


class LocalAICommandError(ValueError):
    pass


def build_local_ai_scout_pack_result(
    root: Path,
    packet_path: Path,
    dry_run: bool,
    base_url: str = DEFAULT_SCOUT_CAPACITY_BASE_URL_WITH_V1,
    model: str = DEFAULT_SCOUT_CAPACITY_MODEL,
    timeout_seconds: float = DEFAULT_SCOUT_CAPACITY_TIMEOUT_SECONDS,
    max_packet_chars: int = DEFAULT_LOCAL_AI_PACKET_MAX_CHARS,
) -> dict[str, Any]:
    root = root.resolve()
    packet = _load_task_packet_file(root, packet_path)
    task_id = packet.get("task_id")
    if not task_id or not isinstance(task_id, str):
        raise LocalAICommandError("Packet payload missing task_id")

    try:
        task_packet = build_task_packet(task_id, root=root)
    except KeyError as exc:
        raise LocalAICommandError(f"Task '{task_id}' not found") from exc

    packet_text = render_task_packet_text(task_packet)
    packet_payload = {
        "schema_version": 1,
        "dry_run": True,
        "mode": "run-scout-pack",
        "packet_path": relative_path(root, packet_path),
        "task_id": task_id,
        "task_title": task_packet.title,
        "worker": "local-packet-scout",
        "worker_profile": "Gemma E4B",
        "authority": "read-only",
        "will_call_model": False,
        "packet_chars": min(len(packet_text), max_packet_chars),
        "max_packet_chars": max_packet_chars,
        "status": "ready",
    }

    if len(packet_text) > max_packet_chars:
        packet_payload["warning"] = (
            f"Rendered task packet exceeds max chars ({max_packet_chars}). "
            "V1 preview remains stable and does not truncate.")

    if dry_run:
        return packet_payload

    from devflow.control_room.local_packet_worker import run_local_packet_review

    try:
        result = run_local_packet_review(
            task_id=task_id,
            root=root,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            max_packet_chars=max_packet_chars,
        )
    except Exception as exc:
        raise LocalAICommandError(f"Packet review failed: {exc}") from exc

    return {
        **packet_payload,
        "dry_run": False,
        "will_call_model": True,
        "status": "success",
        "run_id": result["run_id"],
        "evidence_dir": str(result["evidence_dir"]),
        "response_path": str(result["response_path"]),
    }


def build_local_ai_worker_wave_result(
    root: Path,
    wave_path: Path,
    concurrency: str | int,
    dry_run: bool,
    max_packet_chars: int = DEFAULT_LOCAL_AI_PACKET_MAX_CHARS,
    *,
    base_url: str = DEFAULT_SCOUT_CAPACITY_BASE_URL_WITH_V1,
    model: str = DEFAULT_SCOUT_CAPACITY_MODEL,
    timeout_seconds: float = DEFAULT_SCOUT_CAPACITY_TIMEOUT_SECONDS,
    enforce_capacity_limit: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    auto_requested = isinstance(concurrency, str) and concurrency.strip().lower() == "auto"
    resolved_concurrency = _resolve_concurrency(root, concurrency, enforce_capacity_limit=enforce_capacity_limit)
    if auto_requested and not dry_run and _latest_scout_capacity_failed_at_one(root):
        raise LocalAICommandError(
            "Latest scout-capacity report failed at concurrency 1. Fix Gemma readiness, then run "
            "`devflow local-ai scout-capacity <wave-file> --apply --json` before applying a worker wave."
        )

    wave_jobs = _load_worker_wave_jobs(root, wave_path)
    packet_results = _run_wave_jobs(
        root=root,
        wave_jobs=wave_jobs,
        concurrency=resolved_concurrency,
        dry_run=dry_run,
        max_packet_chars=max_packet_chars,
        base_url=base_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )

    all_success = all(item.get("status") == "success" or (dry_run and item.get("status") == "ready") for item in packet_results)
    return {
        "schema_version": 1,
        "dry_run": dry_run,
        "mode": "run-worker-wave",
        "wave_path": relative_path(root, wave_path),
        "concurrency": resolved_concurrency,
        "status": "success" if all_success else "failed",
        "results": packet_results,
    }


def build_local_ai_scout_capacity_result(
    root: Path,
    wave_path: Path,
    candidates: tuple[int, ...],
    passes: int,
    warmup: int,
    dry_run: bool,
    *,
    timeout_seconds: float = DEFAULT_SCOUT_CAPACITY_TIMEOUT_SECONDS,
    max_packet_chars: int = DEFAULT_LOCAL_AI_PACKET_MAX_CHARS,
    model: str = DEFAULT_SCOUT_CAPACITY_MODEL,
    base_url: str = DEFAULT_SCOUT_CAPACITY_BASE_URL,
) -> dict[str, Any]:
    root = root.resolve()
    if not candidates:
        raise LocalAICommandError("At least one candidate concurrency is required.")
    candidates = tuple(sorted(dict.fromkeys(candidates)))
    if candidates[0] < 1:
        raise LocalAICommandError("Candidate concurrency values must be at least 1.")
    if 1 not in candidates:
        raise LocalAICommandError("Candidate concurrency values must include 1 to establish the latency baseline.")
    if passes < 1 or warmup < 0:
        raise LocalAICommandError("passes must be >= 1 and warmup must be >= 0.")

    wave_jobs = _load_worker_wave_jobs(root, wave_path)
    loaded_ollama_models = inspect_ollama_loaded_models(base_url=base_url)
    loaded_model_state_ok = _loaded_model_state_ok(loaded_ollama_models, model)
    base_payload = {
        "schema_version": 1,
        "mode": "scout-capacity",
        "dry_run": dry_run,
        "wave_path": relative_path(root, wave_path),
        "candidates": list(candidates),
        "passes": passes,
        "warmup": warmup,
        "timeout_seconds": timeout_seconds,
        "max_packet_chars": max_packet_chars,
        "model": model,
        "base_url": base_url,
        "loaded_ollama_models": loaded_ollama_models,
        "loaded_model_state_ok": loaded_model_state_ok,
        "wave_packets": len(wave_jobs),
    }

    if dry_run:
        return {
            **base_payload,
            "status": "ready",
            "max_safe_concurrency": 0,
            "durations": {
                "total_seconds": 0.0,
                "by_candidate_seconds": {str(candidate): 0.0 for candidate in candidates},
            },
            "failure_counts": {
                "failure_count": 0,
                "timeout_failure_count": 0,
                "output_quality_failure_count": 0,
                "loaded_model_failure_count": 0 if loaded_model_state_ok else 1,
            },
            "candidate_results": [
                {
                    "candidate": candidate,
                    "attempts": warmup + passes,
                    "status": "ready",
                    "failure_counts": {
                        "failure_count": 0,
                        "timeout_failure_count": 0,
                        "output_quality_failure_count": 0,
                        "loaded_model_failure_count": 0 if loaded_model_state_ok else 1,
                    },
                }
                for candidate in candidates
            ],
        }

    run_id = _new_capacity_run_id()
    run_report_dir = _capacity_report_dir(root)
    run_report_dir.mkdir(parents=True, exist_ok=True)
    latest_report_path = run_report_dir / "latest.json"
    run_report_path = run_report_dir / f"{run_id}.json"

    candidate_results: list[dict[str, Any]] = []
    total_failure_count = 0
    total_timeout_failures = 0
    total_output_quality_failures = 0
    loaded_model_failure_count = 0 if loaded_model_state_ok else 1
    durations: dict[str, float] = {}
    baseline_p95_seconds: float | None = None
    max_safe_concurrency = 0
    run_start = time.perf_counter()

    for candidate in candidates:
        candidate_start = time.perf_counter()
        attempts = warmup + passes
        passed_attempts = 0
        candidate_failure_count = 0
        candidate_timeout_failure_count = 0
        candidate_output_quality_failure_count = 0
        attempt_durations: list[float] = []
        attempts_run = 0

        if not loaded_model_state_ok:
            candidate_results.append(
                {
                    "candidate": candidate,
                    "attempts": 0,
                    "status": "failed",
                    "failure_counts": {
                        "failure_count": 0,
                        "timeout_failure_count": 0,
                        "output_quality_failure_count": 0,
                        "loaded_model_failure_count": loaded_model_failure_count,
                    },
                    "duration_seconds": round(time.perf_counter() - candidate_start, 6),
                    "attempt_durations_seconds": [],
                    "p95_latency_seconds": None,
                    "latency_gate_ok": False,
                }
            )
            durations[str(candidate)] = 0.0
            break

        for attempt in range(attempts):
            attempts_run += 1
            attempt_payload = _run_wave_attempt_for_capacity(
                root=root,
                wave_path=wave_path,
                concurrency=candidate,
                dry_run=False,
                max_packet_chars=max_packet_chars,
                timeout_seconds=timeout_seconds,
                model=model,
                base_url=base_url,
            )
            candidate_failure_count += attempt_payload["failure_count"]
            candidate_timeout_failure_count += attempt_payload["timeout_failure_count"]
            candidate_output_quality_failure_count += attempt_payload["output_quality_failure_count"]
            total_failure_count += attempt_payload["failure_count"]
            total_timeout_failures += attempt_payload["timeout_failure_count"]
            total_output_quality_failures += attempt_payload["output_quality_failure_count"]
            attempt_durations.append(attempt_payload["duration_seconds"])

            if attempt < warmup:
                continue
            if attempt_payload["status"] == "success":
                passed_attempts += 1
                continue
            break

        candidate_duration = round(time.perf_counter() - candidate_start, 6)
        durations[str(candidate)] = candidate_duration
        p95_seconds = _p95(attempt_durations)
        if candidate == 1 and p95_seconds is not None:
            baseline_p95_seconds = p95_seconds
        latency_ok = candidate == 1 or baseline_p95_seconds is None or (
            p95_seconds is not None and p95_seconds <= baseline_p95_seconds * 2
        )
        candidate_passed = passed_attempts >= passes and loaded_model_state_ok and latency_ok
        candidate_status = "passed" if candidate_passed else "failed"
        candidate_results.append(
            {
                "candidate": candidate,
                "attempts": attempts_run,
                "status": candidate_status,
                "failure_counts": {
                    "failure_count": candidate_failure_count,
                    "timeout_failure_count": candidate_timeout_failure_count,
                    "output_quality_failure_count": candidate_output_quality_failure_count,
                    "loaded_model_failure_count": loaded_model_failure_count,
                },
                "duration_seconds": candidate_duration,
                "attempt_durations_seconds": attempt_durations,
                "p95_latency_seconds": p95_seconds,
                "latency_gate_ok": latency_ok,
            }
        )

        if not candidate_passed:
            break
        max_safe_concurrency = candidate

    payload = {
        **base_payload,
        "status": "success" if max_safe_concurrency >= 1 else "failed",
        "max_safe_concurrency": max_safe_concurrency,
        "durations": {
            "total_seconds": round(time.perf_counter() - run_start, 6),
            "by_candidate_seconds": durations,
        },
        "failure_counts": {
            "failure_count": total_failure_count,
            "timeout_failure_count": total_timeout_failures,
            "output_quality_failure_count": total_output_quality_failures,
            "loaded_model_failure_count": loaded_model_failure_count,
        },
        "candidate_results": candidate_results,
        "run_id": run_id,
    }

    latest_payload = dict(payload)
    run_report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    latest_report_path.write_text(json.dumps(latest_payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["latest_report_path"] = str(latest_report_path)
    payload["run_report_path"] = str(run_report_path)
    return payload


def render_local_ai_scout_capacity_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def scout_openai_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/v1") else f"{normalized}/v1"


def _run_wave_jobs(
    *,
    root: Path,
    wave_jobs: list[Path],
    concurrency: int,
    dry_run: bool,
    max_packet_chars: int,
    base_url: str = DEFAULT_SCOUT_CAPACITY_BASE_URL_WITH_V1,
    model: str = DEFAULT_SCOUT_CAPACITY_MODEL,
    timeout_seconds: float = DEFAULT_SCOUT_CAPACITY_TIMEOUT_SECONDS,
) -> list[dict[str, Any]]:
    packet_results: list[dict[str, Any]] = []
    for batch_start in range(0, len(wave_jobs), concurrency):
        batch_indexes = range(batch_start, min(batch_start + concurrency, len(wave_jobs)))
        batch_failed = False
        indexed_results: dict[int, dict[str, Any]] = {}

        if dry_run:
            for packet_index in batch_indexes:
                result = _run_wave_packet(
                    root=root,
                    packet_path=wave_jobs[packet_index],
                    dry_run=dry_run,
                    max_packet_chars=max_packet_chars,
                    base_url=base_url,
                    model=model,
                    timeout_seconds=timeout_seconds,
                )
                indexed_results[packet_index] = result
                if result.get("status") == "failed":
                    batch_failed = True
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                future_to_index = {
                    executor.submit(
                        _run_wave_packet,
                        root=root,
                        packet_path=wave_jobs[packet_index],
                        dry_run=dry_run,
                        max_packet_chars=max_packet_chars,
                        base_url=base_url,
                        model=model,
                        timeout_seconds=timeout_seconds,
                    ): packet_index
                    for packet_index in batch_indexes
                }
                for future in as_completed(future_to_index):
                    packet_index = future_to_index[future]
                    result = future.result()
                    indexed_results[packet_index] = result
                    if result.get("status") == "failed":
                        batch_failed = True

        for packet_index in batch_indexes:
            result = indexed_results[packet_index]
            result["wave_index"] = packet_index + 1
            result["wave_packet_index"] = packet_index
            packet_results.append(result)

        if batch_failed and not dry_run:
            break

    return packet_results


def _run_wave_packet(
    *,
    root: Path,
    packet_path: Path,
    dry_run: bool,
    max_packet_chars: int,
    base_url: str,
    model: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        return build_local_ai_scout_pack_result(
            root=root,
            packet_path=packet_path,
            dry_run=dry_run,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            max_packet_chars=max_packet_chars,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "schema_version": 1,
            "dry_run": dry_run,
            "mode": "run-scout-pack",
            "packet_path": relative_path(root, packet_path),
            "status": "failed",
            "error": str(exc),
        }


def _run_wave_attempt_for_capacity(
    *,
    root: Path,
    wave_path: Path,
    concurrency: int,
    dry_run: bool,
    max_packet_chars: int,
    timeout_seconds: float,
    model: str,
    base_url: str,
) -> dict[str, Any]:
    attempt_start = time.perf_counter()
    try:
        result = build_local_ai_worker_wave_result(
            root=root,
            wave_path=wave_path,
            concurrency=concurrency,
            dry_run=dry_run,
            max_packet_chars=max_packet_chars,
            base_url=scout_openai_base_url(base_url),
            model=model,
            timeout_seconds=timeout_seconds,
            enforce_capacity_limit=False,
        )
        run_status = result["status"]
        output_quality_failures = _count_output_quality_failures(result["results"])
        if output_quality_failures > 0:
            run_status = "failed"
        timeout_failure_count = sum(
            1
            for result_item in result["results"]
            if result_item.get("status") == "failed"
            and "timeout" in str(result_item.get("error", "")).lower()
        )
        failure_count = sum(
            1 for result_item in result["results"] if result_item.get("status") != "success" and result_item.get("status") != "ready"
        )
    except Exception as exc:  # noqa: BLE001
        run_status = "failed"
        failure_count = 1
        timeout_failure_count = 1 if "timeout" in str(exc).lower() else 0
        output_quality_failures = 0

    return {
        "status": run_status,
        "failure_count": failure_count,
        "timeout_failure_count": timeout_failure_count,
        "output_quality_failure_count": output_quality_failures,
        "duration_seconds": round(time.perf_counter() - attempt_start, 6),
    }


def _resolve_concurrency(
    root: Path,
    concurrency: str | int,
    *,
    enforce_capacity_limit: bool,
) -> int:
    requested = concurrency
    if isinstance(requested, str):
        text = requested.strip().lower()
        if text == "auto":
            latest = _load_latest_scout_capacity(root)
            if isinstance(latest, dict):
                max_safe = latest.get("max_safe_concurrency")
                if (
                    latest.get("status") == "success"
                    and isinstance(max_safe, int)
                    and max_safe > 0
                ):
                    return max_safe
            return 1
        try:
            requested = int(text)
        except ValueError as exc:
            raise LocalAICommandError("Concurrency must be an integer or 'auto'.") from exc

    if requested < 1:
        raise LocalAICommandError("Concurrency must be at least 1.")

    if not enforce_capacity_limit:
        return requested

    latest = _load_latest_scout_capacity(root)
    if (
        isinstance(latest, dict)
        and latest.get("status") == "failed"
        and latest.get("max_safe_concurrency") == 0
        and requested == 1
    ):
        raise LocalAICommandError(
            "Latest scout-capacity report failed at concurrency 1. Fix Gemma readiness, then run "
            "`devflow local-ai scout-capacity <wave-file> --apply --json` before applying a worker wave."
        )

    if requested == 1:
        return requested

    if not isinstance(latest, dict):
        raise LocalAICommandError(
            "No passing scout-capacity report found. Run `devflow local-ai scout-capacity <wave-file> --apply --json` first."
        )
    max_safe = latest.get("max_safe_concurrency")
    latest_status = latest.get("status")
    if not isinstance(max_safe, int) or max_safe < 1 or latest_status != "success":
        raise LocalAICommandError(
            "Latest scout-capacity report is not successful. Run `devflow local-ai scout-capacity <wave-file> --apply --json` first."
        )
    if requested > max_safe:
        raise LocalAICommandError(
            f"Concurrency {requested} exceeds measured safe concurrency ({max_safe}). "
            "Run `devflow local-ai scout-capacity <wave-file> --apply --json` to re-measure."
        )
    return requested


def _capacity_report_dir(root: Path) -> Path:
    return root / SCOUT_CAPACITY_REPORT_DIR


def _latest_scout_capacity_concurrency(root: Path) -> int:
    latest = _load_latest_scout_capacity(root)
    if not isinstance(latest, dict):
        return 0
    if latest.get("status") != "success":
        return 0
    max_safe = latest.get("max_safe_concurrency")
    if not isinstance(max_safe, int) or max_safe < 1:
        return 0
    return max_safe


def _load_latest_scout_capacity(root: Path) -> dict[str, Any] | None:
    report_path = _capacity_report_dir(root) / "latest.json"
    if not report_path.exists():
        return None
    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _latest_scout_capacity_failed_at_one(root: Path) -> bool:
    latest = _load_latest_scout_capacity(root)
    return (
        isinstance(latest, dict)
        and latest.get("status") == "failed"
        and latest.get("max_safe_concurrency") == 0
    )


def _new_capacity_run_id() -> str:
    return f"{int(time.time())}-{secrets.token_hex(4)}"


def _loaded_model_state_ok(loaded_state: dict[str, Any], model: str) -> bool:
    loaded_models = _dict_rows(loaded_state.get("loaded_models"))
    loaded_names = {
        str(item.get("name"))
        for item in loaded_models
        if isinstance(item.get("name"), str)
    }
    return loaded_names <= {model}


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999999) - 1))
    return round(ordered[index], 6)


def _count_output_quality_failures(results: list[dict[str, Any]]) -> int:
    failures = 0
    for item in results:
        if item.get("status") != "success":
            continue
        response_path = item.get("response_path")
        if not response_path:
            failures += 1
            continue
        try:
            text = Path(response_path).read_text(encoding="utf-8").strip()
        except OSError:
            failures += 1
            continue
        if not text:
            failures += 1
    return failures


def render_local_ai_scout_pack_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def render_local_ai_worker_wave_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _load_worker_wave_jobs(root: Path, wave_path: Path) -> list[Path]:
    path = _resolve_packet_path(root, wave_path)
    if not path.exists():
        raise LocalAICommandError(f"Wave file not found: {path}")

    payload = _load_structured_payload(path)
    jobs = payload if isinstance(payload, list) else payload.get("jobs") if isinstance(payload, dict) else None
    if jobs is None or not isinstance(jobs, list):
        raise LocalAICommandError("Wave file must be a list of packets or a mapping with a 'jobs' list")

    packet_paths: list[Path] = []
    for item in jobs:
        if isinstance(item, str):
            packet_paths.append(_resolve_packet_path(root, Path(item)))
            continue
        if not isinstance(item, dict):
            raise LocalAICommandError("Wave job entries must be packet paths or mapping objects")
        packet_value = item.get("packet") or item.get("packet_path")
        if not isinstance(packet_value, str):
            raise LocalAICommandError("Each wave job requires 'packet' or 'packet_path'")
        packet_paths.append(_resolve_packet_path(root, Path(packet_value)))

    if not packet_paths:
        raise LocalAICommandError("Wave file contains no jobs")

    return packet_paths


def _load_task_packet_file(root: Path, packet_path: Path) -> dict[str, Any]:
    path = _resolve_packet_path(root, packet_path)
    payload = _load_structured_payload(path)
    if not isinstance(payload, dict):
        raise LocalAICommandError("Packet content is not a JSON/YAML map")
    if not payload.get("task_id"):
        raise LocalAICommandError("Packet content is missing task_id")
    try:
        TaskPacket.model_validate(payload)
    except Exception as exc:
        raise LocalAICommandError(f"Packet content is not a valid task packet: {exc}") from exc
    return payload


def _load_structured_payload(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise LocalAICommandError(f"Packet file is empty: {path}")

    if path.suffix.lower() in {".yml", ".yaml"}:
        try:
            payload = yaml.safe_load(text)
        except Exception as exc:
            raise LocalAICommandError(f"Failed to parse YAML packet file: {path}: {exc}") from exc
    else:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            try:
                payload = yaml.safe_load(text)
            except Exception as exc:
                raise LocalAICommandError(f"Failed to parse packet file: {path}: {exc}") from exc

    if payload is None:
        raise LocalAICommandError(f"Packet file is empty: {path}")
    return payload


def _resolve_packet_path(root: Path, packet_path: Path) -> Path:
    candidate = packet_path if packet_path.is_absolute() else (root / packet_path)
    normalized = candidate.expanduser().resolve()
    if not normalized.exists():
        raise LocalAICommandError(f"Packet file does not exist: {packet_path}")
    if not normalized.is_file():
        raise LocalAICommandError(f"Packet path is not a file: {packet_path}")

    packet_relative_path = relative_path(root, normalized)
    if is_path_excluded(packet_relative_path) and not (
        normalized.name.endswith("packet.json") or normalized.name.endswith("packet.md")
    ):
        raise LocalAICommandError(f"Refusing excluded packet path: {packet_path}")
    return normalized


_SCOUT_WARNING = (
    "Desired scout target Gemma E4B is not present in the Dev-Flow local model manifest; "
    "lifecycle recommendations stay advisory-only."
)

_NIGHTLY_DRY_RUN_TASK_ID = "<task-id>"


def build_local_ai_nightly_dry_run_plan(root: Path) -> dict[str, Any]:
    """Return a deterministic dry-run-only nightly plan with three phases."""
    manifest = load_expected_local_model_manifest()
    qwen_profile = _nightly_choose_qwen_profile(manifest)
    scout_target, scout_warnings = _scout_target(manifest)
    warnings = list(scout_warnings)
    measured_concurrency = _latest_scout_capacity_concurrency(root)
    effective_concurrency = measured_concurrency if measured_concurrency >= 1 else 1
    if measured_concurrency <= 0:
        warnings.append("Scout capacity is unmeasured. Run `devflow local-ai scout-capacity <wave-file> --dry-run` to measure safe concurrency.")
    else:
        warnings.append(f"Using measured scout capacity concurrency={measured_concurrency}.")
    qwen_server_profile = qwen_profile.get("server_id") or qwen_profile.get("profile_id")

    if not qwen_server_profile:
        warnings.append("No managed local Qwen profile is present in the manifest for dry-run orchestration.")
    if not scout_target.get("manifest_backed"):
        warnings.append("Scout target is not present in the manifest; scout switch will report setup-needed.")

    phases: list[dict[str, Any]] = [
        {
            "phase_id": "qwen-wave",
            "title": "Qwen worker packet phase",
            "steps": [
                {
                    "step_id": "start_qwen",
                    "summary": "Start local Qwen server",
                    "command": "devflow local-ai switch supervisor --dry-run --json",
                    "dry_run": True,
                    "will_call_model": False,
                    "scope": "orchestration",
                },
                {
                    "step_id": "produce_worker_packets",
                    "summary": "Produce Qwen worker packets",
                    "command": f"devflow task packet {_NIGHTLY_DRY_RUN_TASK_ID} --json",
                    "dry_run": True,
                    "will_call_model": False,
                    "scope": "packet-generation",
                },
                {
                    "step_id": "stop_qwen",
                    "summary": "Stop local Qwen server",
                    "command": (
                        f"devflow local-model stop {qwen_server_profile} --dry-run --json"
                        if qwen_server_profile
                        else "devflow local-model stop-all --dry-run --json"
                    ),
                    "dry_run": True,
                    "will_call_model": False,
                    "scope": "orchestration",
                },
            ],
        },
        {
            "phase_id": "gemma-wave",
            "title": "Gemma scout wave",
            "steps": [
                {
                    "step_id": "start_gemma",
                    "summary": "Start local Gemma server",
                    "command": "devflow local-ai switch scout --dry-run --json",
                    "dry_run": True,
                    "will_call_model": False,
                    "scope": "orchestration",
                },
                {
                    "step_id": "run_scout_wave",
                    "summary": "Run Gemma scout packet wave",
                    "command": (
                        f"devflow local-ai run-worker-wave <wave-file> --concurrency {effective_concurrency} --dry-run --json"
                    ),
                    "dry_run": True,
                    "will_call_model": False,
                    "scope": "scout",
                    "note": f"Scout target profile: {scout_target.get('label')}",
                },
                {
                    "step_id": "stop_gemma",
                    "summary": "Stop local Gemma server",
                    "command": "devflow local-ai stop-all --dry-run --include-ollama --json",
                    "dry_run": True,
                    "will_call_model": False,
                    "scope": "orchestration",
                },
            ],
        },
        {
            "phase_id": "qwen-review",
            "title": "Qwen review readiness phase",
            "steps": [
                {
                    "step_id": "restart_qwen_for_review",
                    "summary": "Restart local Qwen server for review",
                    "command": "devflow local-ai switch supervisor --dry-run --json",
                    "dry_run": True,
                    "will_call_model": False,
                    "scope": "orchestration",
                }
            ],
        },
    ]

    return {
        "schema_version": 1,
        "plan_name": "nightly-dry-run-local-ai",
        "dry_run": True,
        "root": str(root.resolve()),
        "phases": phases,
        "action_count": 7,
        "all_dry_run_only": True,
        "warnings": warnings,
    }


def render_local_ai_nightly_dry_run_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)

_LOCAL_AI_SUPERVISOR_PROFILE_ID = "hermes-qwen36-27b-q5-mtp"
_LOCAL_AI_SCOUT_PROFILE_ID = "hermes-gemma4-e4b"
_LOCAL_AI_SCOUT_MODEL_ID = "gemma4-e4b:latest"
_LOCAL_AI_SCOUT_KEEP_ALIVE = "1m"
_LOCAL_AI_SCOUT_START_TIMEOUT_SECONDS = 90.0


def build_local_ai_switch(
    root: Path,
    role: str,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Compose the switch payload for supervisor/scout and keep switches side-effect-light by default."""
    requested_role = (role or "").strip().lower()
    if requested_role not in {"supervisor", "scout"}:
        raise LocalAICommandError("Unsupported role. Use one of: supervisor, scout.")

    manifest = load_expected_local_model_manifest()
    scout_runtime: dict[str, Any] | None = None
    scout_installed: dict[str, Any] | None = None
    target_model_for_ollama = None
    if requested_role == "scout":
        scout_target, _ = _scout_target(manifest)
        target_model_for_ollama = scout_target.get("model_id")
        scout_base_url = scout_target.get("base_url") or "http://127.0.0.1:11434"
        scout_runtime = inspect_ollama_loaded_models(base_url=scout_base_url)
        scout_installed = inspect_ollama_installed_models(base_url=scout_base_url)
    else:
        scout_runtime = inspect_ollama_loaded_models()
    loaded_ollama_models = _dict_rows(scout_runtime.get("loaded_models"))
    loaded_ollama_names = {
        str(model.get("name"))
        for model in loaded_ollama_models
        if isinstance(model.get("name"), str)
    }
    scout_ready = (
        requested_role == "scout"
        and isinstance(target_model_for_ollama, str)
        and loaded_ollama_names == {target_model_for_ollama}
    )
    include_ollama = bool(loaded_ollama_names) and not scout_ready
    skip_stop_for_unready_scout_apply = requested_role == "scout" and not scout_ready and not dry_run
    if skip_stop_for_unready_scout_apply:
        stop_result = {"action": "stop", "status": "skipped", "processes": []}
    else:
        stop_result = local_model_server.stop_local_model_servers(
            root,
            include_ollama=include_ollama,
            dry_run=dry_run,
            timeout_seconds=15.0,
        )

    if requested_role == "supervisor":
        target = _supervisor_target(manifest)
        target_model = target.get("model_id")
        target_provider = target.get("provider_id")
        target_port = target.get("port")
        if not isinstance(target.get("server_id"), str) or not target.get("server_id"):
            raise LocalAICommandError("Supervisor target has no managed local model server.")

        start_result = local_model_server.start_local_model_server(
            root,
            target["server_id"],
            dry_run=dry_run,
            wait_for_ready=not dry_run,
        )
        started_target = {
            "status": start_result.get("status"),
            "server_id": start_result.get("server"),
            "provider": start_result.get("provider"),
            "model": start_result.get("model"),
            "base_url": start_result.get("base_url"),
            "port": start_result.get("port"),
            "pid": start_result.get("pid"),
            "ready": start_result.get("ready"),
        }
        switch_status = str(start_result.get("status") or "unknown")
        warnings: list[str] = []
    else:
        target, scout_warnings = _scout_target(manifest)
        target_model = target.get("model_id")
        target_provider = target.get("provider_id")
        target_port = target.get("port")
        runtime = scout_runtime or inspect_ollama_loaded_models(base_url=target.get("base_url") or "http://127.0.0.1:11434")
        installed = scout_installed or inspect_ollama_installed_models(base_url=target.get("base_url") or "http://127.0.0.1:11434")
        loaded_names = [
            str(model.get("name"))
            for model in _dict_rows(runtime.get("loaded_models"))
            if isinstance(model.get("name"), str)
        ]
        installed_names = {
            str(model.get("name"))
            for model in _dict_rows(installed.get("installed_models"))
            if isinstance(model.get("name"), str)
        }
        warnings = list(scout_warnings)
        warnings.append(f"Ollama runtime status: {runtime.get('status', 'unknown')}.")
        if runtime.get("status") == "loaded" and loaded_names == [target_model]:
            switch_status = "ready"
            started_target = {
                "status": "ready",
                "provider": target_provider,
                "model": target_model,
                "base_url": target.get("base_url"),
                "port": target_port,
            }
        elif target_model in installed_names and not loaded_names:
            if dry_run:
                switch_status = "would_start"
                started_target = None
            else:
                start_result = start_ollama_model(
                    target_model,
                    base_url=target.get("base_url") or "http://127.0.0.1:11434",
                    keep_alive=_LOCAL_AI_SCOUT_KEEP_ALIVE,
                    timeout_seconds=_LOCAL_AI_SCOUT_START_TIMEOUT_SECONDS,
                )
                switch_status = str(start_result.get("status") or "setup_needed")
                if switch_status == "started":
                    started_target = {
                        "status": switch_status,
                        "provider": start_result.get("provider"),
                        "model": start_result.get("model"),
                        "base_url": start_result.get("base_url"),
                        "port": target_port,
                    }
                else:
                    started_target = None
                    if "error" in start_result:
                        warnings.append(start_result["error"])
                if not dry_run:
                    warnings.append(
                        f"Scout target '{target_model}' is in Ollama tags; apply is attempting to load it."
                    )
        else:
            switch_status = "setup_needed"
            started_target = None
            if target_model in loaded_names:
                warnings.append(
                    f"Scout target '{target_model}' is loaded with other Ollama models; unload the other models before switching."
                )
            else:
                warnings.append(
                    f"Scout target '{target_model}' is not currently available in the Ollama runtime; run it in Ollama before switching."
                )
            if skip_stop_for_unready_scout_apply:
                warnings.append("No stop was applied because the scout target was not exclusively ready.")

    return {
        "schema_version": 1,
        "action": "switch",
        "status": switch_status,
        "role": requested_role,
        "dry_run": dry_run,
        "apply": not dry_run,
        "model": target_model,
        "provider": target_provider,
        "port": target_port,
        "include_ollama_stop": include_ollama,
        "stop_skipped": skip_stop_for_unready_scout_apply,
        "stopped_targets": _stopped_targets(stop_result),
        "started_target": started_target,
        "warnings": warnings,
    }


def render_local_ai_switch_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def _stopped_targets(stop_result: dict[str, Any]) -> list[dict[str, Any]]:
    stopped_targets: list[dict[str, Any]] = []
    for process in _dict_rows(stop_result.get("processes")):
        stopped_targets.append(
            {
                "pid": process.get("pid"),
                "kind": process.get("kind"),
                "provider": process.get("provider"),
                "model": process.get("model"),
                "alias": process.get("alias"),
                "port": process.get("port"),
            }
        )
    return stopped_targets

def build_local_ai_snapshot(root: Path, *, include_ollama: bool = True) -> dict[str, Any]:
    manifest = load_expected_local_model_manifest()
    server_status = local_model_server.local_model_server_status(include_ollama=include_ollama)
    inventory = local_model_server.build_local_model_server_inventory(include_ollama=include_ollama)
    ollama_runtime = inspect_ollama_loaded_models() if include_ollama else {"status": "skipped", "loaded_models": []}
    active_model_processes = _active_model_processes(server_status, ollama_runtime)
    runtime_locks = list_local_model_runtime_status(root)
    supervisor_target = _supervisor_target(manifest)
    scout_target, warnings = _scout_target(manifest)
    recommendation = build_local_ai_recommendation(
        root,
        snapshot={
            "local_model_server": {"status": server_status, "inventory": inventory},
            "ollama_runtime": ollama_runtime,
            "runtime_lock": _runtime_lock_payload(runtime_locks),
            "supervisor_target": supervisor_target,
        },
    )
    return {
        "schema_version": 1,
        "policy": {
            "one_active_model_role": True,
        },
        "supervisor_target": supervisor_target,
        "scout_target": scout_target,
        "local_model_server": {
            "status": server_status,
            "inventory": inventory,
        },
        "ollama_runtime": ollama_runtime,
        "active_model_processes": active_model_processes,
        "runtime_lock": _runtime_lock_payload(runtime_locks),
        "recommended_next_action": recommendation,
        "warnings": warnings,
    }


def build_local_ai_recommendation(
    root: Path,
    *,
    snapshot: dict[str, Any] | None = None,
    include_ollama: bool = True,
) -> dict[str, Any]:
    fleet = snapshot or build_local_ai_snapshot(root, include_ollama=include_ollama)
    local_server = _mapping(fleet.get("local_model_server"))
    server_status = _mapping(local_server.get("status"))
    ollama_runtime = _mapping(fleet.get("ollama_runtime"))
    runtime_lock = _mapping(fleet.get("runtime_lock"))
    supervisor_target = _mapping(fleet.get("supervisor_target"))
    processes = _active_model_processes(server_status, ollama_runtime)

    if processes:
        has_ollama = any(process.get("kind") == "ollama" for process in processes)
        command = "devflow local-ai stop-all --dry-run"
        fallback = "devflow local-model stop --dry-run"
        if has_ollama:
            command = f"{command} --include-ollama"
            fallback = f"{fallback} --include-ollama"
        command = f"{command} --json"
        fallback = f"{fallback} --json"
        return {
            "schema_version": 1,
            "action_id": "stop_before_switch",
            "summary": "A local model server is already running. Preview the stop plan before switching roles.",
            "recommended_command": command,
            "fallback_command": fallback,
            "next_safe_action": command,
            "reason": "Dev-Flow keeps one active local model role at a time.",
        }

    if runtime_lock.get("status") in {"running", "stale"}:
        owner = _mapping(runtime_lock.get("owner"))
        return {
            "schema_version": 1,
            "action_id": "inspect_runtime_lock",
            "summary": "No server is running, but the machine-wide local model runtime lock is occupied.",
            "recommended_command": "devflow operating-layer snapshot --json",
            "fallback_command": None,
            "next_safe_action": "Inspect the runtime lock owner before switching local model roles.",
            "reason": (
                f"Current owner: {owner.get('provider') or 'unknown'}/{owner.get('model') or 'unknown'} "
                f"via {owner.get('worker_id') or owner.get('operation') or 'unknown'}."
            ),
        }

    server_id = supervisor_target.get("server_id")
    if isinstance(server_id, str) and server_id:
        command = f"devflow local-model start {server_id} --dry-run --json"
    else:
        command = "devflow local-model inventory --json"
    return {
        "schema_version": 1,
        "action_id": "start_supervisor_dry_run",
        "summary": "No local model server is running. Dry-run the supervisor target before switching.",
        "recommended_command": command,
        "fallback_command": "devflow local-model inventory --json",
        "next_safe_action": command,
        "reason": "Keep the next launch explicit and side-effect-light.",
    }


def inspect_ollama_loaded_models(
    *,
    base_url: str = "http://127.0.0.1:11434",
    timeout_seconds: float = 1.0,
) -> dict[str, Any]:
    """Read Ollama's loaded-model state; the daemon alone is not an active role."""

    url = base_url.rstrip("/") + "/api/ps"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {
            "status": "unavailable",
            "base_url": base_url,
            "loaded_models": [],
            "error": str(exc),
        }
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return {
            "status": "invalid_json",
            "base_url": base_url,
            "loaded_models": [],
            "error": str(exc),
        }
    models = _dict_rows(payload.get("models") if isinstance(payload, dict) else None)
    return {
        "status": "loaded" if models else "idle",
        "base_url": base_url,
        "loaded_models": models,
    }


def inspect_ollama_installed_models(
    *,
    base_url: str = "http://127.0.0.1:11434",
    timeout_seconds: float = 1.0,
) -> dict[str, Any]:
    """Read Ollama's installed model list from /api/tags."""

    url = base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {
            "status": "unavailable",
            "base_url": base_url,
            "installed_models": [],
            "error": str(exc),
        }
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return {
            "status": "invalid_json",
            "base_url": base_url,
            "installed_models": [],
            "error": str(exc),
        }
    models = _dict_rows(payload.get("models") if isinstance(payload, dict) else None)
    return {
        "status": "available" if models else "empty",
        "base_url": base_url,
        "installed_models": models,
    }


def start_ollama_model(
    model_id: str,
    *,
    base_url: str = "http://127.0.0.1:11434",
    keep_alive: str = _LOCAL_AI_SCOUT_KEEP_ALIVE,
    timeout_seconds: float = _LOCAL_AI_SCOUT_START_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Send a tiny request that loads the model into Ollama memory."""

    url = base_url.rstrip("/") + "/api/generate"
    payload: dict[str, Any] = {
        "model": model_id,
        "keep_alive": keep_alive,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {
            "status": "start_failed",
            "provider": "ollama",
            "model": model_id,
            "base_url": base_url,
            "error": str(exc),
        }

    if not body.strip():
        return {
            "status": "started",
            "provider": "ollama",
            "model": model_id,
            "base_url": base_url,
        }

    try:
        payload_response = json.loads(body)
    except json.JSONDecodeError as exc:
        return {
            "status": "start_failed",
            "provider": "ollama",
            "model": model_id,
            "base_url": base_url,
            "error": str(exc),
        }

    if payload_response.get("done") is False:
        return {
            "status": "start_pending",
            "provider": "ollama",
            "model": model_id,
            "base_url": base_url,
        }

    return {
        "status": "started",
        "provider": "ollama",
        "model": model_id,
        "base_url": base_url,
        "response": payload_response,
    }


def render_local_ai_snapshot_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def render_local_ai_snapshot_lines(payload: dict[str, Any]) -> tuple[str, ...]:
    policy = _mapping(payload.get("policy"))
    supervisor = _mapping(payload.get("supervisor_target"))
    scout = _mapping(payload.get("scout_target"))
    local_server = _mapping(payload.get("local_model_server"))
    status = _mapping(local_server.get("status"))
    ollama_runtime = _mapping(payload.get("ollama_runtime"))
    active_model_processes = _dict_rows(payload.get("active_model_processes"))
    runtime_lock = _mapping(payload.get("runtime_lock"))
    recommendation = _mapping(payload.get("recommended_next_action"))
    lines = [
        "Local AI fleet snapshot",
        f"policy.one_active_model_role: {bool(policy.get('one_active_model_role'))}",
        f"supervisor_target: {_target_label(supervisor)}",
        f"scout_target: {_target_label(scout)}",
        f"server_status: {status.get('status', 'unknown')} ({status.get('running_count', 0)} running)",
        f"ollama_loaded_models: {len(_dict_rows(ollama_runtime.get('loaded_models')))}",
        f"active_model_processes: {len(active_model_processes)}",
        f"runtime_lock: {runtime_lock.get('status', 'free')}",
        f"next_safe_action: {recommendation.get('next_safe_action') or 'none'}",
    ]
    for warning in _string_rows(payload.get("warnings")):
        lines.append(f"warning: {warning}")
    return tuple(lines)


def render_local_ai_recommendation_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def render_local_ai_recommendation_lines(payload: dict[str, Any]) -> tuple[str, ...]:
    return (
        f"action_id: {payload.get('action_id')}",
        f"summary: {payload.get('summary')}",
        f"recommended_command: {payload.get('recommended_command')}",
        f"reason: {payload.get('reason')}",
    )


def _supervisor_target(manifest: LocalModelExpectedProfilesManifest) -> dict[str, Any]:
    preferred = manifest.lanes.get(_LOCAL_AI_SUPERVISOR_PROFILE_ID)
    if preferred is not None and preferred.local_server_backed:
        return _lane_payload(preferred, manifest_backed=True)
    candidates = [
        lane
        for lane in manifest.lanes.values()
        if lane.local_server_backed and lane.role == "frontier_planner_architect_reviewer"
    ]
    lane = min(candidates, key=lambda item: (item.min_ram_gb, item.lane_id)) if candidates else None
    return _lane_payload(lane, manifest_backed=lane is not None)


def _nightly_choose_qwen_profile(manifest: LocalModelExpectedProfilesManifest) -> dict[str, Any]:
    candidates = [
        lane
        for lane in manifest.lanes.values()
        if lane.local_server_backed
        and lane.role == "frontier_planner_architect_reviewer"
        and "qwen" in lane.profile_id
    ]
    if not candidates:
        return _supervisor_target(manifest)
    return _lane_payload(sorted(candidates, key=lambda item: item.lane_id)[0], manifest_backed=True)


def _scout_target(manifest: LocalModelExpectedProfilesManifest) -> tuple[dict[str, Any], list[str]]:
    preferred = manifest.lanes.get(_LOCAL_AI_SCOUT_PROFILE_ID)
    if preferred is not None:
        return _lane_payload(preferred, manifest_backed=True), []
    for lane in manifest.lanes.values():
        if lane.role == "scout":
            return _lane_payload(lane, manifest_backed=True), []
    return (
        {
            "label": "Gemma E4B",
            "role": "scout",
            "manifest_backed": False,
            "lane_id": None,
            "profile_id": _LOCAL_AI_SCOUT_PROFILE_ID,
            "provider_id": "ollama",
            "model_id": _LOCAL_AI_SCOUT_MODEL_ID,
            "server_id": None,
            "base_url": "http://127.0.0.1:11434",
            "port": 11434,
            "warning": _SCOUT_WARNING,
        },
        [_SCOUT_WARNING],
    )


def _lane_payload(lane: ExpectedLocalModelLane | None, *, manifest_backed: bool) -> dict[str, Any]:
    if lane is None:
        return {
            "label": None,
            "role": None,
            "manifest_backed": manifest_backed,
            "lane_id": None,
            "profile_id": None,
            "provider_id": None,
            "model_id": None,
            "server_id": None,
            "base_url": None,
            "port": None,
        }
    return {
        "label": lane.profile_id,
        "role": lane.role,
        "manifest_backed": manifest_backed,
        "lane_id": lane.lane_id,
        "profile_id": lane.profile_id,
        "provider_id": lane.provider_id,
        "model_id": lane.model_id,
        "server_id": lane.provider_id if lane.local_server_backed else None,
        "base_url": lane.base_url,
        "port": lane.port,
    }


def _runtime_lock_payload(runtime_locks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not runtime_locks:
        return {"status": "free", "locks": {}}
    key = sorted(runtime_locks)[0]
    owner = dict(runtime_locks[key])
    return {
        "status": owner.get("state") or "running",
        "lock_key": key,
        "owner": owner,
        "locks": runtime_locks,
    }


def _active_model_processes(server_status: dict[str, Any], ollama_runtime: dict[str, Any]) -> list[dict[str, Any]]:
    processes = _dict_rows(server_status.get("processes"))
    loaded_ollama = bool(_dict_rows(ollama_runtime.get("loaded_models")))
    return [
        process
        for process in processes
        if process.get("kind") != "ollama" or loaded_ollama
    ]


def _target_label(target: dict[str, Any]) -> str:
    label = target.get("label")
    role = target.get("role")
    if label and role:
        return f"{label} ({role})"
    if label:
        return str(label)
    return "none"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_rows(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
