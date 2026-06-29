from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

from devflow.control_room.git_state import GitState, inspect_git_state
from devflow.control_room.hermes_profile_resolver import resolve_hermes_profile_for_historical_cleanup
from devflow.control_room.local_model_runtime_lock import (
    local_model_lock_dir,
    local_model_runtime_status,
)
from devflow.control_room.paths import devflow_dir, relative_path
from devflow.control_room.persistence import atomic_write_text, utc_now


SERIAL_LOCAL_AGENT_RUN_SCHEMA_VERSION = 1

SerialLocalRunPhase = Literal[
    "implementer",
    "verifier",
    "tiny_repair",
    "supervisor_final_gate",
]
SerialLocalRunRuntimeKind = Literal["manual", "hermes-profile"]

SERIAL_LOCAL_RUN_PHASES: tuple[str, ...] = (
    "implementer",
    "verifier",
    "tiny_repair",
    "supervisor_final_gate",
)
SERIAL_LOCAL_RUN_RUNTIME_KINDS: tuple[str, ...] = ("manual", "hermes-profile")
_RUNTIME_KIND_ALIASES: dict[str, str] = {
    "manual": "manual",
    "hermes-profile": "hermes-profile",
    "hermes_profile": "hermes-profile",
}

DEFAULT_NON_GOALS: tuple[str, ...] = (
    "no git stage/commit/push",
    "no broad refactor",
    "no off-allowlist edits",
    "no local model concurrency",
    "no local model launch from packet creation",
    "no promotion",
)


