from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from typing import Any, Literal

import yaml

from devflow.control_room.log_sanitizer import DEFAULT_LATEST_LOG_LINE_MAX_CHARS, sanitize_log_line
from devflow.control_room.local_model_runtime_lock import LocalModelRuntimeLockError, local_model_runtime_lock
from devflow.control_room.persistence import atomic_write_text
from devflow.control_room.paths import relative_path, task_dir


RunStatus = Literal["success", "failed", "timeout"]


@dataclass(frozen=True)
class LocalWorkerDefinition:
    name: str
    model: str
    role: str
    default_timeout_seconds: int
    default_input_worker: str | None = None


@dataclass(frozen=True)
class LocalOllamaRunResult:
    task_id: str
    worker_name: str
    model: str
    command: list[str]
    status: RunStatus
    exit_code: int | None
    timeout_seconds: int
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    artifact_dir: Path
    prompt_path: Path
    raw_response_path: Path
    response_path: Path
    run_json_path: Path
    stderr_path: Path
    run_id: str
    error_message: str | None = None

    @property
    def task_status(self) -> Literal["complete", "worker_failed", "timeout"]:
        if self.status == "success":
            return "complete"
        if self.status == "timeout":
            return "timeout"
        return "worker_failed"


LOCAL_WORKERS: dict[str, LocalWorkerDefinition] = {
    "qwen-planner": LocalWorkerDefinition(
        name="qwen-planner",
        model="qwen3.6:latest",
        role="coding planner / implementation scout",
        default_timeout_seconds=600,
    ),
    "qwopus-implementer": LocalWorkerDefinition(
        name="qwopus-implementer",
        model="qwopus:latest",
        role="legacy advisory implementation scout; canonical patch worker is task run --worker qwopus-implementer",
        default_timeout_seconds=600,
        default_input_worker="qwen-planner",
    ),
    "qwen-implementer": LocalWorkerDefinition(
        name="qwen-implementer",
        model="qwen3.6:latest",
        role="legacy advisory implementation scout / patch draft generator",
        default_timeout_seconds=600,
        default_input_worker="qwen-planner",
    ),
    "gemma-reviewer": LocalWorkerDefinition(
        name="gemma-reviewer",
        model="gemma4:latest",
        role="reviewer / summarizer / handoff compressor",
        default_timeout_seconds=600,
        default_input_worker="qwopus-implementer",
    ),
}


def get_local_worker_definition(worker_name: str) -> LocalWorkerDefinition:
    try:
        return LOCAL_WORKERS[worker_name]
    except KeyError as exc:
        available = ", ".join(sorted(LOCAL_WORKERS))
        raise ValueError(f"Unknown local worker '{worker_name}'. Available local workers: {available}.") from exc


def find_latest_worker_evidence(workspace: Path, worker_name: str) -> tuple[Path | None, Path | None]:
    """
    Finds the latest run directory and response.md path for a given worker.
    Returns (run_dir, response_path).
    Supports new run ID folders and falls back to legacy flat folder if no run subfolders exist.
    """
    worker_dir = workspace / "local-workers" / worker_name
    if not worker_dir.exists():
        return None, None

    # Find run subdirectories (e.g. run_*)
    run_dirs = []
    try:
        for child in worker_dir.iterdir():
            if child.is_dir() and child.name.startswith("run_"):
                response_file = child / "response.md"
                run_json_file = child / "run.json"
                if response_file.exists() and run_json_file.exists():
                    run_dirs.append(child)
    except OSError:
        pass

    if run_dirs:
        # Sort by run.json modification time for absolute chronological order
        run_dirs.sort(key=lambda d: (d / "run.json").stat().st_mtime)
        latest_run_dir = run_dirs[-1]
        return latest_run_dir, latest_run_dir / "response.md"

    # Legacy fallback
    legacy_response = worker_dir / "response.md"
    if legacy_response.exists():
        return worker_dir, legacy_response

    return None, None


