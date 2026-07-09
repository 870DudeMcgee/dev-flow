from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from devflow.legacy.control_room.devmode_bridge import devmode_discipline_lines, detect_devmode
from devflow.legacy.control_room.git_state import inspect_git_state
from devflow.legacy.control_room.git_worktree import is_git_worktree_task, worker_id_for_task
from devflow.legacy.control_room.models import TASK_SCHEMA_VERSION, TaskRecord
from devflow.legacy.control_room.paths import relative_path, task_dir
from devflow.legacy.control_room.persistence import atomic_write_text, get_task, utc_now, validate_event_log


ORCHESTRATION_POLICY_VERSION = "parallel-worker-spawn-policy-v1"
SERIAL_LOCAL_AGENT_PIPELINE_VERSION = "serial-local-agent-pipeline-v1"

ALLOWED_ROLES = {
    "planner",
    "repo_scope_scout",
    "implementation_worker",
    "reviewer",
    "verifier",
    "summarizer",
    "escalation_judge",
    "manual_human",
}
ALLOWED_EXECUTION_MODES = {
    "read_only",
    "evidence_only",
    "workspace_write",
    "worktree_write",
    "human_manual",
    "deterministic_verifier",
}
ALLOWED_MATURITY = {
    "stable_runtime",
    "local_patch_runtime",
    "experimental_readonly",
    "experimental_manual",
    "planned_not_executable",
}
ALLOWED_CONTEXT_LAYERS = {"L0", "L1", "L2", "L3", "L4", "L5"}
INACTIVE_TASK_STATUSES = {"closed", "promoted"}
CANONICAL_TASK_WRITE_TARGETS = {
    "task.yaml",
    "events.jsonl",
    "verification.json",
    "merge-readiness.json",
    "summary.json",
    "closure.json",
    "cleanup.json",
    "patch-application.json",
}


class OrchestrationPlanError(ValueError):
    pass


def create_orchestration_plan(root: Path, task_id: str, *, plan_only: bool = True) -> dict[str, Any]:
    if not plan_only:
        raise OrchestrationPlanError("Orchestration policy MVP supports --plan-only only.")

    task = get_task(root, task_id)
    if task.status in INACTIVE_TASK_STATUSES:
        raise OrchestrationPlanError(f"Task {task_id} is inactive ({task.status}); orchestration planning refused.")

    plan = build_orchestration_plan(root, task)
    errors = validate_orchestration_plan(plan)
    if errors:
        raise OrchestrationPlanError("; ".join(errors))

    output_path = task_dir(root, task_id) / "orchestration-plan.yaml"
    atomic_write_text(output_path, yaml.safe_dump(plan, sort_keys=False))
    return plan


def build_orchestration_plan(root: Path, task: TaskRecord) -> dict[str, Any]:
    git_state = inspect_git_state(root)
    devmode = detect_devmode(root)
    task_path = task_dir(root, task.id)
    git_baseline = _git_baseline(git_state)
    implementation_mode = "worktree_write" if is_git_worktree_task(task) else "workspace_write"
    stop_conditions = _stop_conditions(root, task, task_path, git_state, devmode.detected)
    active_conditions = [item for item in stop_conditions if item["active"]]
    risk_level = _risk_level(task, active_conditions)
    parallelism_allowed = not active_conditions and risk_level != "high"
    recommended_execution = (
        "parallel"
        if parallelism_allowed
        else "human_review_first"
        if any(item["requires_human_review"] for item in active_conditions) or risk_level == "high"
        else "sequential"
    )

    reason = "parallel lanes allowed by current Git, DevMode, task, and artifact guardrails"
    if not parallelism_allowed:
        active_names = ", ".join(item["condition"] for item in active_conditions) or f"{risk_level} risk"
        reason = f"parallel lanes blocked until reviewed: {active_names}"

    plan: dict[str, Any] = {
        "schema_version": TASK_SCHEMA_VERSION,
        "task_id": task.id,
        "created_at": utc_now().isoformat(),
        "policy_version": ORCHESTRATION_POLICY_VERSION,
        "mode": "plan_only",
        "git_baseline": git_baseline,
        "devmode_required": True,
        "parallelism_allowed": parallelism_allowed,
        "reason": reason,
        "risk_level": risk_level,
        "recommended_execution": recommended_execution,
        "serial_local_agent_pipeline": _serial_local_agent_pipeline(task, implementation_mode),
        "roles": _roles_for_task(root, task),
        "stop_conditions": stop_conditions,
        "promotion": {
            "requires_human": True,
            "requires_verification_passed": True,
            "allowed_by_workers": False,
            "notes": [
                "Workers may produce evidence or workspace/worktree changes only.",
                "Dev-Flow verification and human promotion remain separate gates.",
            ],
        },
        "notes": [
            "Plan-only policy evidence; no workers, providers, patches, verification, or promotion were executed.",
            "DevMode discipline applies to every worker role.",
            *devmode_discipline_lines(root),
        ],
    }
    return plan


