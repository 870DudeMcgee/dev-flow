from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from devflow.control_room.dogfood_case_result import CaseResultRecorder as _CaseResult
from devflow.control_room.dogfood_case_scratch import (
    create_recorded_git_native_case_scratch_repo as _create_recorded_git_native_case_scratch_repo,
)
from devflow.control_room.operating_layer import build_operating_layer_snapshot
from devflow.control_room.paths import relative_path
from devflow.control_room.persistence import atomic_write_text, get_task, save_task, utc_now
from devflow.control_room.question_resume import answer_question, build_question_snapshot
from devflow.control_room.scheduler_projection import build_scheduler_snapshot, request_scheduler_retry
from devflow.control_room.service import create_task
from devflow.control_room.supervisor_surface import build_control_room_status, build_supervisor_packet
from devflow.control_room.task_closure import close_task


def _case_simple_scheduler_parallel_coordination(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    case_result = _CaseResult(root, run_id, case, case_dir)
    scratch = _create_recorded_git_native_case_scratch_repo(
        case_dir,
        "simple-scheduler-repo",
        case_result=case_result,
        evidence_label="simple-scheduler",
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
    summary_path = case_result.write_summary_artifact("simple-scheduler-summary.json", summary)
    case_result.record_command(
        "devflow scheduler status --json (fixture)",
        status="passed",
        output=relative_path(root, summary_path),
    )
    case_result.record_command(
        "devflow scheduler retry <task-id> --reason 'dogfood retry evidence' --json",
        status="passed",
    )

    retry_after = get_task(scratch, retry_task.id)
    retry_preserved = (
        retry_after.status == "verification_failed"
        and retry_after.verification_status == "failed"
        and retry_after.verification_command == "pytest tests/test_retry.py"
    )
    commands_clean = _commands_have_no_provider_calls(case_result.commands)
    counts = snapshot_after.counts
    case_result.award(
        "B_pipeline_correctness",
        2,
        counts.get("ready", 0) >= 2
        and counts.get("blocked", 0) >= 2
        and counts.get("stale", 0) >= 1
        and counts.get("needs_retry", 0) >= 1,
        "scheduler exposed ready blocked stale and retry work",
    )
    case_result.award(
        "D_worker_artifact_quality",
        3,
        snapshot_after.batches
        and any(batch.next_safe_action == "devflow freshness create-batch G-0001 PB-0001" for batch in snapshot_after.batches)
        and (scratch / retry.retry_request_path).exists(),
        "scheduler wrote reviewable batch and retry evidence",
    )
    case_result.award(
        "E_recovery_failure_handling",
        5,
        retry_preserved and commands_clean,
        "retry request preserved prior task evidence",
    )
    if commands_clean:
        case_result.record_lesson("no background scheduler or provider calls were introduced")
    else:
        case_result.fail("no background scheduler or provider calls were introduced")
    return case_result.finalize()


def _case_question_blocker_resume_loop(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    case_result = _CaseResult(root, run_id, case, case_dir)
    scratch = _create_recorded_git_native_case_scratch_repo(
        case_dir, "question-resume-repo", case_result=case_result, evidence_label="question-resume"
    )

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
    summary_path = case_result.write_summary_artifact("question-resume-summary.json", summary)
    if answered and answered.answer_path:
        case_result.record_artifact(scratch / answered.answer_path, root=scratch)
    case_result.record_command(
        "devflow question list --json (fixture)",
        status="passed",
        output=relative_path(root, summary_path),
    )
    case_result.record_command(
        "devflow question answer <question-id> --answer '<answer>' --json",
        status="passed" if answered else "failed",
    )
    case_result.record_command(
        "devflow scheduler status --json (fixture)",
        status="passed",
    )

    answer_record_exists = bool(answered and answered.answer_path and (scratch / answered.answer_path).exists())
    mirror_exists = bool(
        answered
        and (scratch / ".devflow" / "tasks" / task.id / "question-answers" / f"{answered.question_id}.json").exists()
    )
    events_text = (scratch / ".devflow" / "tasks" / task.id / "events.jsonl").read_text(encoding="utf-8")
    commands_clean = _commands_have_no_provider_calls(case_result.commands)
    case_result.award(
        "B_pipeline_correctness",
        2,
        question is not None
        and question.question_id.startswith("Q-task-0001-")
        and snapshot.counts.get("open") == 1
        and bool(snapshot.warnings),
        "question list exposed deterministic open blocker",
    )
    case_result.award(
        "D_worker_artifact_quality",
        2,
        bool(answered)
        and answer_record_exists
        and mirror_exists
        and before_source == after_source
        and "question_answered" in events_text,
        "answer preserved source question evidence",
    )
    case_result.award(
        "E_recovery_failure_handling",
        4,
        scheduler.counts.get("blocked", 0) == 0
        and answered is not None
        and answered.recommended_resume_command == f"devflow task next-action {task.id}"
        and commands_clean,
        "no worker resume or provider call was executed by question commands",
    )
    return case_result.finalize()


def _case_operator_readiness_reconciliation(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, shared: dict[str, Any]
) -> dict[str, Any]:
    case_result = _CaseResult(root, run_id, case, case_dir)
    scratch = _create_recorded_git_native_case_scratch_repo(
        case_dir, "operator-readiness-repo", case_result=case_result, evidence_label="operator-readiness"
    )

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
    summary_path = case_result.write_summary_artifact("operator-readiness-summary.json", summary)
    case_result.record_command("devflow status --json (fixture)", status="passed", output=relative_path(root, summary_path))
    case_result.record_command("devflow scheduler status --json (fixture)", status="passed")
    case_result.record_command("devflow supervisor packet --json (fixture)", status="passed")
    case_result.record_command("devflow operating-layer snapshot --json (fixture)", status="passed")

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
    commands_clean = _commands_have_no_provider_calls(case_result.commands)

    close_task(scratch, generated.id, outcome="evidence-only", reason="dogfood operator readiness evidence captured")
    close_task(scratch, descriptive.id, outcome="evidence-only", reason="dogfood operator readiness evidence captured")

    case_result.award(
        "B_pipeline_correctness",
        2,
        surface_counts_agree and lifecycle_counts,
        "operator surfaces agreed on readiness counts",
    )
    case_result.award(
        "E_recovery_failure_handling",
        3,
        repair_priority and stale_warning,
        "lifecycle repair outranked stale dispatch guidance",
    )
    case_result.award(
        "D_worker_artifact_quality",
        2,
        plain_label and commands_clean,
        "plain descriptive task labels remained primary",
    )
    return case_result.finalize()


def _commands_have_no_provider_calls(commands: list[dict[str, Any]]) -> bool:
    forbidden = ("ollama", "openai", "anthropic", "gemini", "provider", "route", "promote", "push")
    return not any(
        any(token in str(command.get("command", "")).lower() for token in forbidden)
        for command in commands
    )