def run_local_ollama_worker(
    root: Path,
    task_id: str,
    workspace: Path,
    worker_name: str,
    *,
    input_worker: str | None = None,
    timeout_seconds: int | None = None,
    task_yaml_text: str | None = None,
) -> LocalOllamaRunResult:
    import os
    definition = get_local_worker_definition(worker_name)
    timeout = timeout_seconds or definition.default_timeout_seconds
    command = ["ollama", "run", definition.model]

    started_at = _utc_now()
    monotonic_started_at = time.monotonic()

    run_id = f"run_{started_at.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    artifact_dir = workspace / "local-workers" / worker_name / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = artifact_dir / "prompt.md"
    raw_response_path = artifact_dir / "response.raw.md"
    response_path = artifact_dir / "response.md"
    run_json_path = artifact_dir / "run.json"
    stderr_path = artifact_dir / "stderr.log"

    selected_input_worker = input_worker or definition.default_input_worker
    input_worker_output_path: Path | None = None
    input_worker_output: str | None = None

    if definition.name == "gemma-reviewer" and not input_worker:
        # Dynamic fallback: try qwopus-implementer, then qwen-implementer, then qwen-planner
        _, qwopus_response_path = find_latest_worker_evidence(workspace, "qwopus-implementer")
        if qwopus_response_path:
            selected_input_worker = "qwopus-implementer"
        else:
            _, qwen_response_path = find_latest_worker_evidence(workspace, "qwen-implementer")
            if qwen_response_path:
                selected_input_worker = "qwen-implementer"
            else:
                selected_input_worker = "qwen-planner"

    if selected_input_worker:
        _, found_response_path = find_latest_worker_evidence(workspace, selected_input_worker)
        if found_response_path:
            input_worker_output_path = found_response_path
            input_worker_output = found_response_path.read_text(encoding="utf-8")
        else:
            # Construct a theoretical/fallback path for legacy error reporting (so tests match exactly)
            input_worker_output_path = workspace / "local-workers" / selected_input_worker / "response.md"
            error_message = (
                "Missing input worker output: "
                f"{relative_path(root, input_worker_output_path)}. "
                f"Run 'devflow task local {task_id} --worker {selected_input_worker}' first."
            )
            prompt = _compose_prompt(
                root,
                task_id,
                workspace,
                definition,
                task_yaml_text=task_yaml_text,
                selected_input_worker=selected_input_worker,
                input_worker_output=None,
                input_worker_output_path=input_worker_output_path,
                missing_input_message=error_message,
            )
            atomic_write_text(prompt_path, prompt)
            atomic_write_text(raw_response_path, "")
            atomic_write_text(response_path, "")
            atomic_write_text(stderr_path, error_message + "\n")
            return _write_run_result(
                root,
                task_id,
                definition,
                command,
                "failed",
                1,
                timeout,
                started_at,
                monotonic_started_at,
                artifact_dir,
                prompt_path,
                raw_response_path,
                response_path,
                run_json_path,
                stderr_path,
                run_id,
                error_message=error_message,
            )

    prompt = _compose_prompt(
        root,
        task_id,
        workspace,
        definition,
        task_yaml_text=task_yaml_text,
        selected_input_worker=selected_input_worker,
        input_worker_output=input_worker_output,
        input_worker_output_path=input_worker_output_path,
    )
    atomic_write_text(prompt_path, prompt)

    lock_error_message: str | None = None
    try:
        with local_model_runtime_lock(
            root,
            provider="ollama",
            model=definition.model,
            task_id=task_id,
            worker_id=worker_name,
            operation="local-ollama-worker",
        ):
            completed = subprocess.run(
                command,
                cwd=workspace,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        stdout = _coerce_text(completed.stdout)
        stderr = _coerce_text(completed.stderr)
        exit_code = completed.returncode
        status: RunStatus = "success" if exit_code == 0 else "failed"
    except LocalModelRuntimeLockError as exc:
        lock_error_message = str(exc)
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}\n"
        exit_code = 1
        status = "failed"
    except subprocess.TimeoutExpired as exc:
        stdout = _coerce_text(exc.stdout or exc.output)
        stderr = _coerce_text(exc.stderr)
        exit_code = None
        status = "timeout"
    except OSError as exc:
        stdout = ""
        stderr = f"{type(exc).__name__}: {exc}\n"
        exit_code = 1
        status = "failed"

    atomic_write_text(raw_response_path, stdout)
    atomic_write_text(response_path, stdout)
    atomic_write_text(stderr_path, stderr)
    error_message = None
    if status == "failed":
        error_message = lock_error_message or f"Local worker '{worker_name}' exited with {exit_code}."
    elif status == "timeout":
        error_message = f"Local worker '{worker_name}' timed out after {timeout} seconds."

    return _write_run_result(
        root,
        task_id,
        definition,
        command,
        status,
        exit_code,
        timeout,
        started_at,
        monotonic_started_at,
        artifact_dir,
        prompt_path,
        raw_response_path,
        response_path,
        run_json_path,
        stderr_path,
        run_id,
        error_message=error_message,
    )


