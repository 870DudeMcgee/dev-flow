from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from devflow.control_room.freshness import FreshnessReport, run_freshness_loop
from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.goal_loop import GoalLoopLane
from devflow.control_room.parallel_task_creation import ParallelTaskCreationRun, run_parallel_task_creation_batch
from devflow.control_room.parallel_verification import ParallelVerificationRun, run_parallel_verification_batch
from devflow.control_room.parallel_worker import ParallelWorkerRun, run_parallel_worker_batch
from devflow.control_room.paths import devflow_dir, relative_path, task_dir
from devflow.control_room.persistence import atomic_write_text, get_task, list_tasks
from devflow.control_room.promotion import main_checkout_has_uncommitted_changes
from devflow.control_room.question_resume import build_question_snapshot
from devflow.control_room.service import preview_task_promotion, promote_task


LOOP_SCHEMA_VERSION = 1
LOOP_TEMPLATE_GOAL_AUTOPILOT = "goal-autopilot"
ALLOWED_LOOP_TEMPLATES = {LOOP_TEMPLATE_GOAL_AUTOPILOT}
ALLOWED_LOOP_ACTIONS = {
    "create_tasks",
    "run_shell_workers",
    "run_verification",
    "promotion_preview",
    "promote",
}
DEFAULT_GOAL_AUTOPILOT_ACTIONS = [
    "create_tasks",
    "run_shell_workers",
    "run_verification",
    "promotion_preview",
    "promote",
]


LoopRunStatus = Literal[
    "completed",
    "max_iterations",
    "no_progress",
    "open_questions",
    "blocked",
    "unsafe_git_state",
    "worker_permission_required",
    "verification_permission_required",
    "worker_failed",
    "verification_failed",
    "promotion_preview_failed",
    "promotion_blocked",
]


class LoopConfigError(ValueError):
    pass


class LoopRunError(ValueError):
    pass


class LoopPolicy(BaseModel):
    max_iterations: int = 3
    max_parallel: int = 2
    worker_timeout_seconds: int = 120
    no_progress_limit: int = 2
    allow_promotion: bool = False
    allow_high_risk: bool = False
    stop_on_open_questions: bool = True
    stop_on_blockers: bool = True


class LoopDefinition(BaseModel):
    schema_version: int = LOOP_SCHEMA_VERSION
    loop_id: str
    template: str = LOOP_TEMPLATE_GOAL_AUTOPILOT
    source: str = "active_goals"
    actions: list[str] = Field(default_factory=lambda: list(DEFAULT_GOAL_AUTOPILOT_ACTIONS))
    policy: LoopPolicy = Field(default_factory=LoopPolicy)


class LoopPromotionPreviewResult(BaseModel):
    task_id: str
    status: str
    added: list[str] = Field(default_factory=list)
    modified: list[str] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)
    reason: str | None = None


class LoopPromotionResult(BaseModel):
    task_id: str
    status: str
    reason: str | None = None


class LoopIteration(BaseModel):
    iteration: int
    freshness_status: str
    state_hash: str
    action: str
    stop_reason: str | None = None
    next_safe_action: str
    task_creation_run: ParallelTaskCreationRun | None = None
    worker_run: ParallelWorkerRun | None = None
    verification_run: ParallelVerificationRun | None = None
    promotion_previews: list[LoopPromotionPreviewResult] = Field(default_factory=list)
    promotions: list[LoopPromotionResult] = Field(default_factory=list)


class LoopRun(BaseModel):
    schema_version: int = 1
    loop_id: str
    run_id: str
    status: LoopRunStatus
    max_iterations: int
    max_parallel: int
    worker_timeout_seconds: int
    allow_workers: bool
    allow_verify: bool
    allow_promote: bool
    started_at: str
    finished_at: str
    iterations_completed: int
    tasks_created: int = 0
    workers_run: int = 0
    verification_results: dict[str, int] = Field(default_factory=lambda: {"passed": 0, "failed": 0})
    promotion_previews_completed: int = 0
    promotions_completed: int = 0
    stop_reason: str
    next_safe_action: str
    evidence_path: str | None = None
    iterations: list[LoopIteration] = Field(default_factory=list)


