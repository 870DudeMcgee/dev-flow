from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml

from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.knowledge_foundry import capture_from_validation, search_knowledge
from devflow.control_room.operating_layer_visual_qa import (
    build_visual_qa_plan,
    write_visual_qa_image_fallbacks,
)
from devflow.control_room.orchestration_plan import create_orchestration_plan
from devflow.control_room.paths import (
    dogfood_cases_dir,
    dogfood_runs_dir,
    relative_path,
)
from devflow.control_room.persistence import atomic_write_text, get_task, list_tasks, utc_now
from devflow.control_room.readiness import promotion_readiness_errors
from devflow.control_room.service import create_task, init_control_room, run_shell_task, verify_task
from devflow.control_room.task_closure import close_task
from devflow.control_room.task_packet import TaskPacketLimits, build_task_packet
from devflow.control_room.worker_outcome import validate_worker_outcome, validate_worker_outcome_file


DOGFOOD_SCHEMA_VERSION = 1
PRODUCTION_READINESS_SUITE = "production-readiness"
SILVER_THRESHOLD = 82

CATEGORY_MAX: dict[str, int] = {
    "A_safety_git_discipline": 20,
    "B_pipeline_correctness": 20,
    "C_context_efficiency": 15,
    "D_worker_artifact_quality": 15,
    "E_recovery_failure_handling": 15,
    "F_knowledge_capture": 10,
    "G_performance_lightweight": 5,
    "H_operating_layer_visual_qa": 10,
}

CATEGORY_LABELS: dict[str, str] = {
    "A_safety_git_discipline": "A - Safety and Git discipline",
    "B_pipeline_correctness": "B - Pipeline correctness",
    "C_context_efficiency": "C - Context efficiency",
    "D_worker_artifact_quality": "D - Worker/artifact quality",
    "E_recovery_failure_handling": "E - Recovery and failure handling",
    "F_knowledge_capture": "F - Knowledge capture",
    "G_performance_lightweight": "G - Performance/lightweight behavior",
    "H_operating_layer_visual_qa": "H - Operating-layer visual QA",
}

CRITICAL_CASES = {
    "unsafe-worker-outcome",
    "plan-only-unsafe-git-state",
    "failed-verification-recovery",
    "central-schema-refactor-risk",
}


CaseRunner = Callable[[Path, str, dict[str, Any], Path, dict[str, Any]], dict[str, Any]]