def _compose_prompt(
    root: Path,
    task_id: str,
    workspace: Path,
    definition: LocalWorkerDefinition,
    *,
    task_yaml_text: str | None = None,
    selected_input_worker: str | None = None,
    input_worker_output: str | None = None,
    input_worker_output_path: Path | None = None,
    missing_input_message: str | None = None,
) -> str:
    task_path = task_dir(root, task_id)
    task_yaml_path = task_path / "task.yaml"
    raw_task_yaml = task_yaml_text
    if raw_task_yaml is None:
        raw_task_yaml = task_yaml_path.read_text(encoding="utf-8") if task_yaml_path.exists() else ""
    prompt_task_yaml = _sanitize_task_yaml_for_prompt(raw_task_yaml)
    task_data = _safe_yaml_mapping(prompt_task_yaml)
    context_listing = _file_listing(task_path, root=root)
    workspace_listing = _file_listing(workspace, root=workspace)

    lines = [
        "# Dev-Flow Local Worker Prompt",
        "",
        f"Worker: {definition.name}",
        f"Model: {definition.model}",
        f"Role: {definition.role}",
        "",
        "## Dev-Flow rules",
        "- DevFlow is the local operating layer, not the coding intelligence itself.",
        "- DevFlow owns bounded product-building state, evidence, verification, and human-controlled next decisions.",
        "- Keep output in the task workspace under local-workers/<worker-name>/.",
        "- Keep task.yaml as canonical state.",
        "- Use existing task lifecycle evidence; do not invent a new event or agent framework.",
        "- Do not add remote provider adapters.",
        "- Do not add autonomous routing.",
        "- Do not add a dashboard.",
        "- Do not auto-edit repo files from model output.",
        "- Do not auto-commit.",
        "- Do not auto-merge.",
        "- Treat model output as advisory evidence, not truth.",
        "",
        "## Task summary",
        f"task_id: {task_id}",
    ]
    for key in ("title", "description", "status"):
        value = task_data.get(key)
        if value is not None:
            lines.append(f"{key}: {value}")

    lines.extend(
        [
            "",
            "## task.yaml",
            "```yaml",
            prompt_task_yaml.rstrip(),
            "```",
            "",
            "## Workspace file listing",
            *workspace_listing,
            "",
            "## Task context artifact listing",
            *context_listing,
            "",
        ]
    )

    if missing_input_message:
        lines.extend(["## Missing input", missing_input_message, ""])

    if selected_input_worker is not None:
        lines.extend(
            [
                "## Input worker output",
                f"Input worker: {selected_input_worker}",
                f"Source: {relative_path(root, input_worker_output_path) if input_worker_output_path else ''}",
                "",
                input_worker_output or "",
                "",
            ]
        )

    if definition.name == "qwen-planner":
        lines.extend(
            [
                "## Response request",
                "Please respond with:",
                "1. Understanding",
                "2. Smallest safe implementation slice",
                "3. Files likely involved",
                "4. Step-by-step plan",
                "5. Risks / ambiguity / missing context",
                "6. Verification commands",
                "7. Clean Codex/Antigravity prompt if useful",
            ]
        )
    elif definition.name == "qwopus-implementer":
        lines.extend(
            [
                "## Response request",
                "Please respond with:",
                "1. Brief task understanding",
                "2. Relevant files likely to change",
                "3. Proposed implementation approach",
                "4. Unified diff of proposed changes if enough context is present",
                "5. Changed-file summary",
                "6. Focused pytest commands to run for verification",
                "7. Risks and assumptions",
                "8. Explicit reminder that this output is advisory evidence only and must not be applied automatically",
            ]
        )
    elif definition.name == "qwen-implementer":
        lines.extend(
            [
                "## Response request",
                "Please respond with:",
                "1. Unified diff or patch proposal of proposed changes",
                "2. Detailed explanation of changes",
                "3. Targeted test plan or focused pytest commands",
            ]
        )
    elif definition.name == "gemma-reviewer":
        lines.extend(
            [
                "## Response request",
                "Please respond with:",
                "1. Verdict",
                "2. Useful parts to keep",
                "3. Parts to reject or defer",
                "4. Risks / gaps",
                "5. Smallest next implementation slice",
                "6. Clean implementation prompt",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _sanitize_task_yaml_for_prompt(raw_task_yaml: str) -> str:
    lines = []
    for line in raw_task_yaml.splitlines():
        if line.startswith("latest_log_line:"):
            lines.append(_sanitize_latest_log_line_yaml(line))
        else:
            lines.append(line)
    return "\n".join(lines)


def _sanitize_latest_log_line_yaml(line: str) -> str:
    _, raw_value = line.split(":", 1)
    try:
        value = yaml.safe_load(raw_value.strip())
    except yaml.YAMLError:
        value = raw_value.strip()
    if value is None:
        return "latest_log_line: null"
    sanitized = sanitize_log_line(str(value), max_chars=DEFAULT_LATEST_LOG_LINE_MAX_CHARS)
    if not sanitized:
        return "latest_log_line: null"
    return f"latest_log_line: {json.dumps(sanitized)}"


def _write_run_result(
    root: Path,
    task_id: str,
    definition: LocalWorkerDefinition,
    command: list[str],
    status: RunStatus,
    exit_code: int | None,
    timeout_seconds: int,
    started_at: datetime,
    monotonic_started_at: float,
    artifact_dir: Path,
    prompt_path: Path,
    raw_response_path: Path,
    response_path: Path,
    run_json_path: Path,
    stderr_path: Path,
    run_id: str,
    *,
    error_message: str | None = None,
) -> LocalOllamaRunResult:
    finished_at = _utc_now()
    duration_seconds = round(time.monotonic() - monotonic_started_at, 3)
    payload: dict[str, Any] = {
        "task_id": task_id,
        "worker_name": definition.name,
        "model": definition.model,
        "command": command,
        "role": definition.role,
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "completed_at": finished_at.isoformat(),
        "duration_seconds": duration_seconds,
        "timeout_seconds": timeout_seconds,
        "exit_code": exit_code,
        "status": status,
        "prompt_path": relative_path(root, prompt_path),
        "raw_response_path": relative_path(root, raw_response_path),
        "response_path": relative_path(root, response_path),
        "stderr_path": relative_path(root, stderr_path),
        "evidence_path": relative_path(root, artifact_dir),
    }
    if error_message is not None:
        payload["error_message"] = error_message
    atomic_write_text(run_json_path, json.dumps(payload, indent=2) + "\n")
    return LocalOllamaRunResult(
        task_id=task_id,
        worker_name=definition.name,
        model=definition.model,
        command=command,
        status=status,
        exit_code=exit_code,
        timeout_seconds=timeout_seconds,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        artifact_dir=artifact_dir,
        prompt_path=prompt_path,
        raw_response_path=raw_response_path,
        response_path=response_path,
        run_json_path=run_json_path,
        stderr_path=stderr_path,
        run_id=run_id,
        error_message=error_message,
    )


def _safe_yaml_mapping(raw_yaml: str) -> dict[str, Any]:
    if not raw_yaml.strip():
        return {}
    loaded = yaml.safe_load(raw_yaml)
    if isinstance(loaded, dict):
        return loaded
    return {}


def _file_listing(base: Path, *, root: Path, limit: int = 200) -> list[str]:
    if not base.exists():
        return ["- missing"]
    paths: list[str] = []
    skipped_names = {
        ".git",
        ".devflow",
        "node_modules",
        "dist",
        "build",
        "coverage",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
    for path in sorted(base.rglob("*")):
        try:
            relative_parts = path.relative_to(base).parts
        except ValueError:
            continue
        if any(part in skipped_names or part.startswith(".venv") for part in relative_parts):
            continue
        if path.is_file():
            paths.append(f"- {relative_path(root, path)}")
        if len(paths) >= limit:
            paths.append(f"- ... truncated after {limit} files")
            break
    return paths or ["- none"]


def _coerce_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
