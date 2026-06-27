from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import tempfile
from collections.abc import Callable, Iterable
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from devflow.control_room.agent_registry import load_agent_registry
from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.git_worktree import (
    cleanup_task_git_resources,
    git_worker_lane_summary,
    list_devflow_branches,
    list_devflow_worktrees,
)
from devflow.control_room.goal_tasks import load_goal_task_slices
from devflow.control_room.knowledge_foundry import capture_from_validation, search_knowledge
from devflow.control_room.idea_execution_bridge import create_goal_from_idea
from devflow.control_room.idea_foundry import capture_idea, classify_idea, promote_idea
from devflow.control_room.intent_scaffold import preview_scaffold_from_idea, write_scaffold_from_idea
from devflow.control_room.local_agent_discovery import LocalDiscoveryReport, parse_ollama_list
from devflow.control_room.local_model_worker_pool import agent_json_payload, registry_json_payload
from devflow.control_room.local_worker_lane import local_worker_lane_summary
from devflow.control_room.model_audition import execute_model_audition, write_model_audition_dry_run_plan
from devflow.control_room.operating_layer import build_operating_layer_snapshot
from devflow.control_room.operating_layer_visual_qa import (
    build_visual_qa_plan,
    write_visual_qa_image_fallbacks,
)
from devflow.control_room.orchestration_plan import create_orchestration_plan
from devflow.control_room.paths import (
    dogfood_runs_dir,
    relative_path,
)
from devflow.control_room.persistence import atomic_write_text, get_task, list_tasks, save_task, utc_now
from devflow.control_room.patch_dry_run import preview_patch_dry_run
from devflow.control_room.patch_review import normalize_agent_patch_candidate, review_patch_candidate
from devflow.control_room.question_resume import answer_question, build_question_snapshot
from devflow.control_room.readiness import promotion_readiness_errors
from devflow.control_room.service import (
    apply_task_patch,
    create_task,
    doctor,
    init_control_room,
    preview_task_promotion,
    promote_task,
    run_shell_task,
    verify_task,
)
from devflow.control_room.scheduler_projection import build_scheduler_snapshot, request_scheduler_retry
from devflow.control_room.supervisor_surface import build_control_room_status, build_supervisor_packet
from devflow.control_room.task_closure import close_task
from devflow.control_room.task_packet import TaskPacketLimits, build_agent_packet, build_task_packet
from devflow.control_room.worker_evidence import write_worker_evidence
from devflow.control_room.worker_outcome import validate_worker_outcome, validate_worker_outcome_file
from devflow.control_room.dogfood_case_catalog import (
    CATEGORY_LABELS,
    CATEGORY_MAX,
    DOGFOOD_SCHEMA_VERSION,
    PRODUCTION_READINESS_SUITE,
    DogfoodCaseCatalog,
    materialize_dogfood_cases,
    production_readiness_cases,
    render_dogfood_case,
    render_dogfood_case_list,
    validate_dogfood_case,
)
from devflow.control_room.dogfood_case_result import (
    award_case_points as _award,
    build_dogfood_run_yaml as _build_run_yaml,
    build_dogfood_scorecard as _build_scorecard,
    failed_case_result as _failed_case_result,
    finalize_case_result as _finalize_case,
    git_baseline as _git_baseline,
    git_short_status as _git_short_status,
    record_artifact as _record_artifact,
    record_artifacts as _record_artifacts,
    record_command as _record_command,
    record_lesson as _record_lesson,
    record_warning as _record_warning,
    render_dogfood_report as _render_report,
    set_cleanup_status as _set_cleanup_status,
    skipped_unknown_case_result as _skipped_unknown_case,
    start_case_result as _new_case_state,
    write_case_result as _write_case_result,
)

__all__ = [
    "CATEGORY_MAX",
    "DOGFOOD_SCHEMA_VERSION",
    "PRODUCTION_READINESS_SUITE",
    "load_dogfood_run",
    "materialize_dogfood_cases",
    "production_readiness_cases",
    "render_dogfood_case",
    "render_dogfood_case_list",
    "render_dogfood_score",
    "run_dogfood_suite",
    "validate_dogfood_case",
]


DEFAULT_DOGFOOD_RUN_RETENTION = 1


CaseRunner = Callable[[Path, str, dict[str, Any], Path, dict[str, Any]], dict[str, Any]]


def run_dogfood_suite(
    root: Path,
    suite: str = PRODUCTION_READINESS_SUITE,
    *,
    case_ids: Iterable[str] | None = None,
    write_root_runtime_evidence: bool = False,
    keep_runs: int = DEFAULT_DOGFOOD_RUN_RETENTION,
) -> dict[str, Any]:
    if suite != PRODUCTION_READINESS_SUITE:
        raise ValueError(f"Unknown dogfood suite: {suite}")
    if keep_runs < 1:
        raise ValueError("keep_runs must be at least 1.")

    catalog = DogfoodCaseCatalog.production_readiness()

    init_control_room(root)
    catalog.materialize(root)
    run_id = _new_run_id(root)
    run_dir = dogfood_runs_dir(root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "cases").mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    baseline = _git_baseline(root)
    requested = catalog.requested_ids(case_ids)
    cases_by_id = catalog.by_id()
    results: list[dict[str, Any]] = []

    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    execution_root = root
    try:
        if not write_root_runtime_evidence:
            temp_dir = tempfile.TemporaryDirectory(prefix=f"{run_id}-")
            execution_root = Path(temp_dir.name) / "project"
            _init_git_native_dogfood_repo(execution_root)
        shared: dict[str, Any] = {
            "report_root": root,
            "execution_root": execution_root,
            "write_root_runtime_evidence": write_root_runtime_evidence,
        }

        for case_id in requested:
            case = cases_by_id.get(case_id)
            if case is None:
                results.append(_skipped_unknown_case(run_id, case_id, run_dir))
                continue
            case_dir = run_dir / "cases" / case["id"]
            case_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_text(case_dir / "case.yaml", yaml.safe_dump(case, sort_keys=False))
            pre_case_task_ids = _task_ids(execution_root)
            try:
                result = _RUNNERS[case["id"]](execution_root, run_id, case, case_dir, shared)
            except Exception as exc:
                result = _failed_case_result(execution_root, run_id, case, case_dir, exc)
            closed_tasks = _close_new_dogfood_tasks(execution_root, pre_case_task_ids, run_id, case["id"])
            if closed_tasks:
                result["dogfood_tasks_closed"] = closed_tasks
            if not write_root_runtime_evidence:
                result["runtime_evidence_root"] = "temp_scratch_project"
            _write_case_result(case_dir, result)
            results.append(result)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()

    duration = round(time.monotonic() - started, 3)
    scorecard = _build_scorecard(run_id, suite, baseline, requested, results, duration)
    run_yaml = _build_run_yaml(run_id, suite, baseline, requested, results, scorecard, duration)
    report = _render_report(run_yaml, scorecard, results)

    atomic_write_text(run_dir / "run.yaml", yaml.safe_dump(run_yaml, sort_keys=False))
    atomic_write_text(run_dir / "scorecard.yaml", yaml.safe_dump(scorecard, sort_keys=False))
    atomic_write_text(run_dir / "report.md", report)
    pruned_runs = _prune_old_dogfood_runs(root, keep_runs=keep_runs)

    return {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "run_id": run_id,
        "run_dir": relative_path(root, run_dir),
        "run_path": relative_path(root, run_dir / "run.yaml"),
        "scorecard_path": relative_path(root, run_dir / "scorecard.yaml"),
        "report_path": relative_path(root, run_dir / "report.md"),
        "run": run_yaml,
        "scorecard": scorecard,
        "results": results,
        "pruned_runs": pruned_runs,
    }


def load_dogfood_run(root: Path, run_id: str) -> dict[str, Any]:
    resolved = _resolve_run_id(root, run_id)
    run_dir = dogfood_runs_dir(root) / resolved
    run_path = run_dir / "run.yaml"
    scorecard_path = run_dir / "scorecard.yaml"
    report_path = run_dir / "report.md"
    if not run_path.exists() or not scorecard_path.exists():
        raise KeyError(f"Dogfood run not found: {run_id}")
    return {
        "run_id": resolved,
        "run_dir": run_dir,
        "run": yaml.safe_load(run_path.read_text(encoding="utf-8")) or {},
        "scorecard": yaml.safe_load(scorecard_path.read_text(encoding="utf-8")) or {},
        "report": report_path.read_text(encoding="utf-8") if report_path.exists() else "",
    }


def render_dogfood_score(scorecard: dict[str, Any]) -> str:
    threshold = scorecard["threshold_result"]
    lines = [
        f"run_id: {scorecard['run_id']}",
        f"total_score: {scorecard['total_score']}/{scorecard['max_score']}",
        f"threshold: {threshold['achieved']}",
        f"silver_met: {'yes' if threshold['silver_met'] else 'no'}",
        "category_scores:",
    ]
    for category, item in scorecard["category_scores"].items():
        lines.append(
            f"  - {CATEGORY_LABELS.get(category, category)}: {item['score']}/{item['max']} ({item['percent']}%)"
        )
    if scorecard["failures"]:
        lines.append("failures:")
        lines.extend(f"  - {failure}" for failure in scorecard["failures"])
    if scorecard["warnings"]:
        lines.append("warnings:")
        lines.extend(f"  - {warning}" for warning in scorecard["warnings"])
    return "\n".join(lines) + "\n"


def _task_ids(root: Path) -> set[str]:
    return {task.id for task in list_tasks(root)}


def _close_new_dogfood_tasks(root: Path, before_ids: set[str], run_id: str, case_id: str) -> list[str]:
    reason = f"dogfood run {run_id} case {case_id} evidence captured; not active project work"
    closed: list[str] = []
    for task in list_tasks(root):
        if task.id in before_ids or task.status == "closed":
            continue
        close_task(root, task.id, outcome="evidence-only", reason=reason)
        closed.append(task.id)
    return closed


