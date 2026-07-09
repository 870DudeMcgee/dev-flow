from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path

from devflow.legacy.control_room.local_ollama_worker import find_latest_worker_evidence
from devflow.legacy.control_room.models import TaskRecord
from devflow.legacy.control_room.paths import relative_path, task_dir
from devflow.legacy.control_room.service import get_task
from devflow.legacy.control_room.task_workspace import runtime_workspace_path


class TaskEvidenceSummaryError(Exception):
    """User-facing task evidence summary error."""


@dataclass(frozen=True)
class TaskEvidenceVerification:
    status: str
    command: str | None = None
    exit_code: int | None = None


@dataclass(frozen=True)
class TaskEvidenceWorkerRun:
    name: str
    model: str
    status: str
    duration: float
    response_path: str


@dataclass(frozen=True)
class LocalTaskEvidenceWorkerSummary:
    worker_name: str
    run_id: str
    status: str
    exit_code: str
    model: str
    evidence_path: str
    response_path: str
    completed_at: str
    reviewed_worker: str | None = None
    reviewed_source: str | None = None


@dataclass(frozen=True)
class TaskEvidenceSummary:
    task_id: str
    local: bool
    workspace: Path
    task: TaskRecord | None = None
    verification: TaskEvidenceVerification | None = None
    worker_runs: list[TaskEvidenceWorkerRun] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommended_next_action: str | None = None
    suggested_next_commands: list[str] = field(default_factory=list)
    local_worker_summaries: list[LocalTaskEvidenceWorkerSummary] = field(default_factory=list)
    local_recommendations: list[str] = field(default_factory=list)


_ARTIFACT_PATTERNS = (
    "local-workers/*/response.md",
    "local-workers/*/response.raw.md",
    "*response.md",
    "*review.md",
    "*.md",
    "*.txt",
    "logs/*.log",
    "*.log",
)

_LOCAL_WORKER_DISPLAY_ORDER = (
    "qwen-planner",
    "qwopus-implementer",
    "qwen-implementer",
    "gemma-reviewer",
)


def build_task_evidence_summary(root: Path, task_id: str, local: bool = False) -> TaskEvidenceSummary:
    """Build a read-only summary for `devflow task evidence`."""
    try:
        task = get_task(root, task_id)
    except KeyError as exc:
        raise TaskEvidenceSummaryError(f"Task '{task_id}' not found.") from exc

    workspace = runtime_workspace_path(root, task)
    if not workspace.exists() or not workspace.is_dir():
        raise TaskEvidenceSummaryError(f"Task workspace not found at {workspace}")

    if local:
        summaries = _collect_local_worker_summaries(root, workspace)
        return TaskEvidenceSummary(
            task_id=task.id,
            local=True,
            task=task,
            workspace=workspace,
            local_worker_summaries=summaries,
            local_recommendations=(
                _local_evidence_recommendations(summaries)
                if summaries
                else ["No local AI evidence found."]
            ),
        )

    verification = _verification_status(root, task)
    worker_runs, failed_workers, timeout_workers, missing_inputs = _worker_runs(workspace)
    artifacts = _artifact_paths(root, workspace)
    warnings = _warnings(
        verification.status,
        failed_workers=failed_workers,
        timeout_workers=timeout_workers,
        missing_inputs=missing_inputs,
    )
    return TaskEvidenceSummary(
        task_id=task.id,
        local=False,
        task=task,
        workspace=workspace,
        verification=verification,
        worker_runs=worker_runs,
        artifacts=artifacts,
        warnings=warnings,
        recommended_next_action=_recommended_next_action(task.id, verification.status, worker_runs),
        suggested_next_commands=_suggested_next_commands(task.id, verification.status, worker_runs),
    )


def render_task_evidence_summary(summary: TaskEvidenceSummary) -> list[str]:
    """Render a task evidence summary as terminal lines."""
    if summary.local:
        return _render_local_summary(summary)
    return _render_task_summary(summary)