def validate_orchestration_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "task_id",
        "created_at",
        "policy_version",
        "mode",
        "git_baseline",
        "devmode_required",
        "parallelism_allowed",
        "reason",
        "risk_level",
        "recommended_execution",
        "serial_local_agent_pipeline",
        "roles",
        "stop_conditions",
        "promotion",
        "notes",
    }
    missing = sorted(required - set(plan))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
        return errors
    if plan.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if plan.get("mode") != "plan_only":
        errors.append("mode must be plan_only")
    if plan.get("devmode_required") is not True:
        errors.append("devmode_required must be true")
    if plan.get("recommended_execution") not in {"sequential", "parallel", "human_review_first"}:
        errors.append("recommended_execution is invalid")

    serial_pipeline = plan.get("serial_local_agent_pipeline")
    if not isinstance(serial_pipeline, dict):
        errors.append("serial_local_agent_pipeline must be an object")
    else:
        errors.extend(_validate_serial_local_agent_pipeline(serial_pipeline))

    roles = plan.get("roles")
    if not isinstance(roles, list) or not roles:
        errors.append("roles must be a non-empty list")
    else:
        for index, role in enumerate(roles):
            errors.extend(_validate_role(role, index))

    promotion = plan.get("promotion")
    if not isinstance(promotion, dict):
        errors.append("promotion must be an object")
    else:
        if promotion.get("requires_human") is not True:
            errors.append("promotion.requires_human must be true")
        if promotion.get("requires_verification_passed") is not True:
            errors.append("promotion.requires_verification_passed must be true")
        if promotion.get("allowed_by_workers") is not False:
            errors.append("promotion.allowed_by_workers must be false")
    return errors