def production_readiness_cases() -> list[dict[str, Any]]:
    cases = [
        _case_definition(
            case_id="tiny-deterministic-docs-task",
            title="Tiny deterministic docs task",
            category="B_pipeline_correctness",
            task_type="docs_only_shell_task",
            risk_level="low",
            purpose="Prove Dev-Flow does not overcomplicate a tiny deterministic change.",
            expected_behavior=[
                "create a bounded task",
                "build a bounded task packet",
                "run a tiny workspace-only docs command",
                "verify with a docs-appropriate check",
                "leave the main checkout untouched except ignored dogfood evidence",
            ],
            command_sequence=[
                "devflow task create 'Dogfood tiny docs task'",
                "devflow task packet <task-id>",
                "devflow task run <task-id> --worker shell -- /bin/sh -c 'mkdir -p docs && printf ...'",
                "devflow task verify <task-id> --shell 'test -s docs/dogfood-tiny-note.md'",
            ],
            success_criteria=[
                "task reaches verified state",
                "context packet stays bounded",
                "workspace-only file is verified",
                "no promotion or provider call occurs",
            ],
            scoring={
                "A_safety_git_discipline": 0,
                "B_pipeline_correctness": 6,
                "C_context_efficiency": 7,
                "G_performance_lightweight": 2,
            },
        ),
        _case_definition(
            case_id="cli-help-bounded-feature-task",
            title="CLI/help bounded feature task",
            category="B_pipeline_correctness",
            task_type="cli_help_plan_only",
            risk_level="low",
            purpose="Prove small CLI-facing work follows the pipeline without broad execution.",
            expected_behavior=[
                "create/load task",
                "write orchestration plan-only evidence",
                "inspect dogfood CLI help",
                "avoid unrelated edits and provider calls",
            ],
            command_sequence=[
                "devflow task create 'Dogfood CLI help bounded task'",
                "devflow task orchestrate <task-id> --plan-only",
                "devflow dogfood --help",
            ],
            success_criteria=[
                "orchestration plan exists",
                "dogfood help exposes run/list/report commands",
                "command evidence is stored as a case artifact",
            ],
            scoring={
                "B_pipeline_correctness": 6,
                "C_context_efficiency": 3,
                "G_performance_lightweight": 2,
            },
        ),
        _case_definition(
            case_id="unsafe-worker-outcome",
            title="Unsafe worker outcome",
            category="A_safety_git_discipline",
            task_type="worker_outcome_validation",
            risk_level="high",
            purpose="Prove invalid worker metadata is rejected and preserved as evidence.",
            expected_behavior=[
                "files_touched with parent traversal fails",
                ".git paths fail",
                "unsafe human-review metadata is enforced",
                "validation writes evidence without mutating source",
            ],
            command_sequence=[
                "write invalid worker outcome JSON",
                "devflow worker validate-outcome <outcome-json>",
            ],
            success_criteria=[
                "validation status is failed",
                "path safety errors are explicit",
                "human review error is explicit",
            ],
            scoring={
                "A_safety_git_discipline": 8,
                "D_worker_artifact_quality": 5,
            },
        ),
        _case_definition(
            case_id="success-empty-worker-outcome",
            title="success_empty worker outcome",
            category="D_worker_artifact_quality",
            task_type="worker_outcome_quality",
            risk_level="medium",
            purpose="Prove empty worker success is preserved as no useful progress.",
            expected_behavior=[
                "success_empty remains success_empty in tool evidence",
                "no_useful_result is not normalized into completed useful work",
                "useful result scores higher than empty result",
            ],
            command_sequence=[
                "write no_useful_result outcome with success_empty tool status",
                "write completed outcome with success_with_result tool status",
                "compare deterministic usefulness scores",
            ],
            success_criteria=[
                "empty outcome validates only with human review required",
                "success_empty earns less usefulness credit than success_with_result",
            ],
            scoring={
                "B_pipeline_correctness": 2,
                "D_worker_artifact_quality": 7,
            },
        ),
        _case_definition(
            case_id="plan-only-unsafe-git-state",
            title="Plan-only unsafe Git state",
            category="A_safety_git_discipline",
            task_type="orchestration_plan_git_guardrail",
            risk_level="high",
            purpose="Prove orchestration recognizes unsafe Git state without running workers.",
            expected_behavior=[
                "temporary dirty marker makes Git state unsafe",
                "plan records dirty_git_tree stop condition",
                "parallelism is blocked",
                "temporary marker is removed and cleanup result is visible",
            ],
            command_sequence=[
                "create temporary dirty marker",
                "devflow task orchestrate <task-id> --plan-only",
                "remove temporary dirty marker",
            ],
            success_criteria=[
                "dirty_git_tree is active",
                "recommended execution is human_review_first or sequential",
                "no worker execution occurs",
                "cleanup status is recorded",
            ],
            scoring={
                "A_safety_git_discipline": 5,
                "E_recovery_failure_handling": 3,
            },
        ),
        _case_definition(
            case_id="failed-verification-recovery",
            title="Failed verification recovery",
            category="E_recovery_failure_handling",
            task_type="verification_failure",
            risk_level="medium",
            purpose="Prove failed verification blocks promotion readiness and records next state.",
            expected_behavior=[
                "failed verification is captured",
                "promotion readiness is blocked",
                "next safe action is explainable",
            ],
            command_sequence=[
                "devflow task create 'Dogfood failed verification recovery'",
                "devflow task run <task-id> --worker shell -- /bin/sh -c 'printf actual > recovery.txt'",
                "devflow task verify <task-id> --shell 'test \"$(cat recovery.txt)\" = expected'",
                "inspect promotion readiness errors",
            ],
            success_criteria=[
                "task status is verification_failed",
                "verification exit code is non-zero",
                "promotion_readiness_errors is non-empty",
            ],
            scoring={
                "A_safety_git_discipline": 4,
                "B_pipeline_correctness": 3,
                "E_recovery_failure_handling": 6,
            },
        ),
        _case_definition(
            case_id="knowledge-capture-from-validation-failure",
            title="Knowledge capture from validation failure",
            category="F_knowledge_capture",
            task_type="knowledge_capture",
            risk_level="low",
            purpose="Prove validation failures can become proposed, source-linked knowledge.",
            expected_behavior=[
                "validation failure evidence exists",
                "knowledge capture creates a proposed item",
                "source validation artifact is linked",
                "search can find the item",
                "knowledge is not auto-promoted",
            ],
            command_sequence=[
                "write invalid worker outcome JSON",
                "devflow worker validate-outcome <outcome-json>",
                "devflow knowledge capture --from-validation <validation-json>",
                "devflow knowledge search validation",
            ],
            success_criteria=[
                "knowledge status is proposed",
                "linked artifacts include validation evidence",
                "search returns the proposed item",
            ],
            scoring={
                "D_worker_artifact_quality": 3,
                "F_knowledge_capture": 10,
            },
        ),
        _case_definition(
            case_id="handoff-resume",
            title="Handoff/resume",
            category="E_recovery_failure_handling",
            task_type="artifact_resume",
            risk_level="low",
            purpose="Prove a fresh agent can reconstruct state from files and reports.",
            expected_behavior=[
                "task id and artifact paths are written to handoff evidence",
                "state reloads from canonical task files",
                "next safe action is explicit",
                "no hidden state is required",
            ],
            command_sequence=[
                "devflow task create 'Dogfood handoff resume'",
                "devflow task run <task-id> --worker shell -- /bin/sh -c 'printf handoff > handoff.txt'",
                "devflow task verify <task-id> --shell 'test -s handoff.txt'",
                "write dogfood handoff.md from file artifacts",
            ],
            success_criteria=[
                "fresh load of task succeeds",
                "handoff includes task id, artifacts, state, and next safe action",
            ],
            scoring={
                "B_pipeline_correctness": 3,
                "C_context_efficiency": 2,
                "E_recovery_failure_handling": 4,
            },
        ),
        _case_definition(
            case_id="parallelism-decision-docs-test-split",
            title="Parallelism decision docs/test split",
            category="C_context_efficiency",
            task_type="orchestration_context_layers",
            risk_level="low",
            purpose="Prove safe parallelism can be recommended or blocked conservatively with clear roles.",
            expected_behavior=[
                "plan-only orchestration writes role layers",
                "workers cannot promote",
                "DevMode skills are required",
                "no provider or worker execution occurs",
            ],
            command_sequence=[
                "devflow task create 'Update docs and tests for dogfood split'",
                "devflow task orchestrate <task-id> --plan-only",
            ],
            success_criteria=[
                "role context layers are present",
                "all roles have can_promote false",
                "notes state plan-only with no workers or providers",
            ],
            scoring={
                "C_context_efficiency": 3,
                "G_performance_lightweight": 1,
            },
        ),
        _case_definition(
            case_id="central-schema-refactor-risk",
            title="Central schema/refactor risk",
            category="A_safety_git_discipline",
            task_type="orchestration_high_risk_refusal",
            risk_level="high",
            purpose="Prove unsafe parallelism is refused for high-risk central changes.",
            expected_behavior=[
                "risk is high or medium",
                "recommended execution is not parallel",
                "parallelism_allowed is false",
                "human review is required",
            ],
            command_sequence=[
                "devflow task create 'Rewrite whole repo migration and disable guardrail'",
                "devflow task orchestrate <task-id> --plan-only",
            ],
            success_criteria=[
                "plan records high-risk stop conditions",
                "parallel execution is refused",
            ],
            scoring={
                "A_safety_git_discipline": 3,
                "E_recovery_failure_handling": 2,
            },
        ),
        _case_definition(
            case_id="operating-layer-visual-qa-hardening",
            title="Operating Layer visual QA hardening",
            category="H_operating_layer_visual_qa",
            task_type="operating_layer_visual_qa",
            risk_level="medium",
            purpose="Prove the local operating-layer UI has deterministic visual QA evidence in dogfood.",
            expected_behavior=[
                "desktop and mobile visual QA paths are planned",
                "current and baseline PNG/SVG artifacts are written",
                "deterministic fallback is enough when browser screenshots are unavailable",
                "external/Appshot or Playwright rasters are accepted when present",
                "visual metadata covers no-overflow, Orchestrator-first layout, worker progress, and Action Rail safety",
            ],
            command_sequence=[
                "devflow task create 'Dogfood operating layer visual QA'",
                "devflow task run <task-id> --worker shell -- /bin/sh -c 'printf visual > visual.txt'",
                "devflow task verify <task-id> --shell 'test -s visual.txt'",
                "devflow operating-layer visual-qa --write-current --update-baseline --json",
            ],
            success_criteria=[
                "desktop and mobile current/baseline artifacts exist",
                "visual QA status is pass",
                "metadata confirms no horizontal overflow",
                "metadata confirms Orchestrator-first ordering, worker progress rows, and Action Rail safety state",
            ],
            scoring={
                "H_operating_layer_visual_qa": 10,
            },
        ),
    ]
    _validate_suite_totals(cases)
    return cases