_COMPLETION_VERIFIER_SCRIPT = r'''#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def main() -> int:
    run_dir = Path(__file__).resolve().parent
    manifest = _read_json(run_dir / "run.json")
    repo_root = _repo_root(run_dir, manifest)
    allowed_files = [
        _normalize_path(value)
        for value in manifest.get("allowed_files", [])
        if str(value or "").strip()
    ]
    verification_commands = [
        str(item.get("command", "")).strip()
        for item in manifest.get("verification_commands", [])
        if isinstance(item, dict) and str(item.get("command", "")).strip()
    ]

    command_results: list[dict[str, Any]] = []
    status_snapshot = _git_status(repo_root)
    failure_class = _pre_command_failure(repo_root, status_snapshot, allowed_files)

    if failure_class is None:
        command_results = _run_verification_commands(repo_root, verification_commands)
        status_snapshot = _git_status(repo_root)
        failure_class = _post_command_failure(repo_root, status_snapshot, allowed_files, command_results)

    report = _build_report(
        manifest=manifest,
        run_dir=run_dir,
        repo_root=repo_root,
        status_snapshot=status_snapshot,
        allowed_files=allowed_files,
        command_results=command_results,
        failure_class=failure_class,
    )
    _write_report(run_dir / "verification-report.json", report)
    _emit_summary(report)
    return 0 if report["status"] == "PASS" else 1


def _repo_root(run_dir: Path, manifest: dict[str, Any]) -> Path:
    raw = ((manifest.get("git") or {}).get("repo_root") or "")
    if raw:
        return Path(raw).resolve()
    for candidate in (run_dir, *run_dir.parents):
        if (candidate / ".git").exists():
            return candidate.resolve()
    raise RuntimeError(f"unable to locate git repo root from {run_dir}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _git_status(repo_root: Path) -> dict[str, Any]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    changed: list[str] = []
    untracked: list[str] = []
    for raw_line in proc.stdout.splitlines():
        if len(raw_line) < 4:
            continue
        code = raw_line[:2]
        path = _status_path(raw_line)
        if _ignored_runtime_path(path):
            continue
        if code == "??":
            untracked.append(path)
        else:
            changed.append(path)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "changed_files": sorted(set(changed)),
        "untracked_files": sorted(set(untracked)),
    }


def _status_path(raw_line: str) -> str:
    value = raw_line[3:].strip()
    if " -> " in value:
        value = value.split(" -> ", 1)[1]
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return _normalize_path(value)


def _normalize_path(value: str) -> str:
    text = str(value or "").strip().replace("\\", "/")
    return text[2:] if text.startswith("./") else text


def _ignored_runtime_path(path: str) -> bool:
    return path == ".devflow" or path.startswith(".devflow/")


def _pre_command_failure(repo_root: Path, status_snapshot: dict[str, Any], allowed_files: list[str]) -> str | None:
    if _off_allowlist(status_snapshot, allowed_files):
        return "off_allowlist"
    if _diff_hygiene_issues(repo_root, status_snapshot, allowed_files):
        return "diff_hygiene"
    return None


def _post_command_failure(
    repo_root: Path,
    status_snapshot: dict[str, Any],
    allowed_files: list[str],
    command_results: list[dict[str, Any]],
) -> str | None:
    if _off_allowlist(status_snapshot, allowed_files):
        return "off_allowlist"
    if _diff_hygiene_issues(repo_root, status_snapshot, allowed_files):
        return "diff_hygiene"
    if any(result.get("returncode") == 127 for result in command_results):
        return "missing_command"
    if any(result.get("returncode") != 0 for result in command_results):
        return "test_failure"
    return None


def _run_verification_commands(repo_root: Path, commands: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, command in enumerate(commands, start=1):
        try:
            proc = subprocess.run(
                command,
                cwd=repo_root,
                shell=True,
                capture_output=True,
                text=True,
                check=False,
            )
            results.append(
                {
                    "order": index,
                    "command": command,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                }
            )
        except FileNotFoundError as exc:
            results.append(
                {
                    "order": index,
                    "command": command,
                    "returncode": 127,
                    "stdout": "",
                    "stderr": str(exc),
                }
            )
    return results


def _off_allowlist(status_snapshot: dict[str, Any], allowed_files: list[str]) -> list[str]:
    paths = [
        *status_snapshot.get("changed_files", []),
        *status_snapshot.get("untracked_files", []),
    ]
    return sorted(path for path in paths if not _path_allowed(path, allowed_files))


def _path_allowed(path: str, allowed_files: list[str]) -> bool:
    normalized = _normalize_path(path)
    for allowed in allowed_files:
        if allowed.endswith("/**") and normalized.startswith(allowed[:-3].rstrip("/") + "/"):
            return True
        if normalized == allowed:
            return True
    return False


def _diff_hygiene_issues(repo_root: Path, status_snapshot: dict[str, Any], allowed_files: list[str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    paths = sorted(set(status_snapshot.get("changed_files", []) + status_snapshot.get("untracked_files", [])))
    for rel_path in paths:
        if not _path_allowed(rel_path, allowed_files):
            continue
        path = repo_root / rel_path
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            issues.append({"path": rel_path, "line": None, "message": f"unable to read file: {exc}"})
            continue
        if data and not data.endswith(b"\n"):
            issues.append({"path": rel_path, "line": None, "message": "missing final newline"})
        for line_number, line in enumerate(data.splitlines(), start=1):
            if line.rstrip(b" \t") != line:
                issues.append({"path": rel_path, "line": line_number, "message": "trailing whitespace"})
    return issues


def _build_report(
    *,
    manifest: dict[str, Any],
    run_dir: Path,
    repo_root: Path,
    status_snapshot: dict[str, Any],
    allowed_files: list[str],
    command_results: list[dict[str, Any]],
    failure_class: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest.get("run_id"),
        "phase": manifest.get("phase"),
        "status": "FAIL" if failure_class else "PASS",
        "failure_class": failure_class,
        "repo_root": repo_root.as_posix(),
        "run_dir": run_dir.as_posix(),
        "allowed_files": allowed_files,
        "changed_files": status_snapshot.get("changed_files", []),
        "untracked_files": status_snapshot.get("untracked_files", []),
        "off_allowlist_files": _off_allowlist(status_snapshot, allowed_files),
        "diff_hygiene_issues": _diff_hygiene_issues(repo_root, status_snapshot, allowed_files),
        "commands": command_results,
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _emit_summary(report: dict[str, Any]) -> None:
    print(f"SERIAL_PHASE_VERIFY={report['status']}")
    print(f"failure_class={report['failure_class'] or 'none'}")
    print("changed_files=" + ",".join(report.get("changed_files", [])))
    print("untracked_files=" + ",".join(report.get("untracked_files", [])))


if __name__ == "__main__":
    raise SystemExit(main())
'''