class _StopSignal(BaseModel):
    status: LoopRunStatus
    stop_reason: str
    next_safe_action: str


class _PromotionCandidate(BaseModel):
    goal_id: str
    lane_id: str
    task_id: str
    risk: str
    promotion_allowed: bool
    high_risk: bool


def init_loop_definition(root: Path, loop_id: str, *, template: str) -> LoopDefinition:
    if template not in ALLOWED_LOOP_TEMPLATES:
        raise LoopConfigError(f"Unknown loop template: {template}")
    definition = LoopDefinition(loop_id=loop_id, template=template)
    path = loop_config_path(root, loop_id)
    if path.exists():
        raise LoopConfigError(f"Loop already exists: {loop_id}")
    atomic_write_text(path, yaml.safe_dump(definition.model_dump(mode="json"), sort_keys=False))
    return definition


def list_loop_ids(root: Path) -> list[str]:
    directory = loops_dir(root)
    if not directory.exists():
        return []
    return sorted(
        path.name
        for path in directory.iterdir()
        if path.is_dir() and (path / "loop.yaml").exists()
    )


def load_loop_definition(root: Path, loop_id: str) -> LoopDefinition:
    path = loop_config_path(root, loop_id)
    if not path.exists():
        raise LoopConfigError(f"Loop not found: {loop_id}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise LoopConfigError(f"Loop config is malformed YAML: {relative_path(root, path)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise LoopConfigError(f"Loop config must be a mapping: {relative_path(root, path)}")
    try:
        definition = LoopDefinition.model_validate(payload)
    except Exception as exc:
        raise LoopConfigError(f"Loop config is invalid: {exc}") from exc
    _validate_loop_definition(definition)
    return definition


def render_loop_definition(definition: LoopDefinition) -> str:
    lines = [
        f"loop_id: {definition.loop_id}",
        f"template: {definition.template}",
        f"source: {definition.source}",
        "actions:",
    ]
    lines.extend(f"  - {action}" for action in definition.actions)
    lines.extend(
        [
            "policy:",
            f"  max_iterations: {definition.policy.max_iterations}",
            f"  max_parallel: {definition.policy.max_parallel}",
            f"  worker_timeout_seconds: {definition.policy.worker_timeout_seconds}",
            f"  no_progress_limit: {definition.policy.no_progress_limit}",
            f"  allow_promotion: {_yes_no(definition.policy.allow_promotion)}",
            f"  allow_high_risk: {_yes_no(definition.policy.allow_high_risk)}",
            f"  stop_on_open_questions: {_yes_no(definition.policy.stop_on_open_questions)}",
            f"  stop_on_blockers: {_yes_no(definition.policy.stop_on_blockers)}",
        ]
    )
    return "\n".join(lines) + "\n"


def run_loop(
    root: Path,
    loop_id: str,
    *,
    max_iterations: int | None = None,
    max_parallel: int | None = None,
    worker_timeout_seconds: int | None = None,
    allow_workers: bool = False,
    allow_verify: bool = False,
    allow_promote: bool = False,
    write_evidence: bool = True,
) -> LoopRun:
    definition = load_loop_definition(root, loop_id)
    policy = definition.policy
    iterations_limit = max_iterations if max_iterations is not None else policy.max_iterations
    parallel_limit = max_parallel if max_parallel is not None else policy.max_parallel
    timeout_limit = worker_timeout_seconds if worker_timeout_seconds is not None else policy.worker_timeout_seconds
    _validate_run_controls(iterations_limit, parallel_limit, timeout_limit, policy.no_progress_limit)

    started_at = _now()
    run = LoopRun(
        loop_id=loop_id,
        run_id=_run_id(loop_id, started_at),
        status="max_iterations",
        max_iterations=iterations_limit,
        max_parallel=parallel_limit,
        worker_timeout_seconds=timeout_limit,
        allow_workers=allow_workers,
        allow_verify=allow_verify,
        allow_promote=allow_promote,
        started_at=started_at,
        finished_at=started_at,
        iterations_completed=0,
        stop_reason="max_iterations",
        next_safe_action=f"devflow loop run {loop_id} --max-iterations {iterations_limit}",
    )

    previous_hash: str | None = None
    repeated_hash_count = 0

    for iteration_number in range(1, iterations_limit + 1):
        preflight = _preflight_stop(root, definition)
        if preflight is not None:
            return _finish(root, run, preflight, write_evidence=write_evidence)

        report = run_freshness_loop(root, write_snapshot=True)
        blocked = _blocked_goal_stop(definition, report)
        if blocked is not None:
            iteration = _iteration(iteration_number, report, action="stop", signal=blocked)
            run.iterations.append(iteration)
            return _finish(root, run, blocked, write_evidence=write_evidence)

        creation_batch = _first_parallel_batch(report)
        if creation_batch is not None and "create_tasks" in definition.actions:
            creation_run = run_parallel_task_creation_batch(
                root,
                creation_batch.goal_id,
                creation_batch.batch,
                write_report=True,
            )
            run.tasks_created += creation_run.created_task_count
            run.iterations.append(
                _iteration(
                    iteration_number,
                    report,
                    action="create_tasks",
                    task_creation_run=creation_run,
                )
            )
            previous_hash = None
            repeated_hash_count = 0
            continue

        worker_batch = _first_worker_batch(root, report)
        if worker_batch is not None and "run_shell_workers" in definition.actions:
            if not allow_workers:
                signal = _signal(
                    "worker_permission_required",
                    "allow_workers_flag_required",
                    f"devflow loop run {loop_id} --allow-workers",
                )
                run.iterations.append(_iteration(iteration_number, report, action="stop", signal=signal))
                return _finish(root, run, signal, write_evidence=write_evidence)
            worker_run = run_parallel_worker_batch(
                root,
                worker_batch,
                max_parallel=parallel_limit,
                timeout_seconds=timeout_limit,
                write_report=True,
            )
            run.workers_run += worker_run.task_count
            run.iterations.append(
                _iteration(
                    iteration_number,
                    report,
                    action="run_shell_workers",
                    worker_run=worker_run,
                )
            )
            if worker_run.status == "failed":
                signal = _signal(
                    "worker_failed",
                    "worker_failed",
                    "Inspect failed task worker logs, repair the workspace, then rerun the loop.",
                )
                return _finish(root, run, signal, write_evidence=write_evidence)
            previous_hash = None
            repeated_hash_count = 0
            continue

        verification_batch = _first_verification_batch(root, report)
        if verification_batch is not None and "run_verification" in definition.actions:
            if not allow_verify:
                signal = _signal(
                    "verification_permission_required",
                    "allow_verify_flag_required",
                    f"devflow loop run {loop_id} --allow-verify",
                )
                run.iterations.append(_iteration(iteration_number, report, action="stop", signal=signal))
                return _finish(root, run, signal, write_evidence=write_evidence)
            verification_run = run_parallel_verification_batch(
                root,
                verification_batch,
                max_parallel=parallel_limit,
                timeout_seconds=timeout_limit,
                write_report=True,
            )
            _accumulate_verification(run, verification_run)
            run.iterations.append(
                _iteration(
                    iteration_number,
                    report,
                    action="run_verification",
                    verification_run=verification_run,
                )
            )
            if verification_run.status == "failed":
                signal = _signal(
                    "verification_failed",
                    "verification_failed",
                    "Inspect failed task verification logs, repair the workspace, then rerun the loop.",
                )
                return _finish(root, run, signal, write_evidence=write_evidence)
            previous_hash = None
            repeated_hash_count = 0
            continue

        promotion_candidates = _promotion_candidates(root, report)
        if promotion_candidates:
            signal, preview, promotion = _handle_promotion_candidate(
                root,
                definition,
                promotion_candidates[0],
                allow_promote=allow_promote,
            )
            previews = [preview] if preview is not None else []
            promotions = [promotion] if promotion is not None else []
            if preview is not None and preview.status == "clean":
                run.promotion_previews_completed += 1
            if promotion is not None and promotion.status == "promoted":
                run.promotions_completed += 1
            run.iterations.append(
                _iteration(
                    iteration_number,
                    report,
                    action="promote",
                    signal=signal if signal.status != "completed" else None,
                    promotion_previews=previews,
                    promotions=promotions,
                )
            )
            if signal.status != "completed":
                return _finish(root, run, signal, write_evidence=write_evidence)
            previous_hash = None
            repeated_hash_count = 0
            continue

        if _did_mutating_work(run) and _no_projected_work(report):
            signal = _signal("completed", "no_projected_work", report.next_action)
            run.iterations.append(_iteration(iteration_number, report, action="complete", signal=signal))
            return _finish(root, run, signal, write_evidence=write_evidence)

        if previous_hash == report.state_hash:
            repeated_hash_count += 1
        else:
            repeated_hash_count = 1
        previous_hash = report.state_hash
        run.iterations.append(_iteration(iteration_number, report, action="observe"))

        if repeated_hash_count >= policy.no_progress_limit:
            signal = _signal("no_progress", "repeated_state_hash", report.next_action)
            return _finish(root, run, signal, write_evidence=write_evidence)

    signal = _signal(
        "max_iterations",
        "max_iterations",
        f"Inspect {loop_runs_dir(root, loop_id).as_posix()} or rerun with a higher --max-iterations.",
    )
    return _finish(root, run, signal, write_evidence=write_evidence)


def render_loop_run(run: LoopRun) -> str:
    lines = [
        "DevFlow Loop Run",
        "",
        f"Status: {run.status}",
        f"Iterations: {run.iterations_completed}/{run.max_iterations}",
        f"Tasks created: {run.tasks_created}",
        f"Workers run: {run.workers_run}",
        f"Verification passed: {run.verification_results.get('passed', 0)}",
        f"Verification failed: {run.verification_results.get('failed', 0)}",
        f"Promotion previews: {run.promotion_previews_completed}",
        f"Promotions completed: {run.promotions_completed}",
        f"Stop reason: {run.stop_reason}",
        f"Next safe action: {run.next_safe_action}",
    ]
    if run.evidence_path:
        lines.append(f"Evidence: {run.evidence_path}")
    return "\n".join(lines) + "\n"


def loops_dir(root: Path) -> Path:
    return devflow_dir(root) / "loops"


def loop_dir(root: Path, loop_id: str) -> Path:
    return loops_dir(root) / loop_id


def loop_config_path(root: Path, loop_id: str) -> Path:
    return loop_dir(root, loop_id) / "loop.yaml"


def loop_runs_dir(root: Path, loop_id: str) -> Path:
    return loop_dir(root, loop_id) / "runs"


def _validate_loop_definition(definition: LoopDefinition) -> None:
    if definition.schema_version != LOOP_SCHEMA_VERSION:
        raise LoopConfigError(f"Unsupported loop schema_version: {definition.schema_version}")
    if definition.template not in ALLOWED_LOOP_TEMPLATES:
        raise LoopConfigError(f"Unknown loop template: {definition.template}")
    if definition.source != "active_goals":
        raise LoopConfigError(f"Unknown loop source: {definition.source}")
    for action in definition.actions:
        if action not in ALLOWED_LOOP_ACTIONS:
            raise LoopConfigError(f"Unknown loop action: {action}")
    _validate_run_controls(
        definition.policy.max_iterations,
        definition.policy.max_parallel,
        definition.policy.worker_timeout_seconds,
        definition.policy.no_progress_limit,
    )


def _validate_run_controls(
    max_iterations: int,
    max_parallel: int,
    worker_timeout_seconds: int,
    no_progress_limit: int,
) -> None:
    if max_iterations < 1:
        raise LoopRunError("max_iterations must be at least 1.")
    if max_parallel < 1:
        raise LoopRunError("max_parallel must be at least 1.")
    if worker_timeout_seconds < 1:
        raise LoopRunError("worker_timeout_seconds must be at least 1.")
    if no_progress_limit < 2:
        raise LoopRunError("no_progress_limit must be at least 2.")


def _preflight_stop(root: Path, definition: LoopDefinition) -> _StopSignal | None:
    git_state = inspect_git_state(root)
    if git_state.operation_in_progress:
        return _signal(
            "unsafe_git_state",
            "git_operation_in_progress",
            "Resolve the in-progress Git operation, then rerun the loop.",
        )
    if git_state.is_repo:
        try:
            unsafe_dirty = main_checkout_has_uncommitted_changes(root)
        except ValueError:
            unsafe_dirty = git_state.dirty
        if unsafe_dirty:
            return _signal(
                "unsafe_git_state",
                "unsafe_dirty_git_state",
                "Run devflow git status, then checkpoint or clean unrelated checkout changes before rerunning the loop.",
            )

    if definition.policy.stop_on_open_questions:
        questions = build_question_snapshot(root)
        if questions.counts.get("open", 0):
            open_question = next((item for item in questions.questions if item.status == "open"), None)
            next_action = (
                f"devflow question answer {open_question.question_id} --answer \"<answer>\""
                if open_question is not None
                else "devflow question list"
            )
            return _signal("open_questions", "open_questions", next_action)
    return None


def _blocked_goal_stop(definition: LoopDefinition, report: FreshnessReport) -> _StopSignal | None:
    if report.status == "needs_human_decision":
        return _signal("blocked", "freshness_needs_human_decision", report.next_action)
    if not definition.policy.stop_on_blockers:
        return None
    blocked_goal = next(
        (
            goal
            for goal in report.goal_loop
            if goal.loop_state in {"blocked", "needs_lifecycle_activation"}
            or goal.goal_state in {"blocked", "missing_lifecycle"}
            or goal.blocked_lane_count > 0
        ),
        None,
    )
    if blocked_goal is None:
        return None
    return _signal("blocked", "blocked_goals", blocked_goal.next_action or f"devflow goal status {blocked_goal.goal_id}")


class _SelectedParallelBatch(BaseModel):
    goal_id: str
    batch: Any


def _first_parallel_batch(report: FreshnessReport) -> _SelectedParallelBatch | None:
    for goal in report.goal_loop:
        if goal.parallel_batches:
            return _SelectedParallelBatch(goal_id=goal.goal_id, batch=goal.parallel_batches[0])
    return None


def _first_worker_batch(root: Path, report: FreshnessReport):
    for goal in report.goal_loop:
        for batch in goal.worker_batches:
            filtered_items = [
                item
                for item in batch.items
                if _task_status(root, item.task_id) in {"created", "worker_failed", "failed"}
            ]
            if filtered_items:
                task_ids = _dedupe([item.task_id for item in filtered_items])
                commands = [
                    command
                    for item in filtered_items
                    for command in [item.devflow_command]
                    if command
                ]
                return batch.model_copy(update={"items": filtered_items, "task_ids": task_ids, "commands": commands})
    return None


def _first_verification_batch(root: Path, report: FreshnessReport):
    for goal in report.goal_loop:
        for batch in goal.verification_batches:
            filtered_items = [
                item
                for item in batch.items
                if _task_status(root, item.task_id) in {"complete", "verification_failed"}
            ]
            if filtered_items:
                task_ids = _dedupe([item.task_id for item in filtered_items])
                commands = [
                    command
                    for item in filtered_items
                    for command in [item.devflow_command]
                    if command
                ]
                return batch.model_copy(update={"items": filtered_items, "task_ids": task_ids, "commands": commands})
    return None


def _promotion_candidates(root: Path, report: FreshnessReport) -> list[_PromotionCandidate]:
    candidates: list[_PromotionCandidate] = []
    seen_task_ids: set[str] = set()
    for goal in report.goal_loop:
        for lane in goal.lanes:
            if lane.lane_state != "ready_to_promote" or not lane.linked_task_ids:
                continue
            task_id = lane.linked_task_ids[-1]
            seen_task_ids.add(task_id)
            link = _goal_link(root, task_id)
            risk = str(link.get("risk") or lane.risk or "medium").lower()
            candidates.append(
                _PromotionCandidate(
                    goal_id=goal.goal_id,
                    lane_id=lane.slice_id,
                    task_id=task_id,
                    risk=risk,
                    promotion_allowed=bool(link.get("promotion_allowed")),
                    high_risk=risk in {"high", "critical"},
                )
            )
    for task in list_tasks(root):
        if task.id in seen_task_ids or task.status != "verified" or task.verification_status != "passed":
            continue
        if (task_dir(root, task.id) / "goal-link.yaml").exists():
            continue
        candidates.append(
            _PromotionCandidate(
                goal_id="standalone-task",
                lane_id=task.id,
                task_id=task.id,
                risk="medium",
                promotion_allowed=True,
                high_risk=False,
            )
        )
    return candidates


def _handle_promotion_candidate(
    root: Path,
    definition: LoopDefinition,
    candidate: _PromotionCandidate,
    *,
    allow_promote: bool,
) -> tuple[_StopSignal, LoopPromotionPreviewResult | None, LoopPromotionResult | None]:
    if "promotion_preview" not in definition.actions or "promote" not in definition.actions:
        return (
            _signal("promotion_blocked", "promotion_action_not_enabled", f"Edit {loop_config_path(root, definition.loop_id)}"),
            None,
            None,
        )
    if not definition.policy.allow_promotion:
        return (
            _signal("promotion_blocked", "promotion_not_allowed_by_loop_config", f"Edit {loop_config_path(root, definition.loop_id)}"),
            None,
            None,
        )
    if not allow_promote:
        return (
            _signal("promotion_blocked", "allow_promote_flag_required", f"devflow loop run {definition.loop_id} --allow-promote"),
            None,
            None,
        )
    if not candidate.promotion_allowed:
        return (
            _signal("promotion_blocked", "task_promotion_not_allowed", f"devflow task promote-preview {candidate.task_id}"),
            None,
            None,
        )
    if candidate.high_risk and not definition.policy.allow_high_risk:
        return (
            _signal("promotion_blocked", "high_risk_promotion_blocked", f"devflow task promote-preview {candidate.task_id}"),
            None,
            None,
        )

    try:
        preview = preview_task_promotion(root, candidate.task_id)
    except Exception as exc:
        preview_result = LoopPromotionPreviewResult(task_id=candidate.task_id, status="failed", reason=str(exc))
        return (
            _signal("promotion_preview_failed", "promotion_preview_failed", f"devflow task promote-preview {candidate.task_id}"),
            preview_result,
            None,
        )

    preview_result = LoopPromotionPreviewResult(
        task_id=candidate.task_id,
        status="clean",
        added=list(preview.get("added") or []),
        modified=list(preview.get("modified") or []),
        deleted=list(preview.get("deleted") or []),
    )
    refusal = _promotion_preview_refusal(root, preview)
    if refusal:
        preview_result.status = "blocked"
        preview_result.reason = refusal
        return (
            _signal("promotion_blocked", refusal, f"devflow task promote-preview {candidate.task_id}"),
            preview_result,
            None,
        )

    try:
        promote_task(root, candidate.task_id)
    except Exception as exc:
        return (
            _signal("promotion_blocked", "promotion_failed", f"devflow task promote-preview {candidate.task_id}"),
            preview_result,
            LoopPromotionResult(task_id=candidate.task_id, status="failed", reason=str(exc)),
        )
    return (
        _signal("completed", "promoted", "Continue loop dispatch."),
        preview_result,
        LoopPromotionResult(task_id=candidate.task_id, status="promoted"),
    )


def _promotion_preview_refusal(root: Path, preview: dict[str, Any]) -> str | None:
    if preview.get("deleted"):
        return "promotion_preview_has_deletions"
    if preview.get("binary"):
        return "promotion_preview_has_binary_files"
    human_approval = preview.get("human_approval") or {}
    if human_approval.get("required"):
        return "human_checkpoint_required"
    git_preview = preview.get("git")
    if git_preview and git_preview.get("promotion_readiness") != "ready":
        return "git_promotion_preview_not_ready"
    baseline = preview.get("baseline") or {}
    if inspect_git_state(root).is_repo and baseline.get("baseline_status") != "unchanged":
        return "promotion_baseline_not_clean"
    return None


def _goal_link(root: Path, task_id: str) -> dict[str, Any]:
    path = task_dir(root, task_id) / "goal-link.yaml"
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _no_projected_work(report: FreshnessReport) -> bool:
    for goal in report.goal_loop:
        if goal.parallel_batches or goal.worker_batches or goal.verification_batches:
            return False
        if any(lane.lane_state == "ready_to_promote" for lane in goal.lanes):
            return False
    return True


def _did_mutating_work(run: LoopRun) -> bool:
    return bool(
        run.tasks_created
        or run.workers_run
        or run.verification_results.get("passed", 0)
        or run.verification_results.get("failed", 0)
        or run.promotions_completed
    )


def _accumulate_verification(run: LoopRun, verification_run: ParallelVerificationRun) -> None:
    for result in verification_run.results:
        if result.status == "passed":
            run.verification_results["passed"] = run.verification_results.get("passed", 0) + 1
        else:
            run.verification_results["failed"] = run.verification_results.get("failed", 0) + 1


def _task_status(root: Path, task_id: str) -> str:
    try:
        return get_task(root, task_id).status
    except Exception:
        return "unknown"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _iteration(
    iteration_number: int,
    report: FreshnessReport,
    *,
    action: str,
    signal: _StopSignal | None = None,
    task_creation_run: ParallelTaskCreationRun | None = None,
    worker_run: ParallelWorkerRun | None = None,
    verification_run: ParallelVerificationRun | None = None,
    promotion_previews: list[LoopPromotionPreviewResult] | None = None,
    promotions: list[LoopPromotionResult] | None = None,
) -> LoopIteration:
    return LoopIteration(
        iteration=iteration_number,
        freshness_status=report.status,
        state_hash=report.state_hash,
        action=action,
        stop_reason=signal.stop_reason if signal else None,
        next_safe_action=signal.next_safe_action if signal else report.next_action,
        task_creation_run=task_creation_run,
        worker_run=worker_run,
        verification_run=verification_run,
        promotion_previews=promotion_previews or [],
        promotions=promotions or [],
    )


def _signal(status: LoopRunStatus, stop_reason: str, next_safe_action: str) -> _StopSignal:
    return _StopSignal(status=status, stop_reason=stop_reason, next_safe_action=next_safe_action)


def _finish(root: Path, run: LoopRun, signal: _StopSignal, *, write_evidence: bool) -> LoopRun:
    run.status = signal.status
    run.stop_reason = signal.stop_reason
    run.next_safe_action = signal.next_safe_action
    run.finished_at = _now()
    run.iterations_completed = len(run.iterations)
    if not write_evidence:
        return run
    path = loop_runs_dir(root, run.loop_id) / f"{run.run_id}.json"
    updated = run.model_copy(update={"evidence_path": relative_path(root, path)})
    atomic_write_text(path, updated.model_dump_json(indent=2) + "\n")
    return updated


def _run_id(loop_id: str, timestamp: str) -> str:
    compact = timestamp.replace("-", "").replace(":", "").replace(".", "").replace("+", "Z")
    safe_loop = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in loop_id)
    return f"{safe_loop}-{compact}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"