def _case_tiny_docs(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    task = create_task(root, "Dogfood tiny docs task")
    _record_command(state, f"devflow task create {task.title!r}", status="passed", output=task.id)

    packet = build_task_packet(
        task.id,
        TaskPacketLimits(recent_events_limit=5, worker_log_tail_lines=5, verify_log_tail_lines=5, log_tail_bytes=2048),
        root=root,
    )
    packet_json = packet.model_dump_json(indent=2)
    packet_path = case_dir / "artifacts" / "task-packet.json"
    atomic_write_text(packet_path, packet_json + "\n")
    state["context_packet_size"] = len(packet_json)
    _record_artifact(state, packet_path, root=root)
    _record_command(state, f"devflow task packet {task.id}", status="passed", output=relative_path(root, packet_path))

    run_shell_task(
        root,
        task.id,
        ["/bin/sh", "-c", "mkdir -p docs && printf 'dogfood tiny docs note\n' > docs/dogfood-tiny-note.md"],
        timeout_seconds=10,
    )
    _record_command(state, f"devflow task run {task.id} --worker shell -- tiny docs write", status="passed")

    verified = verify_task(
        root,
        task.id,
        ["/bin/sh", "-c", "test -s docs/dogfood-tiny-note.md"],
        timeout_seconds=10,
    )
    _record_command(state, f"devflow task verify {task.id} --shell docs check", status=verified.verification_status)

    reloaded = get_task(root, task.id)
    sources = packet.bounded_sources or {}
    source_items = sources.get("sources", []) if isinstance(sources, dict) else []
    source_count = len(source_items) if isinstance(source_items, list) else 0

    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(state, scores, failures, "B_pipeline_correctness", 4, reloaded.status == "verified", "task reached verified state")
    _award(state, scores, failures, "C_context_efficiency", 4, state["context_packet_size"] <= 50000, "task packet stayed bounded")
    _award(state, scores, failures, "C_context_efficiency", 3, source_count <= 12, "tiny task did not require whole-repo context")
    _award(state, scores, failures, "G_performance_lightweight", 2, len(state["commands_run"]) <= 4, "docs-only case used a short command sequence")

    return _finalize_case(root, case, state, scores, failures)


def _case_cli_help(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    task = create_task(root, "Dogfood CLI help bounded task")
    _record_command(state, f"devflow task create {task.title!r}", status="passed", output=task.id)

    plan = create_orchestration_plan(root, task.id, plan_only=True)
    plan_path = root / ".devflow" / "tasks" / task.id / "orchestration-plan.yaml"
    _record_artifact(state, plan_path, root=root)
    _record_command(state, f"devflow task orchestrate {task.id} --plan-only", status="passed", output=relative_path(root, plan_path))

    help_result = _run_devflow_help(root, ["dogfood", "--help"])
    help_path = case_dir / "artifacts" / "dogfood-help.txt"
    atomic_write_text(help_path, help_result.stdout + help_result.stderr)
    _record_artifact(state, help_path, root=root)
    _record_command(
        state,
        "devflow dogfood --help",
        status="passed" if help_result.returncode == 0 else "failed",
        exit_code=help_result.returncode,
        output=relative_path(root, help_path),
    )

    help_text = help_path.read_text(encoding="utf-8")
    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(state, scores, failures, "B_pipeline_correctness", 3, plan.get("mode") == "plan_only", "orchestration is plan-only evidence")
    _award(
        state,
        scores,
        failures,
        "B_pipeline_correctness",
        3,
        plan.get("promotion", {}).get("allowed_by_workers") is False,
        "workers cannot promote from the plan",
    )
    _award(
        state,
        scores,
        failures,
        "C_context_efficiency",
        3,
        len(help_text) < 20000 and "run" in help_text and "list" in help_text,
        "dogfood help is bounded and exposes core commands",
    )
    _award(
        state,
        scores,
        failures,
        "G_performance_lightweight",
        2,
        help_result.returncode == 0 and _commands_have_no_provider_calls(state["commands_run"]),
        "CLI help check avoided provider calls",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_unsafe_worker_outcome(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    outcome_path = case_dir / "artifacts" / "unsafe-outcome.json"
    outcome = _worker_outcome(
        task_id=f"dogfood-{run_id}",
        source_path=relative_path(root, outcome_path),
        outcome="completed",
        files_touched=["../outside.txt", ".git/config"],
        tool_status="unsafe_path",
        human_review_required=False,
        notes=["intentionally invalid unsafe worker outcome"],
    )
    atomic_write_text(outcome_path, json.dumps(outcome, indent=2, sort_keys=True) + "\n")
    _record_artifact(state, outcome_path, root=root)
    result = validate_worker_outcome_file(root, outcome_path)
    _record_artifact(state, result["output_path"])
    shared["unsafe_validation_path"] = result["output_path"]
    _record_command(
        state,
        f"devflow worker validate-outcome {relative_path(root, outcome_path)}",
        status=result["status"],
        exit_code=0 if result["status"] == "passed" else 1,
        output=result["output_path"],
    )

    errors_text = "\n".join(result["errors"])
    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(state, scores, failures, "A_safety_git_discipline", 2, result["status"] == "failed", "unsafe outcome was rejected")
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        1,
        "parent traversal is rejected" in errors_text and ".git paths are rejected" in errors_text,
        "path traversal and .git writes were blocked",
    )
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        1,
        "human_review_required must be true" in errors_text,
        "unsafe metadata requires human review",
    )
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        5,
        Path(root / result["output_path"]).exists(),
        "validation evidence artifact was written",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_git_native_worker_lane(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    scratch = case_dir / "artifacts" / "git-native-lane-repo"
    _init_git_native_dogfood_repo(scratch)
    _record_artifact(state, scratch, root=root)
    _record_command(state, "git init scratch Git-native dogfood repo", status="passed", output=relative_path(root, scratch))

    init_control_room(scratch)
    first = create_task(scratch, "Dogfood Git lane one", git_worktree=True)
    second = create_task(scratch, "Dogfood Git lane two", git_worktree=True)
    _record_command(state, "devflow task create --git-worktree 'Dogfood Git lane one' (scratch)", status="passed", output=first.id)
    _record_command(state, "devflow task create --git-worktree 'Dogfood Git lane two' (scratch)", status="passed", output=second.id)

    run_shell_task(
        scratch,
        first.id,
        ["/bin/sh", "-c", "printf 'lane one\n' > lane-one.txt && git add lane-one.txt && git commit -m lane-one"],
        timeout_seconds=20,
    )
    _record_command(state, f"devflow task run {first.id} --worker shell -- commit lane-one.txt (scratch)", status="passed")
    run_shell_task(
        scratch,
        second.id,
        ["/bin/sh", "-c", "printf 'lane two\n' > lane-two.txt && git add lane-two.txt && git commit -m lane-two"],
        timeout_seconds=20,
    )
    _record_command(state, f"devflow task run {second.id} --worker shell -- commit lane-two.txt (scratch)", status="passed")

    first_verified = verify_task(scratch, first.id, ["/bin/sh", "-c", "test -f lane-one.txt"], timeout_seconds=20)
    second_verified = verify_task(scratch, second.id, ["/bin/sh", "-c", "test -f lane-two.txt"], timeout_seconds=20)
    _record_command(state, f"devflow task verify {first.id} --shell lane-one check (scratch)", status=first_verified.verification_status)
    _record_command(state, f"devflow task verify {second.id} --shell lane-two check (scratch)", status=second_verified.verification_status)

    first_preview = preview_task_promotion(scratch, first.id)
    second_preview = preview_task_promotion(scratch, second.id)
    _record_command(state, f"devflow task promote-preview {first.id} (scratch)", status=first_preview["git"]["promotion_readiness"])
    _record_command(state, f"devflow task promote-preview {second.id} (scratch)", status=second_preview["git"]["promotion_readiness"])

    first_lane_ready = git_worker_lane_summary(scratch, get_task(scratch, first.id)) or {}
    second_lane_ready = git_worker_lane_summary(scratch, get_task(scratch, second.id)) or {}
    status = build_control_room_status(scratch)
    operating = build_operating_layer_snapshot(scratch).model_dump(mode="json")
    doctor_checks = doctor(scratch, strict=True)
    worktrees_before = list_devflow_worktrees(scratch)
    branches_before = list_devflow_branches(scratch)

    promote_task(scratch, first.id)
    _record_command(state, f"devflow task promote {first.id} (scratch approval-gated dogfood)", status="passed")
    second_lane_after_promotion = git_worker_lane_summary(scratch, get_task(scratch, second.id)) or {}

    cleanup_dry_run = cleanup_task_git_resources(scratch, first.id, dry_run=True)
    _record_command(state, f"devflow task cleanup {first.id} --dry-run (scratch)", status="passed")
    cleanup_apply = cleanup_task_git_resources(scratch, first.id, dry_run=False)
    _record_command(state, f"devflow task cleanup {first.id} --apply (scratch)", status="passed")

    first_evidence = scratch / ".devflow" / "tasks" / first.id
    first_worktree = scratch / ".devflow" / "worktrees" / first.id / "shell"
    summary = {
        "scratch_repo": relative_path(root, scratch),
        "doctor_strict": [
            {"name": name, "ok": ok, "detail": detail}
            for name, ok, detail in doctor_checks
        ],
        "worktrees_before_cleanup": worktrees_before,
        "branches_before_cleanup": branches_before,
        "first_lane_ready": first_lane_ready,
        "second_lane_ready": second_lane_ready,
        "supervisor_worker_lanes": [
            task.get("worker_lane")
            for task in status["tasks"]
            if task.get("worker_lane")
        ],
        "operating_layer_worker_lanes": [
            task.get("worker_lane")
            for task in operating["tasks"]
            if task.get("worker_lane")
        ],
        "second_lane_after_first_promotion": second_lane_after_promotion,
        "cleanup_dry_run": cleanup_dry_run,
        "cleanup_apply": cleanup_apply,
        "first_lane_after_cleanup": {
            "task_evidence_exists": first_evidence.exists(),
            "worktree_exists": first_worktree.exists(),
        },
    }
    summary_path = case_dir / "artifacts" / "git-native-lane-summary.json"
    atomic_write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _record_artifact(state, summary_path, root=root)

    status_lanes = [task.get("worker_lane") for task in status["tasks"] if task.get("worker_lane")]
    operating_lanes = [task.get("worker_lane") for task in operating["tasks"] if task.get("worker_lane")]
    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        2,
        all(ok for _, ok, _ in doctor_checks)
        and len(worktrees_before) == 2
        and len(branches_before) == 2,
        "strict doctor and owned resource inventory agreed before promotion",
    )
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        2,
        first_evidence.exists()
        and not first_worktree.exists()
        and any(action.get("action") == "archive_branch" and action.get("applied") for action in cleanup_apply),
        "cleanup preserved canonical task evidence",
    )
    _award(
        state,
        scores,
        failures,
        "B_pipeline_correctness",
        2,
        first_lane_ready.get("readiness_status") == "ready"
        and second_lane_ready.get("readiness_status") == "ready"
        and len(status_lanes) == 2
        and len(operating_lanes) == 2,
        "two Git-native lanes reached verified preview state",
    )
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        2,
        second_lane_after_promotion.get("readiness_status") in {"stale", "blocked"}
        and second_lane_after_promotion.get("next_safe_action") == f"devflow task promote-preview {second.id}",
        "second lane reported stale recovery after first promotion",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_local_worker_lane(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    scratch = case_dir / "artifacts" / "local-worker-lane-repo"
    _init_git_native_dogfood_repo(scratch)
    init_control_room(scratch)
    _record_artifact(state, scratch, root=root)
    _record_command(state, "git init scratch local-worker-lane dogfood repo", status="passed", output=relative_path(root, scratch))

    read_only = create_task(scratch, "Dogfood read-only local worker evidence")
    patch_task = create_task(scratch, "Dogfood local patch worker evidence")
    _record_command(state, "devflow task create 'Dogfood read-only local worker evidence' (scratch)", status="passed", output=read_only.id)
    _record_command(state, "devflow task create 'Dogfood local patch worker evidence' (scratch)", status="passed", output=patch_task.id)

    write_worker_evidence(
        root=scratch,
        worker_type="local_model_worker_pool",
        profile_id="local-gemma4-qat",
        worker_id="local-gemma4-qat",
        task_id=read_only.id,
        run_id="run-1",
        packet_text="deterministic dogfood packet",
        raw_output="deterministic read-only analysis",
        response_text="deterministic read-only response",
        model="gemma4:12b-it-qat",
        adapter="ollama_chat",
        adapter_maturity="local_patch_runtime",
        permission_mode="read_only",
        hermes_delegable=False,
        runtime="dogfood_fixture",
        status="success",
        started_at="2026-06-14T00:00:00+00:00",
        quality_notes="dogfood fixture",
        quality_score=0.9,
    )
    _record_command(state, f"write deterministic read-only WorkerEvidence for {read_only.id}", status="passed")

    patch_workspace_file = scratch / ".devflow" / "workspaces" / patch_task.id / "hello.txt"
    patch_agent_dir = scratch / ".devflow" / "tasks" / patch_task.id / "agents" / "qwopus-implementer"
    patch_agent_dir.mkdir(parents=True, exist_ok=True)
    patch_text = (
        "diff --git a/hello.txt b/hello.txt\n"
        "--- /dev/null\n"
        "+++ b/hello.txt\n"
        "@@ -1,0 +1 @@\n"
        "+hello from local worker lane dogfood\n"
    )
    atomic_write_text(patch_agent_dir / "proposal.patch", patch_text)
    atomic_write_text(patch_agent_dir / "result.md", "Patch proposed by deterministic dogfood fixture.\n")
    atomic_write_text(
        patch_agent_dir / "run.json",
        json.dumps(
            {
                "schema_version": 1,
                "task_id": patch_task.id,
                "agent_id": "qwopus-implementer",
                "status": "complete",
                "model": "qwopus:latest",
                "adapter": "ollama_chat",
                "proposal_patch_found": True,
                "proposal_patch_byte_length": len(patch_text.encode("utf-8")),
                "proposed_file_count": 1,
                "proposed_file_paths": ["hello.txt"],
                "finished_at": "2026-06-14T00:01:00+00:00",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    before_apply_exists = patch_workspace_file.exists()
    _record_command(state, f"write deterministic local patch worker evidence for {patch_task.id}", status="passed")

    normalized_run_id = normalize_agent_patch_candidate(scratch, patch_task.id, "qwopus-implementer")
    review = review_patch_candidate(scratch, patch_task.id, run_id=normalized_run_id)
    _record_command(
        state,
        f"devflow task review-patch {patch_task.id} --agent qwopus-implementer (scratch)",
        status=review.review_status,
    )
    dry_run = preview_patch_dry_run(scratch, patch_task.id, run_id=normalized_run_id)
    _record_command(
        state,
        f"devflow task patch-dry-run {patch_task.id} --agent qwopus-implementer (scratch)",
        status=dry_run.dry_run_status,
    )
    apply_task_patch(scratch, patch_task.id, run_id=normalized_run_id)
    after_apply_exists = patch_workspace_file.exists()
    _record_command(state, f"devflow task apply-patch {patch_task.id} --agent qwopus-implementer (scratch)", status="passed")
    verified = verify_task(scratch, patch_task.id, ["/bin/sh", "-c", "test -f hello.txt"], timeout_seconds=20)
    _record_command(
        state,
        f"devflow task verify {patch_task.id} --shell 'test -f hello.txt' (scratch)",
        status=verified.verification_status,
    )
    preview = preview_task_promotion(scratch, patch_task.id)
    _record_command(
        state,
        f"devflow task promote-preview {patch_task.id} (scratch)",
        status=preview.get("promotion_readiness") or preview.get("status") or "previewed",
    )

    read_lane = local_worker_lane_summary(scratch, get_task(scratch, read_only.id)) or {}
    patch_lane = local_worker_lane_summary(scratch, get_task(scratch, patch_task.id)) or {}
    status = build_control_room_status(scratch)
    operating = build_operating_layer_snapshot(scratch).model_dump(mode="json")
    supervisor_lanes = [task.get("local_worker_lane") for task in status["tasks"] if task.get("local_worker_lane")]
    operating_lanes = [task.get("local_worker_lane") for task in operating["tasks"] if task.get("local_worker_lane")]
    summary = {
        "scratch_repo": relative_path(root, scratch),
        "read_only_lane": read_lane,
        "patch_lane": patch_lane,
        "supervisor_local_worker_lanes": supervisor_lanes,
        "operating_layer_local_worker_lanes": operating_lanes,
        "workspace_file_exists_before_apply": before_apply_exists,
        "workspace_file_exists_after_apply": after_apply_exists,
        "root_file_exists_after_apply": (scratch / "hello.txt").exists(),
        "review_status": review.review_status,
        "dry_run_status": dry_run.dry_run_status,
        "verification_status": verified.verification_status,
    }
    summary_path = case_dir / "artifacts" / "local-worker-lane-summary.json"
    atomic_write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _record_artifact(state, summary_path, root=root)

    commands_text = " ".join(str(command["command"]).lower() for command in state["commands_run"])
    forbidden_tokens = ("openai", "anthropic", "gemini", "push-main", "route")
    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        2,
        not before_apply_exists and after_apply_exists and not (scratch / "hello.txt").exists(),
        "workspace mutation waited for explicit apply-patch",
    )
    _award(
        state,
        scores,
        failures,
        "B_pipeline_correctness",
        2,
        review.review_status in {"low_risk_candidate", "review_required"}
        and dry_run.dry_run_status in {"would_apply_cleanly", "would_create_files", "would_modify_with_warnings"}
        and verified.verification_status == "passed",
        "local patch worker evidence reached apply/verify gates",
    )
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        3,
        read_lane.get("lane_type") == "local-model-worker-pool"
        and read_lane.get("permission_mode") == "read_only"
        and read_lane.get("next_safe_action") == f"devflow agent evidence {read_only.id} --json",
        "read-only local worker evidence was summarized",
    )
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        3,
        patch_lane.get("readiness_status") in {"needs_promotion_preview", "ready"}
        and len(supervisor_lanes) >= 2
        and len(operating_lanes) >= 2
        and not any(token in commands_text for token in forbidden_tokens),
        "no provider API calls or autonomous routing were introduced",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_registry_runtime_contract(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    scratch = case_dir / "artifacts" / "registry-runtime-contract-repo"
    scratch.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=scratch, check=True, capture_output=True, text=True, timeout=20)
    init_control_room(scratch)
    _record_artifact(state, scratch, root=root)
    _record_command(state, "devflow init (scratch registry-runtime-contract repo)", status="passed", output=relative_path(root, scratch))

    registry_path = scratch / ".devflow/agents/registry.yaml"
    atomic_write_text(
        registry_path,
        """version: 1
agents:
  remote-provider-worker:
    provider: openai
    model: gpt-5
    adapter: openai_chat
    role: frontier_planner_architect_reviewer
    tier: frontier
    default_mode: frontier_read_only
    execution_mode: automated
    workspace: isolated_task_workspace
    can_see:
      - task_packet
    allowed_reads:
      - "<task>/packet.json"
    forbidden_writes:
      - "<main_checkout>/**"
      - "<workspace>/**"
      - "<task>/task.yaml"
      - "<task>/events.jsonl"
      - "<task>/verification.json"
      - "<task>/merge-readiness.json"
      - ".git/**"
    can_run_shell: false
    can_use_network: true
    can_promote: false
    enabled: true
""",
    )
    _record_command(state, "write enabled remote-provider-worker registry fixture", status="passed")

    task = create_task(scratch, "Dogfood registry runtime contract")
    _record_command(state, "devflow task create 'Dogfood registry runtime contract' (scratch)", status="passed", output=task.id)

    list_payload = registry_json_payload(scratch)
    shell_show = agent_json_payload(scratch, "devflow-shell-worker")
    manual_show = agent_json_payload(scratch, "devflow-manual-codex-worker")
    remote_show = agent_json_payload(scratch, "remote-provider-worker")
    _record_command(state, "devflow agent list --json (scratch)", status="passed")
    _record_command(state, "devflow agent show devflow-shell-worker --json (scratch)", status="passed")
    _record_command(state, "devflow agent show remote-provider-worker --json (scratch)", status="passed")

    registry = load_agent_registry(scratch)
    shell_packet = build_agent_packet(task.id, registry.require_agent("devflow-shell-worker"), root=scratch).model_dump(mode="json")
    manual_packet = build_agent_packet(task.id, registry.require_agent("devflow-manual-codex-worker"), root=scratch).model_dump(mode="json")
    _record_command(state, f"devflow agent packet {task.id} devflow-shell-worker (scratch)", status="passed")
    _record_command(state, f"devflow agent packet {task.id} devflow-manual-codex-worker (scratch)", status="passed")

    shell_result = run_shell_task(
        scratch,
        task.id,
        ["/bin/sh", "-c", "printf registry-runtime-contract > registry-runtime.txt"],
        worker_adapter="devflow-shell-worker",
        timeout_seconds=20,
    )
    _record_command(
        state,
        f"devflow task run {task.id} --worker devflow-shell-worker -- /bin/sh -c 'printf ...' (scratch)",
        status=shell_result.status,
    )

    remote_refusal = ""
    try:
        run_shell_task(
            scratch,
            task.id,
            ["/bin/sh", "-c", "printf should-not-run > provider-ran.txt"],
            worker_adapter="remote-provider-worker",
            timeout_seconds=20,
        )
    except ValueError as exc:
        remote_refusal = str(exc)
    _record_command(
        state,
        f"devflow task run {task.id} --worker remote-provider-worker (scratch)",
        status="refused" if remote_refusal else "unexpected_success",
        output=remote_refusal,
    )

    agent_dir = scratch / ".devflow/tasks" / task.id / "agents" / "devflow-shell-worker"
    workspace_file = scratch / ".devflow/workspaces" / task.id / "registry-runtime.txt"
    root_file = scratch / "registry-runtime.txt"
    provider_ran_file = scratch / ".devflow/workspaces" / task.id / "provider-ran.txt"
    shell_contract = shell_show["runtime_contract"]
    manual_contract = manual_show["runtime_contract"]
    remote_contract = remote_show["runtime_contract"]
    list_shell = next(agent for agent in list_payload["agents"] if agent["id"] == "devflow-shell-worker")
    manual_instructions = manual_packet.get("manual_instructions") or ""
    manual_required = " ".join(manual_packet.get("required_outputs") or [])
    summary = {
        "scratch_repo": relative_path(root, scratch),
        "task_id": task.id,
        "list_shell_runtime_contract": list_shell["runtime_contract"],
        "shell_runtime_contract": shell_contract,
        "manual_runtime_contract": manual_contract,
        "remote_runtime_contract": remote_contract,
        "shell_packet_runtime_contract": shell_packet["runtime_contract"],
        "manual_packet_runtime_contract": manual_packet["runtime_contract"],
        "shell_agent_dir": relative_path(root, agent_dir),
        "shell_agent_evidence": {
            "packet_json": (agent_dir / "packet.json").exists(),
            "worker_log": (agent_dir / "logs" / "worker.log").exists(),
            "result_md": (agent_dir / "result.md").exists(),
        },
        "workspace_file_exists": workspace_file.exists(),
        "root_file_exists": root_file.exists(),
        "provider_ran_file_exists": provider_ran_file.exists(),
        "manual_packet_contracts": {
            "handoff": "handoff.md" in manual_instructions or "handoff.md" in " ".join(manual_packet.get("allowed_reads") or []),
            "result": "result.md" in manual_required and "result.md" in manual_instructions,
            "question": "questions.jsonl" in manual_required and "questions.jsonl" in manual_instructions,
            "failure": "worker_failed.json" in manual_required and "worker_failed.json" in manual_instructions,
        },
        "remote_refusal": remote_refusal,
        "provider_api_calls_attempted": False,
        "autonomous_routing_used": False,
        "auto_verification_used": False,
        "auto_promotion_used": False,
    }
    summary_path = case_dir / "artifacts" / "registry-runtime-contract-summary.json"
    atomic_write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _record_artifact(state, summary_path, root=root)

    commands_text = " ".join(str(command["command"]).lower() for command in state["commands_run"])
    forbidden_tokens = ("push-main", "promote", "verify", "route", "agent run")
    runtime_fields = {"execution_surface", "task_run_allowed", "agent_run_allowed", "packet_allowed", "refusal_reason", "next_command", "evidence_contract"}
    remote_refusal_matches_contract = (
        bool(remote_refusal)
        and remote_refusal == remote_contract["refusal_reason"]
        and remote_contract["task_run_allowed"] is False
        and remote_contract["execution_surface"] in {"agent_advise", "agent_propose_patch"}
    )
    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        2,
        workspace_file.exists() and not root_file.exists() and not provider_ran_file.exists(),
        "shell alias mutated only the isolated workspace and provider run did not execute",
    )
    _award(
        state,
        scores,
        failures,
        "B_pipeline_correctness",
        3,
        runtime_fields.issubset(shell_contract)
        and shell_contract["task_run_allowed"] is True
        and manual_contract["task_run_allowed"] is True
        and remote_contract["task_run_allowed"] is False
        and remote_contract["packet_allowed"] is True,
        "list/show runtime contracts exposed run and packet eligibility",
    )
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        3,
        all(summary["shell_agent_evidence"].values())
        and shell_packet["runtime_contract"]["execution_surface"] == "task_run"
        and all(summary["manual_packet_contracts"].values()),
        "shell and manual packets exposed evidence contracts",
    )
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        2,
        remote_refusal_matches_contract
        and not summary["provider_api_calls_attempted"]
        and not any(token in commands_text for token in forbidden_tokens),
        "remote/provider-backed agent refused before provider execution",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_model_audition_evidence(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    scratch = case_dir / "artifacts" / "model-audition-repo"
    _init_git_native_dogfood_repo(scratch)
    init_control_room(scratch)
    _record_artifact(state, scratch, root=root)
    _record_command(state, "git init scratch model-audition dogfood repo", status="passed", output=relative_path(root, scratch))

    task = create_task(scratch, "Dogfood model audition evidence")
    task_yaml_before = (scratch / ".devflow" / "tasks" / task.id / "task.yaml").read_text(encoding="utf-8")
    discovery = _dogfood_audition_discovery_report()
    dry_run = write_model_audition_dry_run_plan(
        scratch,
        task.id,
        "review-debug",
        discovery_report=discovery,
    )
    _record_command(
        state,
        f"devflow agent audition {task.id} --job review-debug --dry-run --json (fixture)",
        status=dry_run["status"],
        output=dry_run["plan_path"],
    )

    def fixture_run_profile(**kwargs: Any) -> dict[str, Any]:
        profile_id = str(kwargs["profile_id"])
        response_text = _dogfood_audition_response(profile_id, task_id=task.id, task_title=task.title, task_status=task.status)
        evidence = write_worker_evidence(
            root=scratch,
            worker_type="local_model_worker_pool",
            profile_id=profile_id,
            worker_id=profile_id,
            task_id=task.id,
            run_id=f"dogfood-{profile_id}",
            packet_text="deterministic model audition packet",
            raw_output=response_text,
            response_text=response_text,
            model=profile_id,
            adapter="ollama_chat",
            adapter_maturity="local_patch_runtime",
            permission_mode="read_only",
            hermes_delegable=True,
            runtime="dogfood_fixture",
            status="success",
            started_at="2026-06-15T00:00:00+00:00",
            quality_notes="dogfood fixture",
            quality_score=0.9,
        )
        return {
            "task_id": task.id,
            "profile_id": profile_id,
            "worker_id": profile_id,
            "status": "success",
            "run_id": evidence.run_id,
            "model": profile_id,
            "adapter": "ollama_chat",
            "evidence_dir": relative_path(scratch, evidence.evidence_dir),
            "run_metadata_path": relative_path(scratch, evidence.run_metadata_path),
            "response_path": relative_path(scratch, evidence.response_path),
        }

    execute = execute_model_audition(
        scratch,
        task.id,
        "review-debug",
        discovery_report=discovery,
        run_profile=fixture_run_profile,
    )
    _record_command(
        state,
        f"devflow agent audition {task.id} --job review-debug --execute --json (fixture)",
        status=execute["status"],
        output=execute["report_path"],
    )

    audition_dir = scratch / ".devflow" / "tasks" / task.id / "model-auditions" / "execute-review-debug"
    runs = json.loads((audition_dir / "runs.json").read_text(encoding="utf-8"))
    scorecard = json.loads((audition_dir / "scorecard.json").read_text(encoding="utf-8"))
    report_exists = (audition_dir / "report.md").exists()
    ranking = scorecard["advisory_ranking"]
    task_yaml_after = (scratch / ".devflow" / "tasks" / task.id / "task.yaml").read_text(encoding="utf-8")
    git_state = inspect_git_state(scratch)
    proposal_patches = sorted(str(path) for path in (scratch / ".devflow" / "tasks" / task.id).rglob("proposal.patch"))
    summary = {
        "scratch_repo": relative_path(root, scratch),
        "dry_run_plan_path": dry_run["plan_path"],
        "execute_paths": {
            "plan": execute["plan_path"],
            "runs": execute["runs_path"],
            "scorecard": execute["scorecard_path"],
            "report": execute["report_path"],
        },
        "selected_candidate_count": len(dry_run["selected_candidates"]),
        "run_count": len(runs["runs"]),
        "top_profile": ranking[0]["profile_id"] if ranking else None,
        "false_claim_flagged": any("false_claim" in item.get("deductions", []) for item in ranking),
        "task_yaml_unchanged": task_yaml_before == task_yaml_after,
        "git_dirty": git_state.dirty,
        "proposal_patches": proposal_patches,
    }
    summary_path = case_dir / "artifacts" / "model-audition-summary.json"
    atomic_write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _record_artifact(state, summary_path, root=root)

    commands_text = " ".join(str(command["command"]).lower() for command in state["commands_run"])
    forbidden_tokens = ("openai", "anthropic", "gemini", "push-main", "promote", "verify")
    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        2,
        task_yaml_before == task_yaml_after
        and not git_state.dirty
        and not proposal_patches
        and not any(token in commands_text for token in forbidden_tokens),
        "model audition preserved task/source state and avoided promotion-adjacent commands",
    )
    _award(
        state,
        scores,
        failures,
        "B_pipeline_correctness",
        3,
        dry_run["status"] == "planned"
        and execute["status"] == "completed"
        and len(dry_run["selected_candidates"]) <= 3
        and len(runs["runs"]) == len(dry_run["selected_candidates"]),
        "dry-run and execute produced bounded candidate/run evidence",
    )
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        4,
        report_exists
        and ranking
        and ranking[0]["profile_id"] == "local-gemma4-qat"
        and summary["false_claim_flagged"]
        and scorecard["will_update_routing_policy"] is False,
        "scorecard ranked grounded output first and flagged false claims",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_success_empty(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    empty = _worker_outcome(
        task_id=f"dogfood-empty-{run_id}",
        source_path="manual-empty-result",
        outcome="no_useful_result",
        files_touched=[],
        tool_status="success_empty",
        human_review_required=True,
        notes=["empty result must not be treated as useful success"],
    )
    useful = _worker_outcome(
        task_id=f"dogfood-useful-{run_id}",
        source_path="manual-useful-result",
        outcome="completed",
        files_touched=["workspace/result.txt"],
        tool_status="success_with_result",
        human_review_required=False,
        notes=["useful result includes source path and command evidence"],
    )
    empty_errors = validate_worker_outcome(root, empty)
    useful_errors = validate_worker_outcome(root, useful)
    empty_score = _worker_usefulness_score(empty)
    useful_score = _worker_usefulness_score(useful)
    atomic_write_text(case_dir / "artifacts" / "empty-outcome.json", json.dumps(empty, indent=2, sort_keys=True) + "\n")
    atomic_write_text(case_dir / "artifacts" / "useful-outcome.json", json.dumps(useful, indent=2, sort_keys=True) + "\n")
    _record_artifacts(
        state,
        [
            case_dir / "artifacts" / "empty-outcome.json",
            case_dir / "artifacts" / "useful-outcome.json",
        ],
        root=root,
    )
    _record_command(state, "validate success_empty outcome in-process", status="passed" if not empty_errors else "failed")
    _record_command(state, "validate success_with_result outcome in-process", status="passed" if not useful_errors else "failed")
    _record_lesson(state, f"success_empty usefulness score {empty_score}; success_with_result score {useful_score}")

    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(state, scores, failures, "B_pipeline_correctness", 2, not empty_errors and not useful_errors, "both outcome shapes validate")
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        2,
        empty["tool_results"][0]["status"] == "success_empty" and empty["outcome"] == "no_useful_result",
        "success_empty stayed no_useful_result",
    )
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        3,
        empty_score < useful_score,
        "empty result is scored below useful result",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_plan_only_unsafe_git(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    task = create_task(root, "Dogfood plan-only unsafe Git state")
    _record_command(state, f"devflow task create {task.title!r}", status="passed", output=task.id)

    marker = root / f".dogfood-dirty-marker-{run_id}"
    marker_created = False
    cleanup_status = "not_required"
    try:
        marker.write_text("temporary dogfood dirty marker\n", encoding="utf-8")
        marker_created = True
        _record_command(state, f"create {marker.name}", status="passed")
        plan = create_orchestration_plan(root, task.id, plan_only=True)
        _record_command(state, f"devflow task orchestrate {task.id} --plan-only", status="passed")
    finally:
        if marker_created:
            cleanup_ok, cleanup_warning = _cleanup_file(marker)
            cleanup_status = _set_cleanup_status(
                state,
                "marker_removed" if cleanup_ok else f"cleanup_failed: {marker.name}",
                warning=cleanup_warning,
            )

    active = {item["condition"] for item in plan.get("stop_conditions", []) if item.get("active")}
    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(state, scores, failures, "A_safety_git_discipline", 3, "dirty_git_tree" in active, "dirty Git tree stop condition was active")
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        2,
        plan.get("parallelism_allowed") is False and plan.get("recommended_execution") in {"human_review_first", "sequential"},
        "unsafe Git state blocked worker parallelism",
    )
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        3,
        cleanup_status == "marker_removed" and not marker.exists(),
        "temporary dirty marker cleanup is visible",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_failed_verification(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    task = create_task(root, "Dogfood failed verification recovery")
    _record_command(state, f"devflow task create {task.title!r}", status="passed", output=task.id)

    run_shell_task(root, task.id, ["/bin/sh", "-c", "printf actual > recovery.txt"], timeout_seconds=10)
    _record_command(state, f"devflow task run {task.id} --worker shell -- write recovery fixture", status="passed")

    verified = verify_task(
        root,
        task.id,
        ["/bin/sh", "-c", 'test "$(cat recovery.txt)" = expected'],
        timeout_seconds=10,
    )
    _record_command(
        state,
        f"devflow task verify {task.id} --shell failing check",
        status=verified.verification_status,
        exit_code=verified.verification_exit_code,
    )
    readiness_errors = promotion_readiness_errors(verified, root / ".devflow" / "tasks" / task.id)
    atomic_write_text(
        case_dir / "artifacts" / "promotion-readiness-errors.json",
        json.dumps(readiness_errors, indent=2) + "\n",
    )
    _record_artifact(state, case_dir / "artifacts" / "promotion-readiness-errors.json", root=root)

    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        4,
        readiness_errors and verified.status == "verification_failed",
        "failed verification blocked promotion readiness",
    )
    _award(state, scores, failures, "B_pipeline_correctness", 3, verified.verification_exit_code != 0, "failed verification was recorded")
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        6,
        any("verification" in error for error in readiness_errors),
        "readiness errors explain the next safe action",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_knowledge_capture(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    validation_path = shared.get("unsafe_validation_path")
    if not validation_path or not (root / validation_path).exists():
        validation_path = _create_validation_failure(root, run_id, case_dir, state)
    item = capture_from_validation(root, root / validation_path)
    _record_command(state, f"devflow knowledge capture --from-validation {validation_path}", status="passed", output=item["id"])
    results = search_knowledge(root, "validation")
    _record_command(state, "devflow knowledge search validation", status="passed", output=str(len(results)))
    _record_artifact(state, f".devflow/knowledge/{item['id']}/knowledge.json")

    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        3,
        bool(item.get("linked_artifacts")) and validation_path in item.get("linked_artifacts", []),
        "validation source artifact was retained",
    )
    _award(state, scores, failures, "F_knowledge_capture", 4, item["status"] == "proposed", "knowledge remains proposed")
    _award(
        state,
        scores,
        failures,
        "F_knowledge_capture",
        3,
        any(found["id"] == item["id"] for found in results),
        "knowledge search finds the proposed item",
    )
    _award(
        state,
        scores,
        failures,
        "F_knowledge_capture",
        3,
        item.get("promoted_at") is None and item.get("rejected_at") is None,
        "capture did not auto-promote or reject knowledge",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_handoff_resume(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    task = create_task(root, "Dogfood handoff resume")
    _record_command(state, f"devflow task create {task.title!r}", status="passed", output=task.id)
    run_shell_task(root, task.id, ["/bin/sh", "-c", "printf handoff > handoff.txt"], timeout_seconds=10)
    _record_command(state, f"devflow task run {task.id} --worker shell -- write handoff fixture", status="passed")
    verified = verify_task(root, task.id, ["/bin/sh", "-c", "test -s handoff.txt"], timeout_seconds=10)
    _record_command(state, f"devflow task verify {task.id} --shell handoff check", status=verified.verification_status)

    fresh = get_task(root, task.id)
    task_path = root / ".devflow" / "tasks" / task.id
    handoff_path = case_dir / "artifacts" / "handoff.md"
    handoff = "\n".join(
        [
            "# Dogfood Handoff",
            "",
            f"task_id: {fresh.id}",
            f"task_status: {fresh.status}",
            f"verification_status: {fresh.verification_status}",
            f"task_artifacts: {relative_path(root, task_path)}",
            f"verification_artifact: {relative_path(root, task_path / 'verification.json')}",
            "current_state: reload canonical task files and inspect dogfood case-result.yaml",
            "next_safe_action: inspect report.md and decide whether to promote a separate human-reviewed task",
            "hidden_state_required: no",
            "",
        ]
    )
    atomic_write_text(handoff_path, handoff)
    _record_artifact(state, handoff_path, root=root)

    scores: dict[str, int] = {}
    failures: list[str] = []
    handoff_text = handoff_path.read_text(encoding="utf-8")
    _award(state, scores, failures, "B_pipeline_correctness", 3, fresh.status == "verified", "fresh task load is verified")
    _award(
        state,
        scores,
        failures,
        "C_context_efficiency",
        2,
        "hidden_state_required: no" in handoff_text,
        "resume uses files instead of hidden state",
    )
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        2,
        all(token in handoff_text for token in ("task_id:", "task_artifacts:", "next_safe_action:")),
        "handoff includes task, artifacts, state, and next action",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_parallelism_docs_test(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    task = create_task(root, "Update docs and tests for dogfood split")
    _record_command(state, f"devflow task create {task.title!r}", status="passed", output=task.id)
    plan = create_orchestration_plan(root, task.id, plan_only=True)
    _record_command(state, f"devflow task orchestrate {task.id} --plan-only", status="passed")
    if plan.get("parallelism_allowed") is not True:
        _record_warning(
            state,
            "parallelism was conservatively blocked by current repo guardrails; role/context checks still ran"
        )

    roles = plan.get("roles") if isinstance(plan.get("roles"), list) else []
    context_layers = {role.get("context_layer") for role in roles if isinstance(role, dict)}
    all_no_promote = all(role.get("can_promote") is False for role in roles if isinstance(role, dict))
    devmode_required = all(role.get("devmode_skills_required") for role in roles if isinstance(role, dict))
    plan_only_note = any("no workers" in note and "providers" in note for note in plan.get("notes", []))

    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "C_context_efficiency",
        3,
        len(context_layers) >= 3 and all_no_promote and devmode_required,
        "plan records conservative role layers with no promotion rights",
    )
    _award(
        state,
        scores,
        failures,
        "G_performance_lightweight",
        1,
        plan_only_note,
        "plan-only orchestration did not execute providers or workers",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_central_schema_risk(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    task = create_task(root, "Rewrite whole repo migration and disable guardrail")
    _record_command(state, f"devflow task create {task.title!r}", status="passed", output=task.id)
    plan = create_orchestration_plan(root, task.id, plan_only=True)
    _record_command(state, f"devflow task orchestrate {task.id} --plan-only", status="passed")
    active = {item["condition"] for item in plan.get("stop_conditions", []) if item.get("active")}

    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        3,
        plan.get("risk_level") == "high" and plan.get("parallelism_allowed") is False,
        "high-risk central change refused unsafe parallelism",
    )
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        2,
        plan.get("recommended_execution") == "human_review_first"
        and {"expected_edits_overlap_heavily", "architectural_risk_escalates"} & active,
        "plan requires human review for central schema/refactor risk",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_simple_scheduler_parallel_coordination(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    scratch = case_dir / "artifacts" / "simple-scheduler-repo"
    _init_git_native_dogfood_repo(scratch)
    init_control_room(scratch)
    _record_artifact(state, scratch, root=root)
    _record_command(
        state,
        "git init scratch simple-scheduler dogfood repo",
        status="passed",
        output=relative_path(root, scratch),
    )

    goal_path = scratch / ".devflow" / "goals" / "G-0001"
    goal_path.mkdir(parents=True, exist_ok=True)
    atomic_write_text(goal_path / "goal.yaml", "id: G-0001\ntitle: Scheduler dogfood\nstate: active\n")
    atomic_write_text(
        goal_path / "goal-state.yaml",
        "schema_version: 1\ngoal_id: G-0001\nlifecycle: active\nreason: dogfood scheduler case\n",
    )
    atomic_write_text(
        goal_path / "task-slices.yaml",
        """
task_slices:
  - task_id: TS-0001
    title: Ready scheduler lane one
    summary: Can start independently.
    parallel_safe: true
    shared_files: [src/a.py]
    risk: low
    execution_mode: AFK
  - task_id: TS-0002
    title: Ready scheduler lane two
    summary: Can start independently beside TS-0001.
    parallel_safe: true
    shared_files: [src/b.py]
    risk: low
    execution_mode: AFK
  - task_id: TS-0003
    title: Dependency blocked scheduler lane
    summary: Waits for TS-0001.
    blocked_by: [TS-0001]
    parallel_safe: true
    shared_files: [src/c.py]
    risk: medium
    execution_mode: HITL
""".lstrip(),
    )
    atomic_write_text(goal_path / "linked-tasks.yaml", "linked_tasks: {}\n")

    retry_task = create_task(scratch, "Dogfood scheduler retry task")
    retry_record = get_task(scratch, retry_task.id)
    retry_record.status = "verification_failed"
    retry_record.verification_status = "failed"
    retry_record.verification_command = "pytest tests/test_retry.py"
    retry_record.updated_at = utc_now()
    save_task(scratch / ".devflow" / "tasks" / retry_record.id, retry_record)

    stale_task = create_task(scratch, "Dogfood scheduler stale running task")
    stale_record = get_task(scratch, stale_task.id)
    stale_record.status = "running"
    stale_record.started_at = utc_now() - timedelta(seconds=900)
    stale_record.updated_at = stale_record.started_at
    stale_record.timeout_seconds = 60
    save_task(scratch / ".devflow" / "tasks" / stale_record.id, stale_record)

    blocked_task = create_task(scratch, "Dogfood scheduler blocked question task")
    agent_dir = scratch / ".devflow" / "tasks" / blocked_task.id / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True, exist_ok=True)
    with (agent_dir / "questions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "type": "blocked_question",
                    "task_id": blocked_task.id,
                    "agent_id": "devflow-manual-codex-worker",
                    "question": "Which retry path should this dogfood task use?",
                },
                sort_keys=True,
            )
            + "\n"
        )

    snapshot_before = build_scheduler_snapshot(scratch)
    retry = request_scheduler_retry(scratch, retry_task.id, reason="dogfood retry evidence")
    snapshot_after = build_scheduler_snapshot(scratch)
    summary = {
        "before": snapshot_before.model_dump(mode="json"),
        "retry": retry.model_dump(mode="json"),
        "after": snapshot_after.model_dump(mode="json"),
    }
    summary_path = case_dir / "artifacts" / "simple-scheduler-summary.json"
    atomic_write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _record_artifact(state, summary_path, root=root)
    _record_command(
        state,
        "devflow scheduler status --json (fixture)",
        status="passed",
        output=relative_path(root, summary_path),
    )
    _record_command(
        state,
        "devflow scheduler retry <task-id> --reason 'dogfood retry evidence' --json",
        status="passed",
    )

    retry_after = get_task(scratch, retry_task.id)
    retry_preserved = (
        retry_after.status == "verification_failed"
        and retry_after.verification_status == "failed"
        and retry_after.verification_command == "pytest tests/test_retry.py"
    )
    commands_clean = _commands_have_no_provider_calls(state["commands_run"])
    scores: dict[str, int] = {}
    failures: list[str] = []
    counts = snapshot_after.counts
    _award(
        state,
        scores,
        failures,
        "B_pipeline_correctness",
        2,
        counts.get("ready", 0) >= 2
        and counts.get("blocked", 0) >= 2
        and counts.get("stale", 0) >= 1
        and counts.get("needs_retry", 0) >= 1,
        "scheduler exposed ready blocked stale and retry work",
    )
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        3,
        snapshot_after.batches
        and any(batch.next_safe_action == "devflow freshness create-batch G-0001 PB-0001" for batch in snapshot_after.batches)
        and (scratch / retry.retry_request_path).exists(),
        "scheduler wrote reviewable batch and retry evidence",
    )
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        5,
        retry_preserved and commands_clean,
        "retry request preserved prior task evidence",
    )
    if commands_clean:
        _record_lesson(state, "no background scheduler or provider calls were introduced")
    else:
        failures.append("no background scheduler or provider calls were introduced")
    return _finalize_case(root, case, state, scores, failures)


