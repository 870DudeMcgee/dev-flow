from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
from typing import Any, Literal

import yaml

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
    "gemma-reviewer": LocalWorkerDefinition(
        name="gemma-reviewer",
        model="gemma4:latest",
        role="reviewer / summarizer / handoff compressor",
        default_timeout_seconds=600,
        default_input_worker="qwen-planner",
    ),
}


def get_local_worker_definition(worker_name: str) -> LocalWorkerDefinition:
    try:
        return LOCAL_WORKERS[worker_name]
    except KeyError as exc:
        available = ", ".join(sorted(LOCAL_WORKERS))
        raise ValueError(f"Unknown local worker '{worker_name}'. Available local workers: {available}.") from exc


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
    definition = get_local_worker_definition(worker_name)
    timeout = timeout_seconds or definition.default_timeout_seconds
    command = ["ollama", "run", definition.model]
    artifact_dir = workspace / "local-workers" / worker_name
    artifact_dir.mkdir(parents=True, exist_ok=True)

    prompt_path = artifact_dir / "prompt.md"
    raw_response_path = artifact_dir / "response.raw.md"
    response_path = artifact_dir / "response.md"
    run_json_path = artifact_dir / "run.json"
    stderr_path = artifact_dir / "stderr.log"

    started_at = _utc_now()
    monotonic_started_at = time.monotonic()

    selected_input_worker = input_worker or definition.default_input_worker
    input_worker_output_path: Path | None = None
    input_worker_output: str | None = None
    if definition.name == "gemma-reviewer":
        if not selected_input_worker:
            selected_input_worker = "qwen-planner"
        input_worker_output_path = workspace / "local-workers" / selected_input_worker / "response.md"
        if not input_worker_output_path.exists():
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
                error_message=error_message,
            )
        input_worker_output = input_worker_output_path.read_text(encoding="utf-8")

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

    try:
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
        error_message = f"Local worker '{worker_name}' exited with {exit_code}."
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
    task_data = _safe_yaml_mapping(raw_task_yaml)
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
        "- Dev-Flow is a local-first control room, not the coding intelligence itself.",
        "- Dev-Flow owns task state, isolated workspaces, logs, verification evidence, and human-controlled promotion.",
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
            raw_task_yaml.rstrip(),
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
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": duration_seconds,
        "timeout_seconds": timeout_seconds,
        "exit_code": exit_code,
        "status": status,
        "prompt_path": relative_path(root, prompt_path),
        "raw_response_path": relative_path(root, raw_response_path),
        "response_path": relative_path(root, response_path),
        "stderr_path": relative_path(root, stderr_path),
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
    skipped_names = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    for path in sorted(base.rglob("*")):
        try:
            relative_parts = path.relative_to(base).parts
        except ValueError:
            continue
        if any(part in skipped_names for part in relative_parts):
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