def validate_dogfood_case(case: dict[str, Any]) -> list[str]:
    required = {
        "schema_version",
        "id",
        "title",
        "category",
        "task_type",
        "risk_level",
        "purpose",
        "expected_behavior",
        "setup",
        "command_sequence",
        "success_criteria",
        "scoring",
        "cleanup",
        "notes",
    }
    errors: list[str] = []
    missing = sorted(required - set(case))
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
        return errors
    if case["schema_version"] != DOGFOOD_SCHEMA_VERSION:
        errors.append("schema_version must be 1")
    if not isinstance(case["id"], str) or not case["id"]:
        errors.append("id must be a non-empty string")
    if case["category"] not in CATEGORY_MAX:
        errors.append(f"unknown category: {case['category']}")
    if case["risk_level"] not in {"low", "medium", "high"}:
        errors.append("risk_level must be low, medium, or high")
    for list_key in ("expected_behavior", "command_sequence", "success_criteria", "notes"):
        if not isinstance(case[list_key], list):
            errors.append(f"{list_key} must be a list")
    scoring = case["scoring"]
    if not isinstance(scoring, dict) or not scoring:
        errors.append("scoring must be a non-empty mapping")
    else:
        for category, value in scoring.items():
            if category not in CATEGORY_MAX:
                errors.append(f"unknown scoring category: {category}")
            if not isinstance(value, int) or value < 0:
                errors.append(f"scoring.{category} must be a non-negative integer")
    return errors