def _case_question_blocker_resume_loop(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    scratch = case_dir / "artifacts" / "question-resume-repo"
    _init_git_native_dogfood_repo(scratch)
    init_control_room(scratch)
    _record_artifact(state, scratch, root=root)

    task = create_task(scratch, "Dogfood question blocker")
    task.status = "blocked"
    save_task(scratch / ".devflow" / "tasks" / task.id, task)
    agent_dir = scratch / ".devflow" / "tasks" / task.id / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True, exist_ok=True)
    source = agent_dir / "questions.jsonl"
    source.write_text(
        (
            '{"type":"blocked_question","task_id":"task-0001","agent_id":"devflow-manual-codex-worker",'
            '"question":"Which API should I preserve?","blocking_reason":"Need human decision."}\n'
            "{bad json}\n"
        ),
        encoding="utf-8",
    )
    before_source = source.read_text(encoding="utf-8")

    snapshot = build_question_snapshot(scratch)
    question = next((item for item in snapshot.questions if item.status == "open"), None)
    answered = answer_question(scratch, question.question_id, answer="Preserve the stable API.") if question else None
    scheduler = build_scheduler_snapshot(scratch)
    after_source = source.read_text(encoding="utf-8")

    summary = {
        "question_snapshot": snapshot.model_dump(mode="json"),
        "answered": answered.model_dump(mode="json") if answered else None,
        "scheduler": scheduler.model_dump(mode="json"),
        "source_preserved": before_source == after_source,
    }
    summary_path = case_dir / "artifacts" / "question-resume-summary.json"
    atomic_write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _record_artifact(state, summary_path, root=root)
    if answered and answered.answer_path:
        _record_artifact(state, scratch / answered.answer_path, root=scratch)
    _record_command(
        state,
        "devflow question list --json (fixture)",
        status="passed",
        output=relative_path(root, summary_path),
    )
    _record_command(
        state,
        "devflow question answer <question-id> --answer '<answer>' --json",
        status="passed" if answered else "failed",
    )
    _record_command(
        state,
        "devflow scheduler status --json (fixture)",
        status="passed",
    )

    answer_record_exists = bool(answered and answered.answer_path and (scratch / answered.answer_path).exists())
    mirror_exists = bool(
        answered
        and (scratch / ".devflow" / "tasks" / task.id / "question-answers" / f"{answered.question_id}.json").exists()
    )
    events_text = (scratch / ".devflow" / "tasks" / task.id / "events.jsonl").read_text(encoding="utf-8")
    commands_clean = _commands_have_no_provider_calls(state["commands_run"])
    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "B_pipeline_correctness",
        2,
        question is not None
        and question.question_id.startswith("Q-task-0001-")
        and snapshot.counts.get("open") == 1
        and bool(snapshot.warnings),
        "question list exposed deterministic open blocker",
    )
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        2,
        bool(answered)
        and answer_record_exists
        and mirror_exists
        and before_source == after_source
        and "question_answered" in events_text,
        "answer preserved source question evidence",
    )
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        4,
        scheduler.counts.get("blocked", 0) == 0
        and answered is not None
        and answered.recommended_resume_command == f"devflow task next-action {task.id}"
        and commands_clean,
        "no worker resume or provider call was executed by question commands",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_operator_readiness_reconciliation(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    scratch = case_dir / "artifacts" / "operator-readiness-repo"
    _init_git_native_dogfood_repo(scratch)
    init_control_room(scratch)
    _record_artifact(state, scratch, root=root)

    project_dir = scratch / ".devflow" / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        project_dir / "project.yaml",
        yaml.safe_dump(
            {
                "schema_version": 1,
                "id": "operator-console",
                "project_id": "operator-console",
                "name": "Operator Console",
                "root_path": scratch.as_posix(),
            },
            sort_keys=False,
        ),
    )
    goal_path = scratch / ".devflow" / "goals" / "G-0004"
    goal_path.mkdir(parents=True, exist_ok=True)
    atomic_write_text(goal_path / "goal.yaml", "id: G-0004\ntitle: Operator readiness dogfood\nstate: active\n")
    atomic_write_text(
        goal_path / "task-slices.yaml",
        yaml.safe_dump(
            {
                "task_slices": [
                    {
                        "task_id": "TS-0002",
                        "title": "Reconcile operating-layer state",
                        "summary": "Align counts, lifecycle blockers, warnings, and next actions.",
                        "parallel_safe": True,
                        "shared_files": ["src/devflow/control_room/operator_readiness.py"],
                        "risk": "low",
                        "execution_mode": "AFK",
                    }
                ]
            },
            sort_keys=False,
        ),
    )
    atomic_write_text(goal_path / "linked-tasks.yaml", "linked_tasks: {}\n")

    generated = create_task(scratch, "G-0004 • Slice 2")
    descriptive = create_task(scratch, "Implement lifecycle readiness gate")
    atomic_write_text(
        scratch / ".devflow" / "tasks" / generated.id / "goal-link.yaml",
        yaml.safe_dump(
            {
                "schema_version": 1,
                "goal_id": "G-0004",
                "goal_path": ".devflow/goals/G-0004",
                "slice_id": "TS-0002",
                "slice_source_path": ".devflow/goals/G-0004/task-slices.yaml",
                "created_from_goal_slice": True,
            },
            sort_keys=False,
        ),
    )
    agent_dir = scratch / ".devflow" / "tasks" / generated.id / "agents" / "devflow-manual-codex-worker"
    agent_dir.mkdir(parents=True, exist_ok=True)
    with (agent_dir / "questions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "type": "blocked_question",
                    "task_id": generated.id,
                    "agent_id": "devflow-manual-codex-worker",
                    "question": "Should lifecycle repair happen before dispatch?",
                },
                sort_keys=True,
            )
            + "\n"
        )

    freshness_dir = scratch / ".devflow" / "freshness"
    freshness_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        freshness_dir / "latest.json",
        json.dumps(
            {
                "schema_version": 1,
                "status": "ok",
                "goal_loop": [
                    {
                        "goal_id": "G-0004",
                        "title": "Operator readiness dogfood",
                        "goal_state": "active",
                        "loop_state": "ready_for_parallel_task_creation",
                        "next_action": "Parallel batch PB-0001: devflow freshness create-batch G-0004 PB-0001",
                        "parallel_batches": [
                            {
                                "batch_id": "PB-0001",
                                "lane_ids": ["TS-0002"],
                                "commands": ["devflow goal create-task G-0004 TS-0002"],
                                "shared_files": ["src/devflow/control_room/operator_readiness.py"],
                                "reason": "stale recommendation captured before lifecycle state disappeared",
                            }
                        ],
                    }
                ],
                "next_action": "Continue.",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )

    status = build_control_room_status(scratch)
    scheduler = build_scheduler_snapshot(scratch).model_dump(mode="json")
    supervisor = build_supervisor_packet(scratch)
    operating = build_operating_layer_snapshot(scratch).model_dump(mode="json")
    surfaces = {
        "status": status["operator_readiness"],
        "scheduler": scheduler["operator_readiness"],
        "supervisor": supervisor["operator_readiness"],
        "operating_layer": operating["operator_readiness"],
    }
    summary = {
        "generated_task_id": generated.id,
        "descriptive_task_id": descriptive.id,
        "surface_counts": {name: payload["counts"] for name, payload in surfaces.items()},
        "surface_next_actions": {name: payload["next_safe_action"] for name, payload in surfaces.items()},
        "scheduler_next_safe_action": scheduler["next_safe_action"],
        "status_scheduler_next_safe_action": status["scheduler"]["next_safe_action"],
        "operating_layer_next_action": operating["next_action"],
        "status_tasks": surfaces["status"]["tasks"],
        "warnings": surfaces["status"]["warnings"],
    }
    summary_path = case_dir / "artifacts" / "operator-readiness-summary.json"
    atomic_write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _record_artifact(state, summary_path, root=root)
    _record_command(state, "devflow status --json (fixture)", status="passed", output=relative_path(root, summary_path))
    _record_command(state, "devflow scheduler status --json (fixture)", status="passed")
    _record_command(state, "devflow supervisor packet --json (fixture)", status="passed")
    _record_command(state, "devflow operating-layer snapshot --json (fixture)", status="passed")

    surface_counts_agree = len({json.dumps(payload["counts"], sort_keys=True) for payload in surfaces.values()}) == 1
    lifecycle_counts = all(
        payload["counts"].get("worker_ready") == 1 and payload["counts"].get("lifecycle_blocked") == 1
        for payload in surfaces.values()
    )
    repair_priority = all(
        payload["next_safe_action"]["kind"] == "repair_goal_lifecycle"
        and str(payload["next_safe_action"]["command"]).startswith("devflow goal activate G-0004")
        for payload in surfaces.values()
    )
    repair_priority = (
        repair_priority
        and str(status["scheduler"]["next_safe_action"]).startswith("devflow goal activate G-0004")
        and str(scheduler["next_safe_action"]).startswith("devflow goal activate G-0004")
        and str(operating["next_action"]["command"]).startswith("devflow goal activate G-0004")
    )
    generated_projection = next(item for item in surfaces["status"]["tasks"] if item["task_id"] == generated.id)
    plain_label = (
        generated_projection["display"]["primary"] == "Reconcile operating-layer state"
        and generated_projection["display"]["raw_title"] == "G-0004 • Slice 2"
        and generated_projection["display"]["ids"]["goal_id"] == "G-0004"
    )
    stale_warning = any(
        warning.get("code") == "stale_freshness_directive"
        and warning.get("blocked_by") == "goal_lifecycle_missing"
        for warning in surfaces["status"]["warnings"]
    )
    commands_clean = _commands_have_no_provider_calls(state["commands_run"])

    close_task(scratch, generated.id, outcome="evidence-only", reason="dogfood operator readiness evidence captured")
    close_task(scratch, descriptive.id, outcome="evidence-only", reason="dogfood operator readiness evidence captured")

    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "B_pipeline_correctness",
        2,
        surface_counts_agree and lifecycle_counts,
        "operator surfaces agreed on readiness counts",
    )
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        3,
        repair_priority and stale_warning,
        "lifecycle repair outranked stale dispatch guidance",
    )
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        2,
        plain_label and commands_clean,
        "plain descriptive task labels remained primary",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_intent_scaffold_approval_path(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    scratch = case_dir / "artifacts" / "intent-scaffold-repo"
    _init_git_native_dogfood_repo(scratch)
    init_control_room(scratch)
    _record_artifact(state, scratch, root=root)
    _record_command(
        state,
        "git init scratch intent-scaffold dogfood repo",
        status="passed",
        output=relative_path(root, scratch),
    )

    commit_count_before = _git_commit_count(scratch)
    idea = capture_idea(
        scratch,
        "build a search plugin",
        title="Build search plugin",
        source="dogfood",
        tags=["intent"],
    )
    _record_command(state, "devflow idea capture 'build a search plugin'", status="passed", output=idea["id"])

    before_preview = _intent_scaffold_file_snapshot(scratch)
    preview = preview_scaffold_from_idea(scratch, idea["id"])
    after_preview = _intent_scaffold_file_snapshot(scratch)
    dry_run_changed = sorted(set(after_preview) - set(before_preview))
    _record_command(
        state,
        f"devflow idea scaffold-goal {idea['id']} --dry-run",
        status=preview["status"],
    )

    written = write_scaffold_from_idea(scratch, idea["id"])
    scaffold_json = scratch / ".devflow" / "ideas" / idea["id"] / "scaffold-goal.json"
    scaffold_md = scratch / ".devflow" / "ideas" / idea["id"] / "scaffold-goal.md"
    _record_artifacts(state, [scaffold_json, scaffold_md], root=root)
    _record_command(
        state,
        f"devflow idea scaffold-goal {idea['id']}",
        status=written["status"],
        output=relative_path(root, scaffold_json),
    )

    classify_idea(
        scratch,
        idea["id"],
        maturity="goal_ready",
        note="Dogfood scaffold reviewed.",
        tags=["intent"],
    )
    _record_command(
        state,
        f"devflow idea classify {idea['id']} --maturity goal_ready",
        status="passed",
    )
    promote_idea(
        scratch,
        idea["id"],
        target="goal",
        rationale="Human reviewed scaffold evidence.",
    )
    _record_command(
        state,
        f"devflow idea promote {idea['id']} --to goal",
        status="passed",
    )

    created = create_goal_from_idea(scratch, idea["id"])
    goal_path = scratch / created.created_path
    _record_artifact(state, goal_path, root=root)
    _record_command(
        state,
        f"devflow idea create-goal {idea['id']}",
        status="passed",
        output=created.created_id,
    )

    slices = load_goal_task_slices(scratch, created.created_id)
    _record_command(
        state,
        f"devflow goal slices {created.created_id}",
        status="passed",
        output=f"{len(slices)} slices",
    )

    canonical_tasks = list_tasks(scratch)
    prd_path = goal_path / "prd.md"
    risks_path = goal_path / "risks.md"
    handoff_path = goal_path / "handoff.md"
    context_path = goal_path / "context-pointers.yaml"
    link_path = goal_path / "idea-link.yaml"
    open_questions_path = goal_path / "open-questions.yaml"
    task_slices_path = goal_path / "task-slices.yaml"
    prd = prd_path.read_text(encoding="utf-8") if prd_path.exists() else ""
    risks = risks_path.read_text(encoding="utf-8") if risks_path.exists() else ""
    handoff = handoff_path.read_text(encoding="utf-8") if handoff_path.exists() else ""
    context = yaml.safe_load(context_path.read_text(encoding="utf-8")) if context_path.exists() else {}
    link = yaml.safe_load(link_path.read_text(encoding="utf-8")) if link_path.exists() else {}
    open_questions = yaml.safe_load(open_questions_path.read_text(encoding="utf-8")) if open_questions_path.exists() else {}
    slice_ids = [slice_.task_id for slice_ in slices]
    commands_clean = _intent_scaffold_commands_avoid_execution(state["commands_run"])
    commit_count_after = _git_commit_count(scratch)
    tracked_status = _git_short_status(scratch)
    no_execution = (
        commands_clean
        and canonical_tasks == []
        and commit_count_after == commit_count_before
        and tracked_status == []
    )

    summary = {
        "idea_id": idea["id"],
        "preview_status": preview["status"],
        "written_status": written["status"],
        "scaffold_json": relative_path(root, scaffold_json),
        "scaffold_markdown": relative_path(root, scaffold_md),
        "dry_run_changed_files": dry_run_changed,
        "goal_id": created.created_id,
        "goal_path": created.created_path,
        "task_slice_ids": slice_ids,
        "canonical_task_ids": [task.id for task in canonical_tasks],
        "commands_clean": commands_clean,
        "commit_count_before": commit_count_before,
        "commit_count_after": commit_count_after,
        "tracked_git_status": tracked_status,
        "source_scaffold_path": link.get("source_scaffold_path"),
    }
    summary_path = case_dir / "artifacts" / "intent-scaffold-summary.json"
    atomic_write_text(summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _record_artifact(state, summary_path, root=root)

    scaffold_written = (
        preview.get("status") == "ready_for_review"
        and written.get("status") == "ready_for_review"
        and dry_run_changed == []
        and scaffold_json.exists()
        and scaffold_md.exists()
        and scaffold_json.stat().st_mtime_ns <= goal_path.stat().st_mtime_ns
    )
    goal_consumed_scaffold = (
        created.created_id == "G-0001"
        and slice_ids == ["TS-0001", "TS-0002"]
        and link.get("source_scaffold_path") == ".devflow/ideas/I-0001/scaffold-goal.json"
        and not canonical_tasks
    )
    artifacts_reviewable = (
        "Canonical goal/task state is created only after explicit human approval." in prd
        and "TBD" not in prd
        and "Confirm the plugin boundary" in risks
        and "PRODUCT_NORTH_STAR.md" in (context.get("required_context") or [])
        and open_questions.get("implementation_blocked") is False
    )
    slices_reviewable = (
        task_slices_path.exists()
        and len(slices) == 2
        and slices[0].verification_policy.get("commands")
        and slices[0].promotion_allowed is False
        and f"devflow goal create-task {created.created_id} TS-0001" in handoff
    )

    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "B_pipeline_correctness",
        2,
        scaffold_written,
        "intent scaffold wrote review evidence before goal creation",
    )
    _award(
        state,
        scores,
        failures,
        "B_pipeline_correctness",
        2,
        goal_consumed_scaffold,
        "goal creation consumed scaffold task slices without running workers",
    )
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        2,
        artifacts_reviewable,
        "scaffold goal artifacts retained reviewable acceptance criteria",
    )
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        2,
        slices_reviewable and summary_path.exists(),
        "intent scaffold evidence remained inspectable",
    )
    _award(
        state,
        scores,
        failures,
        "E_recovery_failure_handling",
        2,
        no_execution,
        "no provider calls, worker runs, verification, task promotion, commits, or pushes were performed",
    )
    return _finalize_case(root, case, state, scores, failures)