def _render_task_summary(summary: TaskEvidenceSummary) -> list[str]:
    if summary.task is None or summary.verification is None:
        return []

    lines = [
        f"Task: {summary.task.id} {summary.task.title}",
        f"Status: {summary.task.status}",
        "",
        "Verification:",
    ]

    verification = summary.verification
    if verification.status == "passed":
        lines.append(f"  passed  {verification.command or ''}")
    elif verification.status == "failed":
        exit_suffix = f" (exit={verification.exit_code})" if verification.exit_code is not None else ""
        lines.append(f"  failed{exit_suffix}  {verification.command or ''}")
    else:
        lines.append("  not_run")
    lines.append("")

    if summary.worker_runs:
        lines.append("Local workers:")
        for run in summary.worker_runs:
            resp_name = Path(run.response_path).name
            duration_str = f"{int(round(run.duration))}s"
            lines.append(f"  {run.name:<16}  {run.status:<8}  {duration_str:>4}  {resp_name}")
        lines.append("")

    if summary.artifacts:
        lines.append("Artifacts:")
        lines.extend(f"  {artifact}" for artifact in summary.artifacts[:10])
        lines.append("")

    if summary.warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {warning}" for warning in summary.warnings)
        lines.append("")

    lines.extend(
        [
            "Recommended next action:",
            f"  {summary.recommended_next_action or ''}",
            "",
            "Suggested next commands:",
        ]
    )
    lines.extend(f"  {command}" for command in summary.suggested_next_commands)
    return lines


def _render_local_summary(summary: TaskEvidenceSummary) -> list[str]:
    lines = [f"Local runs for {summary.task_id}", ""]

    if not summary.local_worker_summaries:
        lines.extend(
            [
                "No local AI evidence found.",
                "",
                "Recommendation:",
                "  No local AI evidence found.",
            ]
        )
        return lines

    for worker_summary in summary.local_worker_summaries:
        lines.extend(
            [
                worker_summary.worker_name,
                f"  latest run: {worker_summary.run_id}",
                f"  status: {worker_summary.status}",
                f"  exit code: {worker_summary.exit_code}",
                f"  model: {worker_summary.model}",
                f"  evidence: {worker_summary.evidence_path}",
                f"  response: {worker_summary.response_path}",
                f"  completed: {worker_summary.completed_at}",
            ]
        )
        if worker_summary.reviewed_worker:
            reviewed = worker_summary.reviewed_worker
            if worker_summary.reviewed_source:
                reviewed = f"{reviewed} ({worker_summary.reviewed_source})"
            lines.append(f"  reviewed: {reviewed}")
        lines.append("")

    lines.append("Recommendation:")
    lines.extend(f"  {line}" for line in summary.local_recommendations)
    return lines


def _verification_status(root: Path, task: TaskRecord) -> TaskEvidenceVerification:
    status = task.verification_status or "not_run"
    command = task.verification_command
    exit_code = task.verification_exit_code

    verification_path = task_dir(root, task.id) / "verification.json"
    data = _read_json_mapping(verification_path)
    if data.get("task_id") == task.id:
        raw_status = data.get("status")
        raw_command = data.get("command")
        raw_exit_code = data.get("exit_code")
        status = raw_status if isinstance(raw_status, str) else status
        command = raw_command if isinstance(raw_command, str) else command
        exit_code = raw_exit_code if isinstance(raw_exit_code, int) else exit_code

    return TaskEvidenceVerification(status=status, command=command, exit_code=exit_code)


def _worker_runs(workspace: Path) -> tuple[list[TaskEvidenceWorkerRun], list[str], list[str], list[str]]:
    local_workers_dir = workspace / "local-workers"
    worker_runs: list[TaskEvidenceWorkerRun] = []
    failed_workers: list[str] = []
    timeout_workers: list[str] = []
    missing_inputs: list[str] = []

    if not local_workers_dir.exists() or not local_workers_dir.is_dir():
        return worker_runs, failed_workers, timeout_workers, missing_inputs

    for worker_subdir in sorted(local_workers_dir.iterdir()):
        if not worker_subdir.is_dir():
            continue
        run_data = _read_json_mapping(worker_subdir / "run.json")
        if not run_data:
            continue

        worker_name = _string_metadata(run_data, "worker_name", worker_subdir.name)
        model = _string_metadata(run_data, "model")
        status = _string_metadata(run_data, "status")
        duration = _float_metadata(run_data, "duration_seconds")
        response_path = _string_metadata(run_data, "response_path", f"local-workers/{worker_subdir.name}/response.md")
        worker_runs.append(
            TaskEvidenceWorkerRun(
                name=worker_name,
                model=model,
                status=status,
                duration=duration,
                response_path=response_path,
            )
        )

        if status == "failed":
            failed_workers.append(worker_name)
        elif status == "timeout":
            timeout_workers.append(worker_name)

        error_message = run_data.get("error_message") or ""
        if isinstance(error_message, str) and "Missing input worker output" in error_message:
            missing_inputs.append(worker_name)

    return worker_runs, failed_workers, timeout_workers, missing_inputs