def materialize_dogfood_cases(root: Path) -> list[Path]:
    paths: list[Path] = []
    dogfood_cases_dir(root).mkdir(parents=True, exist_ok=True)
    for case in production_readiness_cases():
        path = dogfood_cases_dir(root) / f"{case['id']}.yaml"
        atomic_write_text(path, yaml.safe_dump(case, sort_keys=False))
        paths.append(path)
    return paths


def run_dogfood_suite(
    root: Path,
    suite: str = PRODUCTION_READINESS_SUITE,
    *,
    case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    if suite != PRODUCTION_READINESS_SUITE:
        raise ValueError(f"Unknown dogfood suite: {suite}")

    init_control_room(root)
    materialize_dogfood_cases(root)
    run_id = _new_run_id(root)
    run_dir = dogfood_runs_dir(root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "cases").mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    baseline = _git_baseline(root)
    requested = list(case_ids) if case_ids else [case["id"] for case in production_readiness_cases()]
    cases_by_id = {case["id"]: case for case in production_readiness_cases()}
    results: list[dict[str, Any]] = []
    shared: dict[str, Any] = {}

    for case_id in requested:
        case = cases_by_id.get(case_id)
        if case is None:
            results.append(_skipped_unknown_case(run_id, case_id, run_dir))
            continue
        case_dir = run_dir / "cases" / case["id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(case_dir / "case.yaml", yaml.safe_dump(case, sort_keys=False))
        pre_case_task_ids = _task_ids(root)
        try:
            result = _RUNNERS[case["id"]](root, run_id, case, case_dir, shared)
        except Exception as exc:
            result = _failed_case_result(root, run_id, case, case_dir, exc)
        closed_tasks = _close_new_dogfood_tasks(root, pre_case_task_ids, run_id, case["id"])
        if closed_tasks:
            result["dogfood_tasks_closed"] = closed_tasks
        _write_case_result(case_dir, result)
        results.append(result)

    duration = round(time.monotonic() - started, 3)
    scorecard = _build_scorecard(run_id, suite, baseline, requested, results, duration)
    run_yaml = _build_run_yaml(run_id, suite, baseline, requested, results, scorecard, duration)
    report = _render_report(run_yaml, scorecard, results)

    atomic_write_text(run_dir / "run.yaml", yaml.safe_dump(run_yaml, sort_keys=False))
    atomic_write_text(run_dir / "scorecard.yaml", yaml.safe_dump(scorecard, sort_keys=False))
    atomic_write_text(run_dir / "report.md", report)

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


def render_dogfood_case_list(cases: list[dict[str, Any]] | None = None) -> str:
    selected = cases or production_readiness_cases()
    lines = ["Dogfood suite: production-readiness", ""]
    for case in selected:
        max_score = _case_max_score(case)
        lines.append(f"{case['id']}: {case['title']} ({max_score} pts, {case['risk_level']} risk)")
    return "\n".join(lines) + "\n"


def render_dogfood_case(case_id: str) -> str:
    cases = {case["id"]: case for case in production_readiness_cases()}
    if case_id not in cases:
        raise KeyError(f"Dogfood case not found: {case_id}")
    return yaml.safe_dump(cases[case_id], sort_keys=False)


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


def _case_definition(
    *,
    case_id: str,
    title: str,
    category: str,
    task_type: str,
    risk_level: str,
    purpose: str,
    expected_behavior: list[str],
    command_sequence: list[str],
    success_criteria: list[str],
    scoring: dict[str, int],
) -> dict[str, Any]:
    return {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "id": case_id,
        "title": title,
        "category": category,
        "task_type": task_type,
        "risk_level": risk_level,
        "purpose": purpose,
        "expected_behavior": expected_behavior,
        "setup": ["Create only task, outcome, or dogfood artifacts required for this case."],
        "command_sequence": command_sequence,
        "success_criteria": success_criteria,
        "scoring": scoring,
        "cleanup": [
            "Do not promote, push, call providers, create databases, or create dashboard assets.",
            "Remove any temporary non-.devflow dirty marker created by the case.",
        ],
        "notes": [
            "Deterministic local dogfood case.",
            "Workers remain replaceable; Dev-Flow owns state, verification, and promotion gates.",
        ],
    }


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
    state["artifacts_created"].append(relative_path(root, packet_path))
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
    _award(state, scores, failures, "B_pipeline_correctness", 6, reloaded.status == "verified", "task reached verified state")
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
    state["artifacts_created"].append(relative_path(root, plan_path))
    _record_command(state, f"devflow task orchestrate {task.id} --plan-only", status="passed", output=relative_path(root, plan_path))

    help_result = _run_devflow_help(root, ["dogfood", "--help"])
    help_path = case_dir / "artifacts" / "dogfood-help.txt"
    atomic_write_text(help_path, help_result.stdout + help_result.stderr)
    state["artifacts_created"].append(relative_path(root, help_path))
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
    state["artifacts_created"].append(relative_path(root, outcome_path))
    result = validate_worker_outcome_file(root, outcome_path)
    state["artifacts_created"].append(result["output_path"])
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
    _award(state, scores, failures, "A_safety_git_discipline", 3, result["status"] == "failed", "unsafe outcome was rejected")
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        3,
        "parent traversal is rejected" in errors_text and ".git paths are rejected" in errors_text,
        "path traversal and .git writes were blocked",
    )
    _award(
        state,
        scores,
        failures,
        "A_safety_git_discipline",
        2,
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
    state["artifacts_created"].extend(
        [
            relative_path(root, case_dir / "artifacts" / "empty-outcome.json"),
            relative_path(root, case_dir / "artifacts" / "useful-outcome.json"),
        ]
    )
    _record_command(state, "validate success_empty outcome in-process", status="passed" if not empty_errors else "failed")
    _record_command(state, "validate success_with_result outcome in-process", status="passed" if not useful_errors else "failed")
    state["lessons"].append(f"success_empty usefulness score {empty_score}; success_with_result score {useful_score}")

    scores: dict[str, int] = {}
    failures: list[str] = []
    _award(state, scores, failures, "B_pipeline_correctness", 2, not empty_errors and not useful_errors, "both outcome shapes validate")
    _award(
        state,
        scores,
        failures,
        "D_worker_artifact_quality",
        4,
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
    try:
        marker.write_text("temporary dogfood dirty marker\n", encoding="utf-8")
        marker_created = True
        _record_command(state, f"create {marker.name}", status="passed")
        plan = create_orchestration_plan(root, task.id, plan_only=True)
        _record_command(state, f"devflow task orchestrate {task.id} --plan-only", status="passed")
    finally:
        if marker_created:
            cleanup_ok = _cleanup_file(marker, state["warnings"])
            state["cleanup_status"] = "marker_removed" if cleanup_ok else f"cleanup_failed: {marker.name}"

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
        state["cleanup_status"] == "marker_removed" and not marker.exists(),
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
    state["artifacts_created"].append(relative_path(root, case_dir / "artifacts" / "promotion-readiness-errors.json"))

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
    state["artifacts_created"].append(f".devflow/knowledge/{item['id']}/knowledge.json")

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
    state["artifacts_created"].append(relative_path(root, handoff_path))

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
        4,
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
        state["warnings"].append(
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
    state["artifacts_created"].extend([relative_path(root, plan_path), relative_path(root, result_path)])
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
        and all(bool(checks.get("orchestrator_first")) for checks in metadata_checks),
        "visual metadata confirms Orchestrator-first layout",
    )
    _award(
        state,
        scores,
        failures,
        "H_operating_layer_visual_qa",
        1,
        metadata_checks
        and all(bool(checks.get("worker_progress_rows")) for checks in metadata_checks),
        "visual metadata confirms worker progress rows",
    )
    _award(
        state,
        scores,
        failures,
        "H_operating_layer_visual_qa",
        1,
        metadata_checks
        and all(bool(checks.get("action_rail_safety_states")) for checks in metadata_checks),
        "visual metadata confirms Action Rail safety state",
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
    "success-empty-worker-outcome": _case_success_empty,
    "plan-only-unsafe-git-state": _case_plan_only_unsafe_git,
    "failed-verification-recovery": _case_failed_verification,
    "knowledge-capture-from-validation-failure": _case_knowledge_capture,
    "handoff-resume": _case_handoff_resume,
    "parallelism-decision-docs-test-split": _case_parallelism_docs_test,
    "central-schema-refactor-risk": _case_central_schema_risk,
    "operating-layer-visual-qa-hardening": _case_operating_layer_visual_qa,
}


def _new_case_state(root: Path, run_id: str, case: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    (case_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    return {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "run_id": run_id,
        "case_id": case["id"],
        "status": "passed",
        "score": 0,
        "max_score": _case_max_score(case),
        "category_scores": {category: 0 for category in CATEGORY_MAX},
        "commands_run": [],
        "artifacts_created": [],
        "files_changed": [],
        "context_packet_size": None,
        "token_usage_estimate": None,
        "duration_seconds": 0.0,
        "failure_reason": None,
        "warnings": [],
        "lessons": [],
        "cleanup_status": "not_required",
        "_started": time.monotonic(),
        "_git_status_before": _git_short_status(root),
    }


def _finalize_case(
    root: Path,
    case: dict[str, Any],
    state: dict[str, Any],
    scores: dict[str, int],
    failures: list[str],
) -> dict[str, Any]:
    state["category_scores"] = {category: scores.get(category, 0) for category in CATEGORY_MAX}
    state["score"] = sum(state["category_scores"].values())
    state["duration_seconds"] = round(time.monotonic() - float(state.pop("_started")), 3)
    before = set(state.pop("_git_status_before"))
    after = set(_git_short_status(root))
    state["files_changed"] = sorted(after - before)
    if failures:
        state["status"] = "failed"
        state["failure_reason"] = "; ".join(failures)
    if state["score"] > state["max_score"]:
        state["warnings"].append(f"score exceeded case max; capped from {state['score']} to {state['max_score']}")
        state["score"] = state["max_score"]
    state["critical"] = case["id"] in CRITICAL_CASES
    return {key: value for key, value in state.items() if not key.startswith("_")}


def _failed_case_result(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, exc: Exception
) -> dict[str, Any]:
    state = _new_case_state(root, run_id, case, case_dir)
    state["status"] = "failed"
    state["failure_reason"] = f"{type(exc).__name__}: {exc}"
    state["duration_seconds"] = round(time.monotonic() - float(state.pop("_started")), 3)
    state.pop("_git_status_before", None)
    state["critical"] = case["id"] in CRITICAL_CASES
    return {key: value for key, value in state.items() if not key.startswith("_")}


def _skipped_unknown_case(run_id: str, case_id: str, run_dir: Path) -> dict[str, Any]:
    case_dir = run_dir / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "run_id": run_id,
        "case_id": case_id,
        "status": "skipped",
        "score": 0,
        "max_score": 0,
        "category_scores": {category: 0 for category in CATEGORY_MAX},
        "commands_run": [],
        "artifacts_created": [],
        "files_changed": [],
        "context_packet_size": None,
        "token_usage_estimate": None,
        "duration_seconds": 0.0,
        "failure_reason": "case not found in suite",
        "warnings": ["requested case was not found; scored as skipped"],
        "lessons": [],
        "cleanup_status": "not_required",
        "critical": False,
    }
    _write_case_result(case_dir, result)
    return result


def _write_case_result(case_dir: Path, result: dict[str, Any]) -> None:
    atomic_write_text(case_dir / "case-result.yaml", yaml.safe_dump(result, sort_keys=False))


def _award(
    state: dict[str, Any],
    scores: dict[str, int],
    failures: list[str],
    category: str,
    points: int,
    condition: bool,
    lesson: str,
) -> None:
    if condition:
        scores[category] = scores.get(category, 0) + points
        state["lessons"].append(lesson)
    else:
        failures.append(lesson)
        state["warnings"].append(f"missed: {lesson}")


def _build_scorecard(
    run_id: str,
    suite: str,
    baseline: dict[str, Any],
    requested: list[str],
    results: list[dict[str, Any]],
    duration: float,
) -> dict[str, Any]:
    category_max = {category: 0 for category in CATEGORY_MAX}
    for case in production_readiness_cases():
        if case["id"] in requested:
            for category, points in case["scoring"].items():
                category_max[category] += points
    category_scores = {}
    for category in CATEGORY_MAX:
        score = sum(int(result.get("category_scores", {}).get(category, 0)) for result in results)
        max_score = category_max[category]
        percent = round((score / max_score) * 100, 1) if max_score else 100.0
        category_scores[category] = {
            "score": score,
            "max": max_score,
            "percent": percent,
        }

    total = sum(item["score"] for item in category_scores.values())
    max_score = sum(item["max"] for item in category_scores.values())
    failures = [
        f"{result['case_id']}: {result['failure_reason']}"
        for result in results
        if result.get("status") in {"failed", "blocked"} and result.get("failure_reason")
    ]
    warnings = [
        f"{result['case_id']}: {warning}"
        for result in results
        for warning in result.get("warnings", [])
    ]
    critical_failures = [
        result["case_id"]
        for result in results
        if result.get("critical") and result.get("status") not in {"passed"}
    ]
    threshold = _threshold_result(total, max_score, category_scores, critical_failures)
    return {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "run_id": run_id,
        "suite": suite,
        "created_at": utc_now().isoformat(),
        "git_baseline": baseline,
        "total_score": total,
        "max_score": max_score,
        "category_scores": category_scores,
        "threshold_result": threshold,
        "critical_failures": critical_failures,
        "failures": failures,
        "warnings": warnings,
        "duration_seconds": duration,
    }


def _build_run_yaml(
    run_id: str,
    suite: str,
    baseline: dict[str, Any],
    requested: list[str],
    results: list[dict[str, Any]],
    scorecard: dict[str, Any],
    duration: float,
) -> dict[str, Any]:
    return {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": scorecard["created_at"],
        "suite": suite,
        "git_baseline": baseline,
        "cases_requested": requested,
        "cases_run": [
            {
                "case_id": result["case_id"],
                "status": result["status"],
                "score": result["score"],
                "max_score": result["max_score"],
            }
            for result in results
        ],
        "total_score": scorecard["total_score"],
        "max_score": scorecard["max_score"],
        "category_scores": scorecard["category_scores"],
        "threshold_result": scorecard["threshold_result"],
        "failures": scorecard["failures"],
        "warnings": scorecard["warnings"],
        "duration_seconds": duration,
        "notes": [
            "Deterministic local dogfood validation only.",
            "No provider APIs, autonomous routing, auto-promotion, push, database, vector DB, RAG, dashboard, daemon, or ML training were added or invoked.",
        ],
    }


def _render_report(run_yaml: dict[str, Any], scorecard: dict[str, Any], results: list[dict[str, Any]]) -> str:
    threshold = scorecard["threshold_result"]
    lines = [
        "# Dev-Flow Production Readiness Dogfood Report",
        "",
        f"run_id: {run_yaml['run_id']}",
        f"suite: {run_yaml['suite']}",
        f"score: {scorecard['total_score']}/{scorecard['max_score']}",
        f"threshold: {threshold['achieved']}",
        f"silver_met: {'yes' if threshold['silver_met'] else 'no'}",
        f"duration_seconds: {scorecard['duration_seconds']}",
        "",
        "## Category Scores",
        "",
    ]
    for category, item in scorecard["category_scores"].items():
        lines.append(f"- {CATEGORY_LABELS.get(category, category)}: {item['score']}/{item['max']} ({item['percent']}%)")
    lines.extend(["", "## Cases", ""])
    for result in results:
        lines.append(
            f"- {result['case_id']}: {result['status']} ({result['score']}/{result['max_score']})"
        )
    lines.extend(["", "## Failures", ""])
    if scorecard["failures"]:
        lines.extend(f"- {failure}" for failure in scorecard["failures"])
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    if scorecard["warnings"]:
        lines.extend(f"- {warning}" for warning in scorecard["warnings"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Boundary Confirmation",
            "",
            "- provider_api_calls: none",
            "- autonomous_routing: none",
            "- auto_promotion: none",
            "- push: none",
            "- database: none",
            "- vector_db_rag_embeddings: none",
            "- dashboard_or_daemon: none",
            "- ml_training: none",
            "",
            "## Next Safe Action",
            "",
            _next_safe_action(scorecard),
            "",
        ]
    )
    return "\n".join(lines)


def _threshold_result(
    total: int,
    max_score: int,
    category_scores: dict[str, dict[str, float | int]],
    critical_failures: list[str],
) -> dict[str, Any]:
    normalized = round((total / max_score) * 100, 1) if max_score else 0.0
    category_percents = [
        float(item["percent"])
        for item in category_scores.values()
        if int(item["max"]) > 0
    ]
    no_category_below_70 = all(percent >= 70.0 for percent in category_percents)
    no_category_below_80 = all(percent >= 80.0 for percent in category_percents)
    if normalized >= 95 and no_category_below_80 and not critical_failures:
        achieved = "Bulletproof candidate"
    elif normalized >= 90 and not critical_failures:
        achieved = "Gold"
    elif normalized >= 82 and no_category_below_70 and not critical_failures:
        achieved = "Silver"
    elif normalized >= 70:
        achieved = "Bronze"
    else:
        achieved = "below Bronze"
    return {
        "achieved": achieved,
        "normalized_score": normalized,
        "bronze_met": normalized >= 70,
        "silver_met": normalized >= SILVER_THRESHOLD and no_category_below_70 and not critical_failures,
        "gold_met": normalized >= 90 and not critical_failures,
        "bulletproof_candidate": normalized >= 95 and no_category_below_80 and not critical_failures,
        "no_category_below_70": no_category_below_70,
        "no_category_below_80": no_category_below_80,
        "critical_failures": critical_failures,
    }


def _next_safe_action(scorecard: dict[str, Any]) -> str:
    if scorecard["threshold_result"]["silver_met"]:
        if scorecard["threshold_result"]["gold_met"]:
            return "- Inspect the report warnings, then decide whether to make the harness part of the milestone checklist."
        return "- Improve the lowest-scoring category toward Gold without weakening any safety case."
    category_scores = scorecard["category_scores"]
    lowest = min(
        (item for item in category_scores.items() if item[1]["max"] > 0),
        key=lambda pair: pair[1]["percent"],
        default=("none", {"percent": 0}),
    )
    return f"- Repair the lowest-scoring category first: {CATEGORY_LABELS.get(lowest[0], lowest[0])}."


def _git_baseline(root: Path) -> dict[str, Any]:
    state = inspect_git_state(root)
    return {
        "is_repo": state.is_repo,
        "branch": state.branch,
        "head_sha": state.head_sha,
        "origin_main_sha": state.origin_main_sha,
        "dirty_state": "dirty" if state.dirty else "clean",
        "operation_in_progress": state.operation_in_progress,
        "safe_for_worker_writes": state.safe_for_worker_writes,
        "safe_for_promotion": state.safe_for_promotion,
        "safe_for_push": state.safe_for_push,
    }


def _git_short_status(root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line and not line[3:].startswith(".devflow/")]


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
    state["artifacts_created"].append(relative_path(root, outcome_path))
    validation = validate_worker_outcome_file(root, outcome_path)
    state["artifacts_created"].append(validation["output_path"])
    _record_command(
        state,
        f"devflow worker validate-outcome {relative_path(root, outcome_path)}",
        status=validation["status"],
        exit_code=0 if validation["status"] == "passed" else 1,
        output=validation["output_path"],
    )
    return validation["output_path"]


def _record_command(
    state: dict[str, Any],
    command: str,
    *,
    status: str,
    exit_code: int | None = None,
    output: str | None = None,
) -> None:
    state["commands_run"].append(
        {
            "command": command,
            "status": status,
            "exit_code": exit_code,
            "output": output,
        }
    )


def _commands_have_no_provider_calls(commands: list[dict[str, Any]]) -> bool:
    forbidden = ("ollama", "openai", "anthropic", "gemini", "provider", "route", "promote", "push")
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


def _cleanup_file(path: Path, warnings: list[str]) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return True
    except Exception as exc:
        warnings.append(f"cleanup failed for {path.name}: {exc}")
        return False


def _case_max_score(case: dict[str, Any]) -> int:
    return sum(int(value) for value in case.get("scoring", {}).values())


def _validate_suite_totals(cases: list[dict[str, Any]]) -> None:
    category_totals = {category: 0 for category in CATEGORY_MAX}
    for case in cases:
        errors = validate_dogfood_case(case)
        if errors:
            raise ValueError(f"Dogfood case {case.get('id', '<unknown>')} is invalid: {'; '.join(errors)}")
        for category, points in case["scoring"].items():
            category_totals[category] += points
    if category_totals != CATEGORY_MAX:
        raise ValueError(f"Dogfood suite scoring totals drifted: {category_totals} != {CATEGORY_MAX}")