def _case_operating_layer_visual_qa(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    task = create_task(root, "Dogfood operating layer visual QA")
    _record_command(state, f"devflow task create {task.title!r}", status="passed", output=task.id)

    run_shell_task(root, task.id, ["/bin/sh", "-c", "printf visual > visual.txt"], timeout_seconds=10)
    _record_command(state, f"devflow task run {task.id} --worker shell -- write visual fixture", status="passed")

    verified = verify_task(root, task.id, ["/bin/sh", "-c", "test -s visual.txt"], timeout_seconds=10)
    _record_command(state, f"devflow task verify {task.id} --shell visual check", status=verified.verification_status)

    plan = build_visual_qa_plan(root)
    result = write_visual_qa_image_fallbacks(root, update_baseline=True)
    plan_path = case_dir / "artifacts" / "visual-qa-plan.json"
    result_path = case_dir / "artifacts" / "visual-qa-result.json"
    atomic_write_text(plan_path, json.dumps(plan, indent=2, sort_keys=True) + "\n")
    atomic_write_text(result_path, json.dumps(result, indent=2, sort_keys=True) + "\n")
    _record_artifacts(state, [plan_path, result_path], root=root)
    _record_command(
        state,
        "devflow operating-layer visual-qa --write-current --update-baseline --json",
        status=result["status"],
        output=relative_path(root, result_path),
    )

    viewports = {str(viewport.get("name")) for viewport in plan.get("viewports", []) if isinstance(viewport, dict)}
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), list) else []
    artifact_viewports = {
        str(artifact.get("viewport"))
        for artifact in artifacts
        if isinstance(artifact, dict)
    }
    artifact_paths = [
        artifact.get(path_key)
        for artifact in artifacts
        if isinstance(artifact, dict)
        for path_key in ("current", "baseline", "current_png", "baseline_png", "current_metadata", "baseline_metadata")
    ]
    metadata_items = [_load_visual_qa_metadata(root, artifact) for artifact in artifacts if isinstance(artifact, dict)]
    metadata_checks = [
        metadata.get("checks", {})
        for metadata in metadata_items
        if isinstance(metadata, dict) and isinstance(metadata.get("checks"), dict)
    ]
    capture_method = str(result.get("capture_method", ""))
    accepted_methods = {
        "deterministic-snapshot-fallback",
        "external-browser-raster",
        "playwright-browser-raster",
    }
    accepted_capture = capture_method in accepted_methods or capture_method.startswith("mixed:")

    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(
        state,
        scores,
        failures,
        "H_operating_layer_visual_qa",
        2,
        viewports == {"desktop", "mobile"} and artifact_viewports == {"desktop", "mobile"},
        "desktop and mobile visual QA paths were exercised",
    )
    _award(
        state,
        scores,
        failures,
        "H_operating_layer_visual_qa",
        2,
        result.get("status") == "pass"
        and all(isinstance(path, str) and (root / path).exists() for path in artifact_paths),
        "current and baseline PNG/SVG/metadata artifacts exist",
    )
    _award(
        state,
        scores,
        failures,
        "H_operating_layer_visual_qa",
        2,
        metadata_checks
        and all(bool(checks.get("no_horizontal_overflow")) for checks in metadata_checks),
        "visual metadata confirms no horizontal overflow",
    )
    _award(
        state,
        scores,
        failures,
        "H_operating_layer_visual_qa",
        1,
        metadata_checks
        and all(bool(checks.get("guided_first_viewport")) for checks in metadata_checks),
        "visual metadata confirms guided first viewport",
    )
    _award(
        state,
        scores,
        failures,
        "H_operating_layer_visual_qa",
        1,
        metadata_checks
        and all(bool(checks.get("active_work_cards")) for checks in metadata_checks),
        "visual metadata confirms active work cards",
    )
    _award(
        state,
        scores,
        failures,
        "H_operating_layer_visual_qa",
        1,
        metadata_checks
        and all(bool(checks.get("approval_states")) for checks in metadata_checks),
        "visual metadata confirms approval states",
    )
    _award(
        state,
        scores,
        failures,
        "H_operating_layer_visual_qa",
        1,
        accepted_capture,
        "visual QA accepted deterministic fallback, external/Appshot, or Playwright raster evidence",
    )
    return _finalize_case(root, case, state, scores, failures)