def _artifact_paths(root: Path, workspace: Path) -> list[str]:
    all_candidate_files: list[Path] = []
    for path in workspace.rglob("*"):
        if not path.is_file():
            continue
        try:
            path.resolve().relative_to(workspace)
        except ValueError:
            continue
        all_candidate_files.append(path)

    valid_candidates: list[Path] = []
    for candidate in sorted(all_candidate_files, key=lambda path: _artifact_sort_key(workspace, path)):
        if _artifact_sort_key(workspace, candidate)[0] < len(_ARTIFACT_PATTERNS):
            valid_candidates.append(candidate)
    return [relative_path(root, candidate) for candidate in valid_candidates]


def _artifact_sort_key(workspace: Path, path: Path) -> tuple[int, str]:
    rel_path = path.relative_to(workspace).as_posix()
    rel_path_lower = rel_path.lower()
    name = path.name.lower()

    for idx, pattern in enumerate(_ARTIFACT_PATTERNS):
        if fnmatch.fnmatch(rel_path_lower, pattern) or fnmatch.fnmatch(name, pattern):
            return (idx, rel_path_lower)
    return (len(_ARTIFACT_PATTERNS), rel_path_lower)


def _warnings(
    verification_status: str,
    *,
    failed_workers: list[str],
    timeout_workers: list[str],
    missing_inputs: list[str],
) -> list[str]:
    warnings: list[str] = []
    warnings.extend(f"failed worker run: {worker}" for worker in failed_workers)
    warnings.extend(f"timeout worker run: {worker}" for worker in timeout_workers)
    warnings.extend(f"missing input-worker output for: {worker}" for worker in missing_inputs)
    if verification_status != "passed":
        warnings.append("unverified task")
    return warnings


def _recommended_next_action(task_id: str, verification_status: str, worker_runs: list[TaskEvidenceWorkerRun]) -> str:
    if verification_status == "passed":
        if any(run.name == "gemma-reviewer" and run.status == "success" for run in worker_runs):
            return "review gemma-reviewer response, then handoff to Codex"
        return f"review promotion preview, then run 'devflow task promote {task_id}'"
    if verification_status == "failed":
        return f"fix the failure and re-run verification using 'devflow task verify {task_id} -- <command>'"
    return f"verify the task using 'devflow task verify {task_id} -- <command>'"


def _suggested_next_commands(
    task_id: str,
    verification_status: str,
    worker_runs: list[TaskEvidenceWorkerRun],
) -> list[str]:
    commands = [f"devflow task open {task_id}"]
    if worker_runs:
        commands.append(f"devflow task open {task_id} --worker {worker_runs[-1].name}")
    if verification_status != "passed":
        commands.append(f"devflow task verify {task_id} -- <command>")
    else:
        commands.append(f"devflow task promote-preview {task_id}")
    return commands


def _collect_local_worker_summaries(root: Path, workspace: Path) -> list[LocalTaskEvidenceWorkerSummary]:
    local_workers_dir = workspace / "local-workers"
    if not local_workers_dir.exists() or not local_workers_dir.is_dir():
        return []

    try:
        worker_names = sorted(
            {child.name for child in local_workers_dir.iterdir() if child.is_dir()},
            key=_local_worker_sort_key,
        )
    except OSError:
        return []

    summaries: list[LocalTaskEvidenceWorkerSummary] = []
    for worker_name in worker_names:
        evidence_dir, response_path = find_latest_worker_evidence(workspace, worker_name)
        if evidence_dir is None or response_path is None:
            continue

        run_data = _read_json_mapping(evidence_dir / "run.json")
        reviewed_worker, reviewed_source = _reviewed_input_from_metadata(evidence_dir, run_data)
        summaries.append(
            LocalTaskEvidenceWorkerSummary(
                worker_name=_string_metadata(run_data, "worker_name", worker_name),
                run_id=_local_run_id(evidence_dir, run_data),
                status=_string_metadata(run_data, "status"),
                exit_code=_exit_code_metadata(run_data),
                model=_string_metadata(run_data, "model"),
                evidence_path=_metadata_path(root, workspace, run_data.get("evidence_path"), evidence_dir),
                response_path=_metadata_path(root, workspace, run_data.get("response_path"), response_path),
                completed_at=_completion_metadata(run_data),
                reviewed_worker=reviewed_worker,
                reviewed_source=reviewed_source,
            )
        )

    return summaries


