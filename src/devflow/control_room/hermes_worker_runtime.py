from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from devflow.control_room.local_model_runtime_lock import (
    LocalModelRuntimeLockError,
    local_model_runtime_lock,
)
from devflow.control_room.paths import relative_path
from devflow.control_room.persistence import atomic_write_text, utc_now
from devflow.control_room.serial_local_agent_run import (
    build_serial_local_run_preflight,
    serial_local_run_dir,
)

HERMES_WORKER_RUNTIME_SCHEMA_VERSION = 1
DEFAULT_HERMES_EXECUTABLE = "hermes"
DEFAULT_HERMES_TIMEOUT_SECONDS = 900


class HermesWorkerRuntimeError(ValueError):
    """Raised when a Hermes worker runtime launch cannot be prepared safely."""


def dry_run_hermes_worker_runtime(
    root: Path,
    *,
    run_id: str,
    hermes_profile: str,
    force: bool = False,
    hermes_executable: str = DEFAULT_HERMES_EXECUTABLE,
) -> dict[str, Any]:
    """Validate a SerialLocalRun packet and preview a Hermes argv list.

    This is deliberately dry-run only. It reads existing packet evidence and
    current runtime lock state, but it does not launch Hermes, write launch
    evidence, mutate git, run tests, or start providers/local models.
    """

    request = _prepare_hermes_worker_runtime(
        root,
        run_id=run_id,
        hermes_profile=hermes_profile,
        force=force,
        hermes_executable=hermes_executable,
        require_launch_ready=True,
    )
    return _base_payload(request, will_launch_hermes=False, dry_run=True) | {
        "launch_allowed": True,
    }