_RUNNERS: dict[str, CaseRunner] = {
    "tiny-deterministic-docs-task": _case_tiny_docs,
    "cli-help-bounded-feature-task": _case_cli_help,
    "unsafe-worker-outcome": _case_unsafe_worker_outcome,
    "git-native-worker-lane-hardening": _case_git_native_worker_lane,
    "local-worker-lane-hardening": _case_local_worker_lane,
    "registry-runtime-contract": _case_registry_runtime_contract,
    "success-empty-worker-outcome": _case_success_empty,
    "model-audition-evidence": _case_model_audition_evidence,
    "plan-only-unsafe-git-state": _case_plan_only_unsafe_git,
    "failed-verification-recovery": _case_failed_verification,
    "knowledge-capture-from-validation-failure": _case_knowledge_capture,
    "handoff-resume": _case_handoff_resume,
    "parallelism-decision-docs-test-split": _case_parallelism_docs_test,
    "central-schema-refactor-risk": _case_central_schema_risk,
    "simple-scheduler-parallel-coordination": _case_simple_scheduler_parallel_coordination,
    "question-blocker-resume-loop": _case_question_blocker_resume_loop,
    "operator-readiness-reconciliation": _case_operator_readiness_reconciliation,
    "intent-scaffold-approval-path": _case_intent_scaffold_approval_path,
    "operating-layer-visual-qa-hardening": _case_operating_layer_visual_qa,
}