def _local_worker_sort_key(worker_name: str) -> tuple[int, str]:
    try:
        return (_LOCAL_WORKER_DISPLAY_ORDER.index(worker_name), "")
    except ValueError:
        return (len(_LOCAL_WORKER_DISPLAY_ORDER), worker_name)


def _read_json_mapping(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _string_metadata(run_data: dict[str, object], key: str, default: str = "unknown") -> str:
    value = run_data.get(key)
    return value if isinstance(value, str) and value else default


def _float_metadata(run_data: dict[str, object], key: str, default: float = 0.0) -> float:
    value = run_data.get(key)
    if isinstance(value, int | float):
        return float(value)
    return default


def _exit_code_metadata(run_data: dict[str, object]) -> str:
    if "exit_code" not in run_data:
        return "unknown"
    value = run_data.get("exit_code")
    return "none" if value is None else str(value)


def _completion_metadata(run_data: dict[str, object]) -> str:
    for key in ("completed_at", "finished_at"):
        value = run_data.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _local_run_id(evidence_dir: Path, run_data: dict[str, object]) -> str:
    run_id = run_data.get("run_id")
    if isinstance(run_id, str) and run_id:
        return run_id
    if evidence_dir.name.startswith("run_"):
        return evidence_dir.name
    return "legacy"


def _metadata_path(root: Path, workspace: Path, value: object, fallback: Path) -> str:
    if isinstance(value, str) and value.strip():
        raw_path = value.strip()
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            if raw_path.startswith("local-workers/"):
                candidate = workspace / candidate
            else:
                candidate = root / candidate
        return relative_path(root, candidate)
    return relative_path(root, fallback)


def _reviewed_input_from_metadata(evidence_dir: Path, run_data: dict[str, object]) -> tuple[str | None, str | None]:
    reviewed_worker = _first_string_metadata(run_data, ("reviewed_worker", "input_worker"))
    reviewed_source = _first_string_metadata(
        run_data,
        ("reviewed_response_path", "input_response_path", "input_worker_output_path"),
    )
    if reviewed_worker and reviewed_source:
        return reviewed_worker, reviewed_source

    prompt_worker, prompt_source = _reviewed_input_from_prompt(evidence_dir / "prompt.md")
    return reviewed_worker or prompt_worker, reviewed_source or prompt_source


def _first_string_metadata(run_data: dict[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = run_data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _reviewed_input_from_prompt(prompt_path: Path) -> tuple[str | None, str | None]:
    if not prompt_path.exists():
        return None, None

    reviewed_worker: str | None = None
    reviewed_source: str | None = None
    try:
        with prompt_path.open("r", encoding="utf-8") as prompt_file:
            for _ in range(200):
                line = prompt_file.readline()
                if not line:
                    break
                stripped = line.strip()
                if not reviewed_worker and stripped.startswith("Input worker:"):
                    reviewed_worker = stripped.split(":", 1)[1].strip() or None
                elif not reviewed_source and stripped.startswith("Source:"):
                    reviewed_source = stripped.split(":", 1)[1].strip() or None
                if reviewed_worker and reviewed_source:
                    break
    except OSError:
        return None, None
    return reviewed_worker, reviewed_source


def _local_evidence_recommendations(summaries: list[LocalTaskEvidenceWorkerSummary]) -> list[str]:
    worker_names = {summary.worker_name for summary in summaries}
    successful_workers = {
        summary.worker_name
        for summary in summaries
        if summary.status == "success"
    }

    if "qwopus-implementer" in successful_workers and "gemma-reviewer" in successful_workers:
        lead = (
            "Legacy local advisory implementation + review evidence available; "
            "canonical patch evidence still comes from task run --worker qwopus-implementer."
        )
    elif worker_names == {"qwen-planner"}:
        lead = "Planning advisory evidence exists; canonical implementation patch evidence is missing."
    else:
        lead = (
            "Use local advisory evidence for scouting/review; "
            "apply only proposal.patch from task run --worker qwopus-implementer."
        )

    if lead.startswith("Use local advisory evidence"):
        return [lead]
    return [
        lead,
        (
            "Use local advisory evidence for scouting/review; "
            "apply only proposal.patch from task run --worker qwopus-implementer."
        ),
    ]