class SerialLocalAgentRunError(ValueError):
    """Raised when a serial local-agent packet request is invalid."""


@dataclass(frozen=True)
class SerialLocalAgentRunResult:
    run_id: str
    run_dir: Path
    manifest: dict[str, Any]


def create_serial_local_agent_run(
    root: Path,
    *,
    phase: SerialLocalRunPhase | str,
    provider: str,
    model: str,
    allowed_files: Sequence[str],
    verification_commands: Sequence[str],
    mission: str | None = None,
    run_id: str | None = None,
    non_goals: Sequence[str] | None = None,
    task_id: str | None = None,
    worker_id: str | None = None,
    runtime_kind: SerialLocalRunRuntimeKind | str = "manual",
    hermes_profile: str | None = None,
    toolsets: Sequence[str] | None = None,
) -> SerialLocalAgentRunResult:
    """Write packet-only evidence for one serial local-agent phase.

    This function creates a durable run directory and packet artifacts only. It
    intentionally does not launch a model, mutate source files, stage/commit,
    push, verify, or promote.
    """

    repo_root = root.resolve()
    phase_value = _validate_phase(phase)
    provider_value = _required_text(provider, "provider")
    model_value = _required_text(model, "model")
    allowed = _normalize_required_list(allowed_files, "allowed_files", "path")
    commands = _normalize_required_list(verification_commands, "verification_commands", "command")
    goals = _normalize_non_goals(non_goals)
    mission_value = (mission or _default_mission(phase_value)).strip()
    runtime_payload = _runtime_payload(
        runtime_kind=runtime_kind,
        hermes_profile=hermes_profile,
        toolsets=toolsets,
    )

    run_id_value = _slug_run_id(run_id) if run_id else derive_serial_local_run_id(
        phase=phase_value,
        provider=provider_value,
        model=model_value,
        allowed_files=allowed,
        verification_commands=commands,
        runtime_kind=runtime_payload["kind"],
        hermes_profile=runtime_payload["hermes_profile"],
        toolsets=runtime_payload["toolsets"],
    )
    run_dir = serial_local_run_dir(repo_root, run_id_value)
    git_state = inspect_git_state(repo_root)
    created_at = utc_now().isoformat()

    verification_payload = _verification_payload(run_id_value, commands)
    preflight_payload = build_serial_local_run_preflight(
        repo_root,
        provider=provider_value,
        model=model_value,
        checked_at=created_at,
    )
    manifest = _run_manifest(
        root=repo_root,
        run_id=run_id_value,
        run_dir=run_dir,
        created_at=created_at,
        phase=phase_value,
        provider=provider_value,
        model=model_value,
        mission=mission_value,
        task_id=_optional_text(task_id),
        worker_id=_optional_text(worker_id),
        allowed_files=allowed,
        non_goals=goals,
        verification_payload=verification_payload,
        preflight_payload=preflight_payload,
        git_state=git_state,
        runtime_payload=runtime_payload,
    )

    atomic_write_text(run_dir / "run.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    atomic_write_text(run_dir / "preflight.json", json.dumps(preflight_payload, indent=2, sort_keys=True) + "\n")
    atomic_write_text(run_dir / "worker-packet.md", _render_worker_packet(manifest))
    atomic_write_text(run_dir / "completion-verifier.py", _render_completion_verifier_script())
    atomic_write_text(run_dir / "allowlist.txt", "".join(f"{path}\n" for path in allowed))
    atomic_write_text(run_dir / "non-goals.txt", "".join(f"{item}\n" for item in goals))
    atomic_write_text(
        run_dir / "verification-commands.json",
        json.dumps(verification_payload, indent=2, sort_keys=True) + "\n",
    )

    return SerialLocalAgentRunResult(run_id=run_id_value, run_dir=run_dir, manifest=manifest)


def local_agent_runs_dir(root: Path) -> Path:
    return devflow_dir(root.resolve()) / "local-agent-runs"


def serial_local_run_dir(root: Path, run_id: str) -> Path:
    return local_agent_runs_dir(root) / _slug_run_id(run_id)


def serial_local_agent_run_snapshot(root: Path) -> dict[str, Any]:
    """Return read-only snapshot data for serial local-agent run evidence."""

    repo_root = root.resolve()
    base = local_agent_runs_dir(repo_root)
    if not base.exists():
        return _empty_serial_local_run_snapshot()

    runs: list[dict[str, Any]] = []
    for run_dir in sorted(path for path in base.iterdir() if path.is_dir()):
        manifest = _read_json_file(run_dir / "run.json")
        if not manifest:
            continue
        runs.append(_serial_local_run_summary(repo_root, run_dir, manifest))

    if not runs:
        return _empty_serial_local_run_snapshot()

    runs.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("run_id") or "")), reverse=True)
    latest = runs[0]
    run_state = latest["state"]
    verification_status = latest["verification_status"]
    status_source = (
        "verification_report"
        if verification_status != "not_run"
        else "hermes_run"
        if latest.get("hermes_run")
        else "run_manifest"
    )
    return {
        "schema_version": SERIAL_LOCAL_AGENT_RUN_SCHEMA_VERSION,
        "status": verification_status if verification_status != "not_run" else run_state,
        "run_state": run_state,
        "verification_status": verification_status,
        "status_source": status_source,
        "runtime_kind": latest.get("runtime_kind"),
        "hermes_profile": latest.get("hermes_profile"),
        "launch_status": latest.get("launch_status"),
        "exit_code": latest.get("exit_code"),
        "read_only": True,
        "latest_run": latest,
        "run_count": len(runs),
        "runs": runs[:5],
        "browser_actions": [],
        "next_safe_action": _serial_local_run_next_safe_action(latest),
    }