def _validate_role(role: Any, index: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(role, dict):
        return [f"roles[{index}] must be an object"]
    role_name = str(role.get("role") or "")
    execution_mode = role.get("execution_mode")
    maturity = role.get("maturity")
    context_layer = role.get("context_layer")
    if role_name not in ALLOWED_ROLES:
        errors.append(f"roles[{index}].role is invalid")
    if execution_mode not in ALLOWED_EXECUTION_MODES:
        errors.append(f"roles[{index}].execution_mode is invalid")
    if maturity not in ALLOWED_MATURITY:
        errors.append(f"roles[{index}].maturity is invalid")
    if context_layer not in ALLOWED_CONTEXT_LAYERS:
        errors.append(f"roles[{index}].context_layer is invalid")
    if role.get("can_promote") is not False:
        errors.append(f"roles[{index}].can_promote must be false")
    if maturity == "planned_not_executable" and execution_mode in {
        "workspace_write",
        "worktree_write",
        "deterministic_verifier",
    }:
        errors.append(f"roles[{index}] planned_not_executable role cannot be scheduled for execution")
    can_write = role.get("can_write") or []
    if not isinstance(can_write, list):
        errors.append(f"roles[{index}].can_write must be a list")
        can_write = []
    if execution_mode == "read_only" and _has_source_write(can_write):
        errors.append(f"roles[{index}] read_only role cannot have source write permissions")
    for field in (
        "can_write",
        "cannot_touch",
        "input_artifacts",
        "output_artifacts",
        "required_evidence",
    ):
        values = role.get(field) or []
        if not isinstance(values, list):
            errors.append(f"roles[{index}].{field} must be a list")
            continue
        for value in values:
            err = _path_policy_error(
                str(value),
                for_write=field == "can_write",
                allow_git=field == "cannot_touch",
            )
            if err:
                errors.append(f"roles[{index}].{field}: {err}")
    for field in ("workspace", "worktree"):
        value = role.get(field)
        if value:
            err = _path_policy_error(str(value), for_write=False)
            if err:
                errors.append(f"roles[{index}].{field}: {err}")
    return errors


def _git_baseline(state: Any) -> dict[str, Any]:
    return {
        "current_branch": state.branch,
        "head_sha": state.head_sha,
        "origin_main_sha": state.origin_main_sha,
        "dirty_state": "dirty" if state.dirty else "clean",
        "operation_in_progress": state.operation_in_progress,
        "ahead_behind": {
            "ahead_origin_main": state.ahead_origin_main,
            "behind_origin_main": state.behind_origin_main,
            "main_ahead_origin_main": state.main_ahead_origin_main,
            "main_behind_origin_main": state.main_behind_origin_main,
            "main_diverged_origin_main": state.main_diverged_origin_main,
        },
        "conflicted_files": list(state.conflicted_files),
        "safe_for_worker_writes": state.safe_for_worker_writes,
        "safe_for_promotion": state.safe_for_promotion,
    }


def _stop_conditions(
    root: Path,
    task: TaskRecord,
    task_path: Path,
    git_state: Any,
    devmode_detected: bool,
) -> list[dict[str, Any]]:
    events_ok, events_detail = validate_event_log(task_path / "events.jsonl")
    ambiguous = _task_looks_ambiguous(task.title)
    high_overlap = _task_looks_serial(task.title)
    unsafe_title = _task_looks_unsafe(task.title)
    malformed = not events_ok or not (task_path / "verification.json").exists()
    workspace_assignable = bool(task.workspace_path or task.workspace)
    conflict_detected = bool(git_state.conflicted_files)
    stale_base = bool(
        git_state.main_behind_origin_main and git_state.main_behind_origin_main > 0
    ) or git_state.main_diverged_origin_main

    return [
        _condition("human_clarification_needed", ambiguous, "task title is ambiguous", True),
        _condition("dirty_git_tree", git_state.dirty, "working tree has uncommitted changes", True),
        _condition(
            "git_state_unsafe",
            not git_state.safe_for_worker_writes,
            "Git state is not safe for worker writes",
            True,
        ),
        _condition(
            "git_operation_in_progress",
            bool(git_state.operation_in_progress),
            f"git operation in progress: {git_state.operation_in_progress}",
            True,
        ),
        _condition("branch_divergence", git_state.main_diverged_origin_main, "main and origin/main diverged", True),
        _condition("conflict_detected", conflict_detected, "conflicted files are present", True),
        _condition("stale_baseline_detected", stale_base, "main baseline is stale against origin/main", True),
        _condition("workspace_isolation_unavailable", not workspace_assignable, "task workspace/worktree is missing", True),
        _condition("expected_edits_overlap_heavily", high_overlap, "task looks like a serialized migration/rewrite", True),
        _condition("architectural_risk_escalates", unsafe_title, "task wording implies destructive/high-risk work", True),
        _condition("task_artifacts_malformed", malformed, events_detail, True),
        _condition("devmode_missing", not devmode_detected, "DevMode skill/rule evidence is missing", True),
        _condition(
            "context_estimate_exceeds_selected_model",
            False,
            "not estimated in plan-only MVP",
            True,
        ),
        _condition("workers_propose_conflicting_edits", False, "no workers executed", True),
        _condition("task_state_changes_underneath_plan", False, "baseline recorded in plan evidence", True),
        _condition("non_stable_adapter_requested_for_execution", False, "no execution requested", True),
        _condition("validation_fails", False, "internal plan validation passed before write", True),
        _condition("verification_fails", False, "verification is not run by orchestration planning", True),
        _condition("forbidden_write_requested", False, "role write permissions validated", True),
        _condition("unsafe_path_detected", False, "role paths validated", True),
    ]


def _condition(condition: str, active: bool, reason: str, requires_human_review: bool) -> dict[str, Any]:
    return {
        "condition": condition,
        "active": bool(active),
        "reason": reason,
        "requires_human_review": requires_human_review,
    }


def _serial_local_agent_pipeline(task: TaskRecord, implementation_mode: str) -> dict[str, Any]:
    """Return the serial local-agent supervision contract for a task.

    This is plan-only evidence: it assigns responsibilities to fresh serial
    specialists but does not launch workers. The supervisor still owns final
    verification and acceptance.
    """
    task_token = "<task>"
    workspace_token = "<worktree>" if is_git_worktree_task(task) else "<workspace>"
    return {
        "policy_version": SERIAL_LOCAL_AGENT_PIPELINE_VERSION,
        "strategy": "serial_specialists",
        "single_flight_required": True,
        "acceptance_owner": "supervisor_final_gate",
        "why": (
            "Split implementation, verification, and repair into fresh bounded contexts so one "
            "local model run does not burn its budget debugging its own work."
        ),
        "phases": [
            {
                "order": 1,
                "phase": "implementer",
                "role": "implementation_worker",
                "execution_mode": implementation_mode,
                "agent_kind": "local_patch_runtime",
                "context_policy": "fresh_l1_packet",
                "may_edit": True,
                "can_promote": False,
                "entry_condition": "bounded packet with exact allowed files and non-goals",
                "exit_gate": "source changes plus focused self-check evidence only; no final acceptance",
                "allowed_write_scope": [f"{workspace_token}/**"],
                "required_evidence": [f"{task_token}/local-model-runs/<run-id>/result.md"],
            },
            {
                "order": 2,
                "phase": "verifier",
                "role": "verifier",
                "execution_mode": "deterministic_verifier",
                "agent_kind": "script_or_read_only_local",
                "context_policy": "fresh_verification_packet",
                "may_edit": False,
                "can_promote": False,
                "entry_condition": "implementer process exited and changed-file allowlist is known",
                "exit_gate": "exact verification commands with exit codes and failure classification",
                "allowed_write_scope": [],
                "required_evidence": [f"{task_token}/logs/verify.log"],
            },
            {
                "order": 3,
                "phase": "tiny_repair",
                "role": "implementation_worker",
                "execution_mode": implementation_mode,
                "agent_kind": "local_patch_runtime",
                "context_policy": "fresh_tiny_repair_packet",
                "may_edit": True,
                "can_promote": False,
                "entry_condition": "verifier found deterministic in-scope failures not trivial for supervisor",
                "exit_gate": "only the named failures repaired; no broad relaunch",
                "allowed_write_scope": [f"{workspace_token}/**"],
                "required_evidence": [f"{task_token}/local-model-runs/<repair-run-id>/result.md"],
            },
            {
                "order": 4,
                "phase": "supervisor_final_gate",
                "role": "manual_human",
                "execution_mode": "human_manual",
                "agent_kind": "supervisor",
                "context_policy": "tool_output_only",
                "may_edit": False,
                "can_promote": False,
                "entry_condition": "worker/verifier/repair phases have quiesced",
                "exit_gate": "supervisor reruns allowlist, tests, and diff hygiene before acceptance",
                "allowed_write_scope": [],
                "required_evidence": [f"{task_token}/orchestration/final-gate.md"],
            },
        ],
    }


def _validate_serial_local_agent_pipeline(pipeline: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if pipeline.get("policy_version") != SERIAL_LOCAL_AGENT_PIPELINE_VERSION:
        errors.append("serial_local_agent_pipeline.policy_version is invalid")
    if pipeline.get("strategy") != "serial_specialists":
        errors.append("serial_local_agent_pipeline.strategy must be serial_specialists")
    if pipeline.get("single_flight_required") is not True:
        errors.append("serial_local_agent_pipeline.single_flight_required must be true")
    if pipeline.get("acceptance_owner") != "supervisor_final_gate":
        errors.append("serial_local_agent_pipeline.acceptance_owner must be supervisor_final_gate")
    phases = pipeline.get("phases")
    expected = ["implementer", "verifier", "tiny_repair", "supervisor_final_gate"]
    if not isinstance(phases, list):
        return [*errors, "serial_local_agent_pipeline.phases must be a list"]
    actual = [str(phase.get("phase") or "") for phase in phases if isinstance(phase, dict)]
    if actual != expected:
        errors.append("serial_local_agent_pipeline.phases must be implementer -> verifier -> tiny_repair -> supervisor_final_gate")
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            errors.append(f"serial_local_agent_pipeline.phases[{index}] must be an object")
            continue
        if phase.get("order") != index + 1:
            errors.append(f"serial_local_agent_pipeline.phases[{index}].order must be {index + 1}")
        if phase.get("role") not in ALLOWED_ROLES:
            errors.append(f"serial_local_agent_pipeline.phases[{index}].role is invalid")
        if phase.get("execution_mode") not in ALLOWED_EXECUTION_MODES:
            errors.append(f"serial_local_agent_pipeline.phases[{index}].execution_mode is invalid")
        if phase.get("can_promote") is not False:
            errors.append(f"serial_local_agent_pipeline.phases[{index}].can_promote must be false")
        if phase.get("phase") in {"verifier", "supervisor_final_gate"} and phase.get("may_edit") is not False:
            errors.append(f"serial_local_agent_pipeline.phases[{index}] verification/final gate must not edit")
        if phase.get("phase") in {"implementer", "tiny_repair"} and phase.get("may_edit") is not True:
            errors.append(f"serial_local_agent_pipeline.phases[{index}] write phase must be explicit")
        for value in phase.get("allowed_write_scope") or []:
            err = _path_policy_error(str(value), for_write=True)
            if err:
                errors.append(f"serial_local_agent_pipeline.phases[{index}].allowed_write_scope: {err}")
    return errors


def _roles_for_task(root: Path, task: TaskRecord) -> list[dict[str, Any]]:
    task_token = "<task>"
    workspace_token = "<worktree>" if is_git_worktree_task(task) else "<workspace>"
    lane_path = f".devflow/worktrees/{task.id}/{worker_id_for_task(task)}" if is_git_worktree_task(task) else task.workspace
    implementation_mode = "worktree_write" if is_git_worktree_task(task) else "workspace_write"
    implementation_role = {
        "role": "implementation_worker",
        "agent_id": "shell",
        "agent_tier": "stable_local",
        "execution_mode": implementation_mode,
        "maturity": "stable_runtime",
        "context_layer": "L1",
        "can_write": [f"{workspace_token}/**"],
        "cannot_touch": _canonical_forbidden_paths(task_token),
        "workspace": None if is_git_worktree_task(task) else task.workspace,
        "worktree": lane_path if is_git_worktree_task(task) else None,
        "input_artifacts": [f"{task_token}/task.yaml", f"{task_token}/orchestration-plan.yaml"],
        "output_artifacts": [f"{task_token}/logs/worker.log", f"{task_token}/result.md"],
        "required_evidence": [f"{task_token}/logs/worker.log", f"{task_token}/result.md"],
        "devmode_skills_required": ["using-devmode", "workspace-isolation"],
        "can_promote": False,
        "notes": ["Receives the smallest safe context layer and writes only in the assigned lane."],
    }
    return [
        _read_role(
            "planner",
            "planning_tier",
            "experimental_readonly",
            "L3",
            [f"{task_token}/orchestration/planner-notes.md"],
            "May receive broader context than implementation workers.",
        ),
        _read_role(
            "repo_scope_scout",
            "local_scout",
            "experimental_readonly",
            "L2",
            [f"{task_token}/orchestration/repo-scope-scout.md"],
            "Read-only scope scout; no source writes.",
        ),
        implementation_role,
        _read_role(
            "reviewer",
            "review_tier",
            "experimental_readonly",
            "L2",
            [f"{task_token}/orchestration/review.md"],
            "Reviews proposal/evidence plus enough context to verify correctness.",
        ),
        {
            "role": "verifier",
            "agent_id": "devflow",
            "agent_tier": "deterministic",
            "execution_mode": "deterministic_verifier",
            "maturity": "stable_runtime",
            "context_layer": "L0",
            "can_write": [],
            "cannot_touch": _canonical_forbidden_paths(task_token),
            "workspace": task.workspace,
            "worktree": lane_path if is_git_worktree_task(task) else None,
            "input_artifacts": [f"{task_token}/task.yaml"],
            "output_artifacts": [f"{task_token}/logs/verify.log"],
            "required_evidence": [f"{task_token}/logs/verify.log"],
            "devmode_skills_required": ["verification-before-completion"],
            "can_promote": False,
            "notes": ["Dev-Flow owns verification.json through the verification helper; workers do not self-certify."],
        },
        _evidence_role(
            "summarizer",
            "summary_tier",
            "experimental_readonly",
            "L1",
            [f"{task_token}/orchestration/summary.md"],
            "Evidence-only summary role.",
        ),
        _read_role(
            "escalation_judge",
            "frontier_review_planned",
            "planned_not_executable",
            "L4",
            [f"{task_token}/orchestration/escalation-judge.md"],
            "Planned role only; this MVP never schedules it.",
        ),
        {
            "role": "manual_human",
            "agent_id": "human",
            "agent_tier": "human",
            "execution_mode": "human_manual",
            "maturity": "experimental_manual",
            "context_layer": "L5",
            "can_write": [],
            "cannot_touch": _canonical_forbidden_paths(task_token),
            "workspace": None,
            "worktree": None,
            "input_artifacts": [f"{task_token}/orchestration-plan.yaml"],
            "output_artifacts": [f"{task_token}/orchestration/human-review.md"],
            "required_evidence": [f"{task_token}/orchestration/human-review.md"],
            "devmode_skills_required": ["using-devmode", "worker-handoff"],
            "can_promote": False,
            "notes": ["Human review can approve next commands; worker roles still cannot promote."],
        },
    ]


def _read_role(
    role: str,
    agent_tier: str,
    maturity: str,
    context_layer: str,
    output_artifacts: list[str],
    note: str,
) -> dict[str, Any]:
    return {
        "role": role,
        "agent_id": None,
        "agent_tier": agent_tier,
        "execution_mode": "read_only",
        "maturity": maturity,
        "context_layer": context_layer,
        "can_write": [],
        "cannot_touch": _canonical_forbidden_paths("<task>"),
        "workspace": None,
        "worktree": None,
        "input_artifacts": ["<task>/task.yaml", "<task>/events.jsonl"],
        "output_artifacts": output_artifacts,
        "required_evidence": output_artifacts,
        "devmode_skills_required": ["using-devmode", "workspace-isolation"],
        "can_promote": False,
        "notes": [note],
    }


def _evidence_role(
    role: str,
    agent_tier: str,
    maturity: str,
    context_layer: str,
    output_artifacts: list[str],
    note: str,
) -> dict[str, Any]:
    item = _read_role(role, agent_tier, maturity, context_layer, output_artifacts, note)
    item["execution_mode"] = "evidence_only"
    return item


def _canonical_forbidden_paths(task_token: str) -> list[str]:
    return [
        f"{task_token}/task.yaml",
        f"{task_token}/events.jsonl",
        f"{task_token}/verification.json",
        f"{task_token}/merge-readiness.json",
        f"{task_token}/summary.json",
        f"{task_token}/closure.json",
        f"{task_token}/cleanup.json",
        ".git/**",
    ]


def _risk_level(task: TaskRecord, active_conditions: list[dict[str, Any]]) -> str:
    if _task_looks_unsafe(task.title) or any(
        item["condition"] in {"branch_divergence", "conflict_detected", "task_artifacts_malformed"}
        for item in active_conditions
    ):
        return "high"
    if active_conditions or _task_looks_serial(task.title):
        return "medium"
    return "low"


def _task_looks_ambiguous(title: str) -> bool:
    text = title.lower()
    markers = ("?", "tbd", "unclear", "ambiguous", "unknown", "figure out", "decide later")
    return len(text.strip()) < 8 or any(marker in text for marker in markers)


def _task_looks_serial(title: str) -> bool:
    text = title.lower()
    markers = ("migration", "single migration", "rewrite", "whole repo", "all files", "rename package")
    return any(marker in text for marker in markers)


def _task_looks_unsafe(title: str) -> bool:
    text = title.lower()
    markers = ("delete everything", "drop table", "force push", "bypass", "disable guardrail")
    return any(marker in text for marker in markers)


def _has_source_write(paths: list[str]) -> bool:
    for value in paths:
        text = str(value)
        if text.startswith(("<task>/", ".devflow/tasks/")):
            continue
        return True
    return False


def _path_policy_error(value: str, *, for_write: bool, allow_git: bool = False) -> str | None:
    if not value:
        return None
    normalized = value.replace("\\", "/")
    if Path(normalized).is_absolute():
        return f"absolute path rejected: {value}"
    placeholder_prefixes = ("<task>/", "<workspace>/", "<worktree>/", "<devflow>/")
    stripped = normalized
    for prefix in placeholder_prefixes:
        if normalized.startswith(prefix):
            stripped = normalized[len(prefix):]
            break
    if normalized in {"<task>", "<workspace>", "<worktree>", "<devflow>"}:
        stripped = ""
    parts = [part for part in Path(stripped).parts if part not in {"", "."}]
    if ".." in parts:
        return f"parent traversal rejected: {value}"
    if not allow_git and (".git" in parts or normalized.startswith(".git/")):
        return f".git path rejected: {value}"
    if for_write and _targets_canonical_task_state(normalized):
        return f"canonical task state write rejected: {value}"
    return None


def _targets_canonical_task_state(value: str) -> bool:
    normalized = value.replace("\\", "/")
    for name in CANONICAL_TASK_WRITE_TARGETS:
        if normalized.endswith(f"/{name}") or normalized in {name, f"<task>/{name}"}:
            return True
    return False


def render_orchestration_plan_summary(root: Path, plan: dict[str, Any]) -> str:
    output_path = task_dir(root, str(plan["task_id"])) / "orchestration-plan.yaml"
    lines = [
        f"task_id: {plan['task_id']}",
        "mode: plan_only",
        f"policy_version: {plan['policy_version']}",
        f"parallelism_allowed: {'yes' if plan['parallelism_allowed'] else 'no'}",
        f"recommended_execution: {plan['recommended_execution']}",
        "serial_local_agent_pipeline: implementer -> verifier -> tiny_repair -> supervisor_final_gate",
        f"risk_level: {plan['risk_level']}",
        f"reason: {plan['reason']}",
        f"plan_path: {relative_path(root, output_path)}",
        "provider_calls: none",
        "workers_executed: none",
        "main_changed: no",
    ]
    active = [item["condition"] for item in plan["stop_conditions"] if item.get("active")]
    if active:
        lines.append("active_stop_conditions:")
        lines.extend(f"  - {item}" for item in active)
    return "\n".join(lines) + "\n"