def run_hermes_worker_runtime(
    root: Path,
    *,
    run_id: str,
    hermes_profile: str,
    force: bool = False,
    hermes_executable: str = DEFAULT_HERMES_EXECUTABLE,
    timeout_seconds: int = DEFAULT_HERMES_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Launch a Hermes profile for a validated packet and capture evidence.

    Tests pass a fake executable through ``hermes_executable``. The production
    path uses the same argv-list invocation and never shells out through a
    string. This function captures launch evidence only; it does not run the
    packet completion verifier or claim task verification success.
    """

    request = _prepare_hermes_worker_runtime(
        root,
        run_id=run_id,
        hermes_profile=hermes_profile,
        force=force,
        hermes_executable=hermes_executable,
        require_launch_ready=True,
    )
    timeout_value = _positive_int(timeout_seconds, "timeout_seconds")
    stdout_path = request["run_dir_path"] / "hermes-stdout.txt"
    stderr_path = request["run_dir_path"] / "hermes-stderr.txt"
    evidence_path = request["run_dir_path"] / "hermes-run.json"
    started_at = utc_now().isoformat()
    stdout_text = ""
    stderr_text = ""
    exit_code: int | None = None
    launch_status = "failed"
    error_message: str | None = None
    lock_owner_payload: dict[str, Any] | None = None

    try:
        with local_model_runtime_lock(
            request["repo_root"],
            provider=request["provider"],
            model=request["model"],
            task_id=request["manifest"].get("task_id"),
            worker_id=request["hermes_profile"],
            operation="hermes-worker-runtime",
        ) as owner:
            lock_owner_payload = owner.model_dump()
            try:
                completed = subprocess.run(
                    request["command_preview"],
                    cwd=request["repo_root"],
                    capture_output=True,
                    text=True,
                    timeout=timeout_value,
                    check=False,
                )
                stdout_text = completed.stdout or ""
                stderr_text = completed.stderr or ""
                exit_code = int(completed.returncode)
                launch_status = "completed" if exit_code == 0 else "failed"
            except FileNotFoundError as exc:
                exit_code = 127
                error_message = str(exc)
                stderr_text = f"{exc}\n"
            except subprocess.TimeoutExpired as exc:
                exit_code = 124
                launch_status = "timeout"
                error_message = f"Hermes worker runtime timed out after {timeout_value}s"
                stdout_text = _timeout_output_text(exc.stdout)
                stderr_text = _timeout_output_text(exc.stderr) or f"{error_message}\n"
    except LocalModelRuntimeLockError as exc:
        raise HermesWorkerRuntimeError(str(exc)) from exc

    finished_at = utc_now().isoformat()
    atomic_write_text(stdout_path, stdout_text)
    atomic_write_text(stderr_path, stderr_text)
    payload = _base_payload(request, will_launch_hermes=True, dry_run=False) | {
        "launch_allowed": True,
        "launch_status": launch_status,
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": exit_code,
        "timeout_seconds": timeout_value,
        "stdout_path": relative_path(request["repo_root"], stdout_path),
        "stderr_path": relative_path(request["repo_root"], stderr_path),
        "hermes_run_path": relative_path(request["repo_root"], evidence_path),
        "runtime_lock": lock_owner_payload,
        "error": error_message,
        "verification_ran": False,
        "completion_verifier_path": relative_path(
            request["repo_root"], request["run_dir_path"] / "completion-verifier.py"
        ),
        "next_safe_action": "Run completion-verifier.py from the packet directory.",
    }
    atomic_write_text(evidence_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return payload


def _prepare_hermes_worker_runtime(
    root: Path,
    *,
    run_id: str,
    hermes_profile: str,
    force: bool,
    hermes_executable: str,
    require_launch_ready: bool,
) -> dict[str, Any]:
    repo_root = root.resolve()
    run_id_value = _required_text(run_id, "run_id")
    profile_value = _required_text(hermes_profile, "hermes_profile")
    executable_value = _required_text(hermes_executable, "hermes_executable")
    run_dir = serial_local_run_dir(repo_root, run_id_value)
    manifest_path = run_dir / "run.json"
    if not manifest_path.exists():
        raise HermesWorkerRuntimeError(f"serial local-agent run '{run_id_value}' was not found")

    manifest = _read_manifest(manifest_path, run_id_value)
    raw_artifacts = manifest.get("artifacts")
    artifacts: dict[str, Any] = raw_artifacts if isinstance(raw_artifacts, dict) else {}
    worker_packet_name = str(artifacts.get("worker_packet") or "worker-packet.md")
    worker_packet_path = run_dir / worker_packet_name
    if not worker_packet_path.exists():
        raise HermesWorkerRuntimeError(
            f"worker-packet.md is missing for serial local-agent run '{run_id_value}'"
        )

    raw_runtime = manifest.get("runtime")
    runtime: dict[str, Any] = raw_runtime if isinstance(raw_runtime, dict) else {}
    runtime_kind = str(runtime.get("kind") or "manual")
    packet_profile = runtime.get("hermes_profile")
    if runtime_kind == "hermes-profile":
        packet_profile_value = _required_text(packet_profile, "runtime.hermes_profile")
        if packet_profile_value != profile_value:
            raise HermesWorkerRuntimeError(
                f"requested profile '{profile_value}' does not match packet Hermes profile "
                f"'{packet_profile_value}'"
            )
    elif not force:
        raise HermesWorkerRuntimeError(
            f"serial local-agent run '{run_id_value}' has runtime '{runtime_kind}'; pass --force "
            "to preview a Hermes command anyway"
        )

    provider = _required_text(manifest.get("provider"), "provider")
    model = _required_text(manifest.get("model"), "model")
    current_preflight = build_serial_local_run_preflight(
        repo_root,
        provider=provider,
        model=model,
    )
    if require_launch_ready and not current_preflight.get("launch_packet_ready"):
        reason = str(current_preflight.get("reason") or "runtime preflight blocked launch")
        raise HermesWorkerRuntimeError(reason)

    packet_rel = relative_path(repo_root, worker_packet_path)
    manifest_rel = relative_path(repo_root, manifest_path)
    run_dir_rel = relative_path(repo_root, run_dir)
    prompt = _packet_prompt(packet_rel)
    if profile_value == "default":
        command_preview = [executable_value, "chat", "-q", prompt]
    else:
        command_preview = [executable_value, "-p", profile_value, "chat", "-q", prompt]

    return {
        "repo_root": repo_root,
        "run_dir_path": run_dir,
        "manifest": manifest,
        "provider": provider,
        "model": model,
        "run_id": str(manifest.get("run_id") or run_id_value),
        "run_dir": run_dir_rel,
        "run_manifest_path": manifest_rel,
        "packet_path": packet_rel,
        "hermes_profile": profile_value,
        "packet_hermes_profile": packet_profile,
        "runtime_kind": runtime_kind,
        "command_preview": command_preview,
        "preflight_state": current_preflight.get("state"),
        "preflight_reason": current_preflight.get("reason"),
        "preflight_lock_path": current_preflight.get("lock_path"),
        "force": bool(force),
        "workdir": repo_root.as_posix(),
    }


def _base_payload(
    request: dict[str, Any], *, will_launch_hermes: bool, dry_run: bool
) -> dict[str, Any]:
    return {
        "schema_version": HERMES_WORKER_RUNTIME_SCHEMA_VERSION,
        "will_launch_hermes": will_launch_hermes,
        "dry_run": dry_run,
        "run_id": request["run_id"],
        "run_dir": request["run_dir"],
        "run_manifest_path": request["run_manifest_path"],
        "packet_path": request["packet_path"],
        "hermes_profile": request["hermes_profile"],
        "packet_hermes_profile": request["packet_hermes_profile"],
        "runtime_kind": request["runtime_kind"],
        "command_preview": request["command_preview"],
        "preflight_state": request["preflight_state"],
        "preflight_reason": request["preflight_reason"],
        "preflight_lock_path": request["preflight_lock_path"],
        "force": request["force"],
        "workdir": request["workdir"],
    }


def _packet_prompt(packet_path: str) -> str:
    return (
        "You are running a DevFlow SerialLocalRun packet. "
        f"Read the packet at {packet_path} and follow it exactly. "
        "Do not stage, commit, push, promote, or edit outside the packet allowlist. "
        "When done, report changed files, verification output, risks, blockers, "
        "and whether any off-allowlist file was touched."
    )


def _read_manifest(path: Path, run_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HermesWorkerRuntimeError(
            f"run.json for serial local-agent run '{run_id}' is not valid JSON"
        ) from exc
    except OSError as exc:
        raise HermesWorkerRuntimeError(
            f"could not read run.json for serial local-agent run '{run_id}': {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise HermesWorkerRuntimeError(
            f"run.json for serial local-agent run '{run_id}' must contain a JSON object"
        )
    return payload


def _required_text(value: object, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise HermesWorkerRuntimeError(f"{field_name} is required")
    return text


def _positive_int(value: object, field_name: str) -> int:
    try:
        number = int(str(value))
    except (TypeError, ValueError) as exc:
        raise HermesWorkerRuntimeError(f"{field_name} must be a positive integer") from exc
    if number <= 0:
        raise HermesWorkerRuntimeError(f"{field_name} must be a positive integer")
    return number


def _timeout_output_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


__all__ = [
    "DEFAULT_HERMES_EXECUTABLE",
    "DEFAULT_HERMES_TIMEOUT_SECONDS",
    "HERMES_WORKER_RUNTIME_SCHEMA_VERSION",
    "HermesWorkerRuntimeError",
    "dry_run_hermes_worker_runtime",
    "run_hermes_worker_runtime",
]