def _empty_serial_local_run_snapshot() -> dict[str, Any]:
    return {
        "schema_version": SERIAL_LOCAL_AGENT_RUN_SCHEMA_VERSION,
        "status": "none",
        "run_state": "none",
        "verification_status": "not_run",
        "status_source": "none",
        "runtime_kind": None,
        "hermes_profile": None,
        "launch_status": "not_started",
        "exit_code": None,
        "read_only": True,
        "latest_run": None,
        "run_count": 0,
        "runs": [],
        "browser_actions": [],
        "next_safe_action": "Create a packet with devflow agent serial-packet before launching a local worker.",
    }


def _serial_local_run_summary(root: Path, run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    report_path = run_dir / "verification-report.json"
    report = _read_json_file(report_path) if report_path.exists() else None
    verification_status = "not_run"
    failure_class = None
    if report:
        raw_status = str(report.get("status") or "").strip().lower()
        verification_status = raw_status if raw_status in {"pass", "fail"} else "unknown"
        failure_class = report.get("failure_class")

    artifacts = manifest.get("artifacts") or {}
    raw_runtime = manifest.get("runtime")
    runtime: dict[str, Any] = raw_runtime if isinstance(raw_runtime, dict) else _manual_runtime_payload()
    launch = _serial_local_run_launch_summary(root, run_dir)
    run_state = _serial_local_run_state(
        str(manifest.get("state") or "unknown"),
        launch,
    )
    evidence_names = [
        artifacts.get("run_manifest") or "run.json",
        artifacts.get("worker_packet") or "worker-packet.md",
        artifacts.get("preflight") or "preflight.json",
        artifacts.get("completion_verifier") or "completion-verifier.py",
    ]
    evidence_paths = [relative_path(root, run_dir / name) for name in evidence_names if name]
    if launch["hermes_run"]:
        evidence_paths.append(str(launch["hermes_run"]))
    for key in ("stdout_path", "stderr_path"):
        value = launch.get(key)
        if value:
            evidence_paths.append(str(value))
    if report_path.exists():
        evidence_paths.append(relative_path(root, report_path))

    raw_toolsets = runtime.get("toolsets")
    toolsets = [str(item) for item in raw_toolsets] if isinstance(raw_toolsets, list) else []
    return {
        "run_id": manifest.get("run_id") or run_dir.name,
        "created_at": manifest.get("created_at"),
        "phase": manifest.get("phase"),
        "state": run_state,
        "manifest_state": manifest.get("state") or "unknown",
        "provider": manifest.get("provider"),
        "model": manifest.get("model"),
        "mission": manifest.get("mission") or "",
        "run_dir": relative_path(root, run_dir),
        "runtime_kind": runtime.get("kind") or "manual",
        "hermes_profile": runtime.get("hermes_profile"),
        "toolsets": toolsets,
        "allowed_file_count": len(manifest.get("allowed_files") or []),
        "verification_command_count": len(manifest.get("verification_commands") or []),
        "verification_status": verification_status,
        "failure_class": failure_class,
        "verification_report": relative_path(root, report_path) if report_path.exists() else None,
        "launch_status": launch["launch_status"],
        "exit_code": launch["exit_code"],
        "hermes_run": launch["hermes_run"],
        "stdout_path": launch["stdout_path"],
        "stderr_path": launch["stderr_path"],
        "verification_ran": launch["verification_ran"],
        "preflight": manifest.get("preflight") or {},
        "safety": manifest.get("safety") or {},
        "evidence_paths": evidence_paths,
        "read_only": True,
    }


def _serial_local_run_launch_summary(root: Path, run_dir: Path) -> dict[str, Any]:
    evidence_path = run_dir / "hermes-run.json"
    payload = _read_json_file(evidence_path) if evidence_path.exists() else {}
    if not evidence_path.exists():
        return {
            "launch_status": "not_started",
            "exit_code": None,
            "hermes_run": None,
            "stdout_path": None,
            "stderr_path": None,
            "verification_ran": False,
        }

    launch_status = str(payload.get("launch_status") or "launched").strip().lower() or "launched"
    return {
        "launch_status": launch_status,
        "exit_code": _optional_int(payload.get("exit_code")),
        "hermes_run": _launch_evidence_path(root, run_dir, evidence_path, payload.get("hermes_run_path")),
        "stdout_path": _launch_evidence_path(root, run_dir, run_dir / "hermes-stdout.txt", payload.get("stdout_path")),
        "stderr_path": _launch_evidence_path(root, run_dir, run_dir / "hermes-stderr.txt", payload.get("stderr_path")),
        "verification_ran": bool(payload.get("verification_ran")),
    }


def _serial_local_run_state(manifest_state: str, launch: dict[str, Any]) -> str:
    launch_status = str(launch.get("launch_status") or "not_started")
    if launch_status == "not_started":
        return manifest_state
    exit_code = launch.get("exit_code")
    if launch_status == "completed" and exit_code == 0:
        return "ready_for_verifier"
    if launch_status in {"failed", "timeout"} or (exit_code is not None and exit_code != 0):
        return "failed"
    return "launched"


def _serial_local_run_next_safe_action(latest: dict[str, Any]) -> str:
    verification_status = latest.get("verification_status")
    if verification_status == "pass":
        return "Review verification-report.json and continue to the next DevFlow gate."
    if verification_status in {"fail", "unknown"}:
        return "Inspect verification-report.json, repair within the allowlist, then rerun completion-verifier.py."
    run_state = latest.get("state")
    if run_state == "ready_for_verifier":
        return "Run completion-verifier.py from the packet directory."
    if run_state == "failed":
        return "Inspect Hermes launch stdout/stderr, repair the packet or runtime, then rerun Hermes manually."
    if run_state == "launched":
        return "Inspect hermes-run.json and launch stdout/stderr before running completion-verifier.py."
    return "Review worker-packet.md, launch manually outside the browser, then run completion-verifier.py."


def _launch_evidence_path(root: Path, run_dir: Path, fallback_path: Path, value: object) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return relative_path(root, fallback_path)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_serial_local_run_preflight(
    root: Path,
    *,
    provider: str,
    model: str,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Project same-provider/model runtime lock state into packet readiness."""

    repo_root = root.resolve()
    provider_value = _required_text(provider, "provider")
    model_value = _required_text(model, "model")
    status = local_model_runtime_status(repo_root, provider=provider_value, model=model_value)
    fallback_lock_path = relative_path(
        repo_root,
        local_model_lock_dir(repo_root, provider_value, model_value),
    )
    if status is None:
        return {
            "schema_version": SERIAL_LOCAL_AGENT_RUN_SCHEMA_VERSION,
            "checked_at": checked_at or utc_now().isoformat(),
            "provider": provider_value,
            "model": model_value,
            "state": "free",
            "launch_packet_ready": True,
            "reason": "local model runtime is free",
            "lock_path": fallback_lock_path,
            "owner": None,
        }

    owner = status.model_dump()
    state = status.state
    reason = (
        "local model runtime is already running"
        if state == "running"
        else "stale local model runtime lock requires explicit cleanup"
    )
    return {
        "schema_version": SERIAL_LOCAL_AGENT_RUN_SCHEMA_VERSION,
        "checked_at": checked_at or utc_now().isoformat(),
        "provider": provider_value,
        "model": model_value,
        "state": state,
        "launch_packet_ready": False,
        "reason": reason,
        "lock_path": status.lock_path,
        "owner": owner,
    }


def derive_serial_local_run_id(
    *,
    phase: SerialLocalRunPhase | str,
    provider: str,
    model: str,
    allowed_files: Sequence[str],
    verification_commands: Sequence[str],
    runtime_kind: SerialLocalRunRuntimeKind | str = "manual",
    hermes_profile: str | None = None,
    toolsets: Sequence[str] | None = None,
) -> str:
    phase_value = _validate_phase(phase)
    provider_value = _required_text(provider, "provider")
    model_value = _required_text(model, "model")
    allowed = _normalize_required_list(allowed_files, "allowed_files", "path")
    commands = _normalize_required_list(verification_commands, "verification_commands", "command")
    runtime_payload = _runtime_payload(
        runtime_kind=runtime_kind,
        hermes_profile=hermes_profile,
        toolsets=toolsets,
    )
    fingerprint_payload = {
        "phase": phase_value,
        "provider": provider_value,
        "model": model_value,
        "allowed_files": allowed,
        "verification_commands": commands,
    }
    if runtime_payload != _manual_runtime_payload():
        fingerprint_payload["runtime"] = runtime_payload
    digest = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:12]
    return "-".join(
        part
        for part in (
            "slr",
            _slug_run_id(phase_value),
            _slug_run_id(provider_value),
            _slug_run_id(model_value),
            digest,
        )
        if part
    )


def _run_manifest(
    *,
    root: Path,
    run_id: str,
    run_dir: Path,
    created_at: str,
    phase: str,
    provider: str,
    model: str,
    mission: str,
    task_id: str | None,
    worker_id: str | None,
    allowed_files: list[str],
    non_goals: list[str],
    verification_payload: dict[str, Any],
    preflight_payload: dict[str, Any],
    git_state: GitState,
    runtime_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SERIAL_LOCAL_AGENT_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": created_at,
        "phase": phase,
        "state": "pending",
        "provider": provider,
        "model": model,
        "task_id": task_id,
        "worker_id": worker_id,
        "mission": mission,
        "allowed_files": allowed_files,
        "non_goals": non_goals,
        "verification_commands": verification_payload["commands"],
        "runtime": runtime_payload,
        "preflight": preflight_payload,
        "git": _git_payload(git_state),
        "artifacts": {
            "run_manifest": "run.json",
            "worker_packet": "worker-packet.md",
            "allowlist": "allowlist.txt",
            "completion_verifier": "completion-verifier.py",
            "non_goals": "non-goals.txt",
            "preflight": "preflight.json",
            "verification_commands": "verification-commands.json",
        },
        "run_dir": relative_path(root, run_dir),
        "safety": {
            "packet_only": True,
            "model_launch": False,
            "git_mutation": False,
            "promotion": False,
        },
    }


def _git_payload(git_state: GitState) -> dict[str, Any]:
    return {
        "is_repo": git_state.is_repo,
        "repo_root": git_state.repo_root,
        "baseline": {
            "branch": git_state.branch,
            "head_sha": git_state.head_sha,
            "origin_main_sha": git_state.origin_main_sha,
        },
        "dirty_state": {
            "dirty": git_state.dirty,
            "staged_count": git_state.counts.staged,
            "unstaged_count": git_state.counts.unstaged,
            "untracked_count": git_state.counts.untracked,
            "conflicted_files": list(git_state.conflicted_files),
            "operation_in_progress": git_state.operation_in_progress,
        },
    }


def _verification_payload(run_id: str, commands: Sequence[str]) -> dict[str, Any]:
    return {
        "schema_version": SERIAL_LOCAL_AGENT_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "commands": [
            {"order": index + 1, "command": command}
            for index, command in enumerate(commands)
        ],
    }


def _render_completion_verifier_script() -> str:
    return _COMPLETION_VERIFIER_SCRIPT


def _render_worker_packet(manifest: dict[str, Any]) -> str:
    allowed = "\n".join(f"- {path}" for path in manifest["allowed_files"])
    non_goals = "\n".join(f"- {item}" for item in manifest["non_goals"])
    commands = "\n".join(command["command"] for command in manifest["verification_commands"])
    runtime = manifest.get("runtime") or _manual_runtime_payload()
    runtime_kind = str(runtime.get("kind") or "manual")
    hermes_profile = runtime.get("hermes_profile")
    toolsets = runtime.get("toolsets") or []
    toolsets_text = "`, `".join(str(item) for item in toolsets) if toolsets else "none"
    git = manifest["git"]
    baseline = git["baseline"]
    dirty = git["dirty_state"]
    if runtime_kind == "hermes-profile":
        runtime_note = (
            f"This packet is intended for Hermes profile `{hermes_profile}`, "
            "but packet creation did not launch it.\n"
        )
    else:
        runtime_note = "Packet creation did not launch Hermes, a local model, or a worker.\n"
    return (
        f"# Serial Local-Agent Packet: {manifest['phase']}\n\n"
        f"Run ID: `{manifest['run_id']}`\n"
        f"State: `{manifest['state']}`\n"
        f"Provider/model: `{manifest['provider']}/{manifest['model']}`\n\n"
        "## Runtime Target\n"
        f"- runtime kind: `{runtime_kind}`\n"
        f"- hermes profile: `{hermes_profile or 'none'}`\n"
        f"- toolsets: `{toolsets_text}`\n"
        f"{runtime_note}\n"
        "## Mission\n"
        f"{manifest['mission']}\n\n"
        "## Baseline\n"
        f"- branch: `{baseline['branch'] or 'unknown'}`\n"
        f"- HEAD: `{baseline['head_sha'] or 'unknown'}`\n"
        f"- origin/main: `{baseline['origin_main_sha'] or 'unknown'}`\n"
        f"- dirty: `{dirty['dirty']}` "
        f"(staged={dirty['staged_count']}, unstaged={dirty['unstaged_count']}, "
        f"untracked={dirty['untracked_count']})\n\n"
        "## Runtime Preflight\n"
        f"- state: `{manifest['preflight']['state']}`\n"
        f"- launch_packet_ready: `{manifest['preflight']['launch_packet_ready']}`\n"
        f"- reason: {manifest['preflight']['reason']}\n"
        f"- lock: `{manifest['preflight']['lock_path']}`\n\n"
        "## Allowed Files\n"
        f"{allowed}\n\n"
        "## Non-Goals\n"
        f"{non_goals}\n\n"
        "## Verification Commands\n"
        "```bash\n"
        f"{commands}\n"
        "```\n\n"
        "## Output Required\n"
        "- changed files\n"
        "- self-checks / verification output\n"
        "- risks and blockers\n"
        "- whether any off-allowlist file was touched\n\n"
        "## Safety Boundary\n"
        "Packet creation is evidence-only. Do not launch Hermes, a local model, a worker, "
        "stage, commit, push, promote, or edit outside the allowed files from this packet.\n"
    )


def _manual_runtime_payload() -> dict[str, Any]:
    return {
        "kind": "manual",
        "hermes_profile": None,
        "toolsets": [],
        "packet_only": True,
    }


def _runtime_payload(
    *,
    runtime_kind: SerialLocalRunRuntimeKind | str,
    hermes_profile: str | None,
    toolsets: Sequence[str] | None,
) -> dict[str, Any]:
    kind = _validate_runtime_kind(runtime_kind)
    profile = _optional_text(hermes_profile)
    toolset_values = _normalize_optional_list(toolsets, "toolsets", "toolset")
    if kind == "hermes-profile":
        if not profile:
            raise SerialLocalAgentRunError(
                "hermes_profile is required when runtime_kind is hermes-profile"
            )
        profile = _canonical_hermes_profile(profile)
    else:
        if profile:
            raise SerialLocalAgentRunError(
                "hermes_profile requires runtime_kind hermes-profile"
            )
        if toolset_values:
            raise SerialLocalAgentRunError(
                "toolsets require runtime_kind hermes-profile"
            )
    return {
        "kind": kind,
        "hermes_profile": profile if kind == "hermes-profile" else None,
        "toolsets": toolset_values,
        "packet_only": True,
    }


def _canonical_hermes_profile(profile_id: str) -> str:
    if str(profile_id or "").strip() == "default":
        return "default"
    profile = resolve_hermes_profile_for_historical_cleanup(profile_id)
    if profile is None:
        raise SerialLocalAgentRunError(
            f"hermes_profile must be a canonical Hermes profile id: {profile_id}"
        )
    return profile.hermes_profile


def _validate_runtime_kind(runtime_kind: SerialLocalRunRuntimeKind | str) -> str:
    value = str(runtime_kind or "").strip()
    normalized = _RUNTIME_KIND_ALIASES.get(value)
    if normalized is None:
        raise SerialLocalAgentRunError(
            f"runtime_kind must be one of: {', '.join(SERIAL_LOCAL_RUN_RUNTIME_KINDS)}"
        )
    return normalized


def _normalize_optional_list(
    values: Sequence[str] | None, field_name: str, item_name: str
) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            raise SerialLocalAgentRunError(f"{field_name} entries must be non-empty {item_name}s")
        normalized.append(text)
    return normalized


def _validate_phase(phase: SerialLocalRunPhase | str) -> str:
    value = str(phase or "").strip()
    if value not in SERIAL_LOCAL_RUN_PHASES:
        raise SerialLocalAgentRunError(
            f"phase must be one of: {', '.join(SERIAL_LOCAL_RUN_PHASES)}"
        )
    return value


def _required_text(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SerialLocalAgentRunError(f"{field_name} is required")
    return text


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_required_list(values: Sequence[str], field_name: str, item_name: str) -> list[str]:
    normalized: list[str] = []
    for value in values:
        text = str(value or "").strip().replace("\\", "/")
        if not text:
            continue
        if item_name == "path":
            _validate_allowed_path(text, field_name)
        normalized.append(text)
    if not normalized:
        noun = "path" if item_name == "path" else "command"
        raise SerialLocalAgentRunError(f"{field_name} must contain at least one {noun}")
    return normalized


def _normalize_non_goals(non_goals: Sequence[str] | None) -> list[str]:
    values = non_goals if non_goals is not None else DEFAULT_NON_GOALS
    normalized = [str(value).strip() for value in values if str(value or "").strip()]
    return normalized or list(DEFAULT_NON_GOALS)


def _validate_allowed_path(value: str, field_name: str) -> None:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise SerialLocalAgentRunError(f"{field_name} entries must be repo-relative paths")


def _default_mission(phase: str) -> str:
    return f"Run the {phase} phase of the serial local-agent pipeline against the allowed files only."


def _slug_run_id(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(value or "").lower()).strip("-")
    if not text:
        raise SerialLocalAgentRunError("run_id is required")
    return text


__all__ = [
    "DEFAULT_NON_GOALS",
    "SERIAL_LOCAL_AGENT_RUN_SCHEMA_VERSION",
    "SERIAL_LOCAL_RUN_PHASES",
    "SerialLocalAgentRunError",
    "SerialLocalAgentRunResult",
    "SerialLocalRunRuntimeKind",
    "build_serial_local_run_preflight",
    "create_serial_local_agent_run",
    "derive_serial_local_run_id",
    "local_agent_runs_dir",
    "serial_local_agent_run_snapshot",
    "serial_local_run_dir",
]