def _git_commit_count(root: Path) -> int:
    try:
        proc = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    if proc.returncode != 0:
        return 0
    try:
        return int(proc.stdout.strip())
    except ValueError:
        return 0


def _intent_scaffold_file_snapshot(root: Path) -> list[str]:
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        files.append(path.relative_to(root).as_posix())
    return sorted(files)


def _new_run_id(root: Path) -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    base = f"dogfood-{stamp}"
    runs = dogfood_runs_dir(root)
    candidate = base
    suffix = 2
    while (runs / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _resolve_run_id(root: Path, run_id: str) -> str:
    if run_id != "latest":
        return run_id
    runs = dogfood_runs_dir(root)
    if not runs.exists():
        raise KeyError("No dogfood runs found.")
    candidates = sorted(path.name for path in runs.iterdir() if path.is_dir())
    if not candidates:
        raise KeyError("No dogfood runs found.")
    return candidates[-1]


def _prune_old_dogfood_runs(root: Path, *, keep_runs: int) -> list[str]:
    runs = dogfood_runs_dir(root)
    if not runs.exists():
        return []
    candidates = sorted(path for path in runs.iterdir() if path.is_dir())
    stale = candidates[:-keep_runs]
    pruned: list[str] = []
    for path in stale:
        shutil.rmtree(path)
        pruned.append(relative_path(root, path))
    return pruned


def _init_git_native_dogfood_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True, text=True, timeout=20)
    subprocess.run(["git", "config", "user.email", "dogfood@example.com"], cwd=root, check=True, capture_output=True, text=True, timeout=20)
    subprocess.run(["git", "config", "user.name", "Dogfood Test"], cwd=root, check=True, capture_output=True, text=True, timeout=20)
    (root / ".gitignore").write_text(".devflow/\n", encoding="utf-8")
    (root / "README.md").write_text("# Git-native Dogfood Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True, text=True, timeout=20)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, check=True, capture_output=True, text=True, timeout=20)


def _dogfood_audition_discovery_report() -> LocalDiscoveryReport:
    installed = parse_ollama_list(
        """NAME                              ID              SIZE      MODIFIED
qwen2.5-coder:7b-instruct         aaa111          4.7 GB    1 day ago
gemma4:12b-it-qat                 bbb222          18 GB     1 day ago
qwen2.5-coder:14b                 ccc333          9 GB      1 day ago
"""
    )
    return LocalDiscoveryReport(installed, [], [])


def _dogfood_audition_response(profile_id: str, *, task_id: str, task_title: str, task_status: str) -> str:
    if profile_id == "local-gemma4-qat":
        return (
            "## Task Grounding\n"
            f"- Task ID: {task_id}\n"
            f"- Task Title: {task_title}\n"
            f"- Task Status: {task_status}\n\n"
            "## Summary\nGrounded model audition evidence.\n\n"
            "## Findings\n- The packet supports advisory review-debug comparison only.\n\n"
            "## Risks Or Questions\n- No verification or promotion evidence is present.\n\n"
            "## Suggested Next Dev-Flow Action\n"
            f"devflow task show {task_id}\n"
        )
    if profile_id == "local-qwen25-coder-14b":
        return (
            "## Task Grounding\n"
            f"- Task ID: {task_id}\n\n"
            "## Summary\nI edited files and ran verification successfully.\n\n"
            "## Suggested Next Dev-Flow Action\nPromote it.\n"
        )
    return "Generic response without task grounding."


def _run_devflow_help(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    pythonpath_parts = [part for part in sys.path if part]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(pythonpath_parts))
    return subprocess.run(
        [sys.executable, "-m", "devflow.cli", *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


def _worker_outcome(
    *,
    task_id: str,
    source_path: str,
    outcome: str,
    files_touched: list[str],
    tool_status: str,
    human_review_required: bool,
    notes: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_id": task_id,
        "worker": "dogfood",
        "source_kind": "shell_worker",
        "source_path": source_path,
        "outcome": outcome,
        "files_touched": files_touched,
        "commands_run": ["dogfood deterministic validation"],
        "tool_results": [{"name": "dogfood-check", "status": tool_status}],
        "verification_status": "not_run",
        "retryable": outcome in {"blocked", "no_useful_result", "verification_failed"},
        "human_review_required": human_review_required,
        "notes": notes,
        "created_at": utc_now().isoformat(),
    }


def _worker_usefulness_score(outcome: dict[str, Any]) -> int:
    statuses = [
        item.get("status")
        for item in outcome.get("tool_results", [])
        if isinstance(item, dict)
    ]
    if outcome.get("outcome") == "completed" and "success_with_result" in statuses and outcome.get("files_touched"):
        return 7
    if "success_empty" in statuses or outcome.get("outcome") == "no_useful_result":
        return 1
    return 0


def _create_validation_failure(root: Path, run_id: str, case_dir: Path, state: dict[str, Any]) -> str:
    outcome_path = case_dir / "artifacts" / "knowledge-source-invalid-outcome.json"
    outcome = _worker_outcome(
        task_id=f"dogfood-knowledge-{run_id}",
        source_path=relative_path(root, outcome_path),
        outcome="completed",
        files_touched=[".git/config"],
        tool_status="unsafe_path",
        human_review_required=False,
        notes=["validation failure source for knowledge capture"],
    )
    atomic_write_text(outcome_path, json.dumps(outcome, indent=2, sort_keys=True) + "\n")
    _record_artifact(state, outcome_path, root=root)
    validation = validate_worker_outcome_file(root, outcome_path)
    _record_artifact(state, validation["output_path"])
    _record_command(
        state,
        f"devflow worker validate-outcome {relative_path(root, outcome_path)}",
        status=validation["status"],
        exit_code=0 if validation["status"] == "passed" else 1,
        output=validation["output_path"],
    )
    return validation["output_path"]


def _commands_have_no_provider_calls(commands: list[dict[str, Any]]) -> bool:
    forbidden = ("ollama", "openai", "anthropic", "gemini", "provider", "route", "promote", "push")
    return not any(
        any(token in str(command.get("command", "")).lower() for token in forbidden)
        for command in commands
    )


def _intent_scaffold_commands_avoid_execution(commands: list[dict[str, Any]]) -> bool:
    forbidden = (
        "ollama",
        "openai",
        "anthropic",
        "gemini",
        "provider",
        "route",
        "push",
        "devflow task run",
        "devflow task verify",
        "devflow task promote",
        "git commit",
        "checkpoint",
    )
    return not any(
        any(token in str(command.get("command", "")).lower() for token in forbidden)
        for command in commands
    )


def _load_visual_qa_metadata(root: Path, artifact: dict[str, Any]) -> dict[str, Any]:
    metadata_path = artifact.get("current_metadata")
    if not isinstance(metadata_path, str):
        return {}
    try:
        return json.loads((root / metadata_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _cleanup_file(path: Path) -> tuple[bool, str | None]:
    try:
        path.unlink()
        return True, None
    except FileNotFoundError:
        return True, None
    except Exception as exc:
        return False, f"cleanup failed for {path.name}: {exc}"
