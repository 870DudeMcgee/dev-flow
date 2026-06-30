from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room import evidence_review_detail as evidence_review_detail_module
from devflow.control_room import task_workbench as task_workbench_module
from devflow.control_room.paths import task_dir
from devflow.control_room.persistence import get_task, save_task
from devflow.control_room.task_workbench import build_task_workbench


runner = CliRunner()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_local_patch_worker_evidence(root: Path, task_id: str) -> None:
    agent_dir = root / ".devflow" / "tasks" / task_id / "agents" / "qwopus-implementer"
    _write_json(
        agent_dir / "run.json",
        {
            "schema_version": 1,
            "task_id": task_id,
            "agent_id": "qwopus-implementer",
            "status": "complete",
            "model": "qwopus:latest",
            "adapter": "ollama_chat",
            "proposal_patch_found": True,
        },
    )
    (agent_dir / "proposal.patch").write_text("diff --git a/hello.txt b/hello.txt\n", encoding="utf-8")


def _controls_by_intent(task) -> dict[str, object]:
    return {control.intent: control for control in task.controls}


def _write_stale_task_lock(root: Path, task_id: str) -> None:
    lock_dir = root / ".devflow" / "tasks" / task_id / ".lock"
    lock_dir.mkdir(parents=True, exist_ok=True)
    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    (lock_dir / "owner.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "operation": "stale-run",
                "pid": 1,
                "host": "other-host",
                "acquired_at": old_time.isoformat(),
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_task_workbench_review_models_are_reexported_for_existing_callers() -> None:
    from devflow.control_room import task_workbench as workbench_module
    from devflow.control_room.task_workbench_review import (
        TaskWorkbenchGateReceipt,
        TaskWorkbenchReviewLoop,
        TaskWorkbenchReviewQueueItem,
        TaskWorkbenchWorkerActivity,
    )

    assert workbench_module.TaskWorkbenchGateReceipt is TaskWorkbenchGateReceipt
    assert workbench_module.TaskWorkbenchReviewLoop is TaskWorkbenchReviewLoop
    assert workbench_module.TaskWorkbenchReviewQueueItem is TaskWorkbenchReviewQueueItem
    assert workbench_module.TaskWorkbenchWorkerActivity is TaskWorkbenchWorkerActivity


def test_task_workbench_projects_task_lanes_focus_controls_and_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert runner.invoke(app, ["task", "create", "new task"]).exit_code == 0

    assert runner.invoke(app, ["task", "create", "needs verification"]).exit_code == 0
    run_needs_verify = runner.invoke(app, ["task", "run", "task-0002", "--shell", "echo done > result.txt"])
    assert run_needs_verify.exit_code == 0, run_needs_verify.output

    assert runner.invoke(app, ["task", "create", "failed verification"]).exit_code == 0
    run_failed = runner.invoke(app, ["task", "run", "task-0003", "--shell", "echo done > result.txt"])
    assert run_failed.exit_code == 0, run_failed.output
    failed_verify = runner.invoke(app, ["task", "verify", "task-0003", "--shell", "test -f missing.txt"])
    assert failed_verify.exit_code != 0, failed_verify.output

    assert runner.invoke(app, ["task", "create", "ready to promote"]).exit_code == 0
    run_ready = runner.invoke(app, ["task", "run", "task-0004", "--shell", "echo done > result.txt"])
    assert run_ready.exit_code == 0, run_ready.output
    verify_ready = runner.invoke(app, ["task", "verify", "task-0004", "--shell", "test -f result.txt"])
    assert verify_ready.exit_code == 0, verify_ready.output

    assert runner.invoke(app, ["task", "create", "closed task"]).exit_code == 0
    close = runner.invoke(
        app,
        ["task", "close", "task-0005", "--outcome", "evidence-only", "--reason", "captured"],
    )
    assert close.exit_code == 0, close.output

    workbench = build_task_workbench(tmp_path)
    tasks = {task.id: task for task in workbench.tasks}
    lanes = {lane.name: lane.task_ids for lane in workbench.lanes}

    assert workbench.focus_task_id == "task-0003"
    assert lanes["new"] == ["task-0001"]
    assert lanes["needs_verification"] == ["task-0002"]
    assert lanes["failed"] == ["task-0003"]
    assert lanes["ready_to_promote"] == ["task-0004"]
    assert lanes["closed"] == ["task-0005"]
    assert workbench.counts.active_task_ids == ["task-0001", "task-0002", "task-0003", "task-0004"]

    new_controls = _controls_by_intent(tasks["task-0001"])
    assert tasks["task-0001"].worker_model_label == "shell"
    assert tasks["task-0001"].next_safe_action == "devflow task run task-0001 --worker shell -- <command>"
    assert new_controls["start_shell"].command == "devflow task run task-0001 --worker shell -- <command>"
    assert new_controls["start_shell"].required_inputs == ["shell_command"]
    assert new_controls["start_shell"].safety_class == "approval_required_worker_runtime"
    assert new_controls["start_shell"].requires_human_approval is True
    assert new_controls["start_shell"].supervisor_may_auto_run is False
    assert new_controls["inspect"].command == "devflow task show task-0001"
    assert new_controls["inspect"].required_inputs == []

    verify_controls = _controls_by_intent(tasks["task-0002"])
    assert verify_controls["verify"].command == 'devflow task verify task-0002 --shell "<command>"'
    assert verify_controls["verify"].required_inputs == ["verification_command"]
    assert ".devflow/tasks/task-0002/logs/worker.log" in tasks["task-0002"].evidence_paths
    assert tasks["task-0002"].review_detail.review_state == "needs_verification"
    assert tasks["task-0002"].review_detail.evidence_paths == tasks["task-0002"].evidence_paths
    assert any(artifact.kind == "result" for artifact in tasks["task-0002"].review_detail.artifacts)

    failed_controls = _controls_by_intent(tasks["task-0003"])
    assert failed_controls["inspect"].command == "devflow task show task-0003"
    assert failed_controls["verify"].command == 'devflow task verify task-0003 --shell "<command>"'
    assert failed_controls["close"].required_inputs == ["close_outcome", "close_reason"]

    ready_controls = _controls_by_intent(tasks["task-0004"])
    assert ready_controls["review_preview"].command == "devflow task promote-preview task-0004"
    assert ready_controls["promote"].command == "devflow task promote task-0004"
    assert ready_controls["promote"].safety_class == "approval_required_git"
    assert ready_controls["promote"].requires_human_approval is True

    closed_controls = _controls_by_intent(tasks["task-0005"])
    assert closed_controls["cleanup_preview"].command == "devflow task cleanup task-0005 --preview"

    assert [item.task_id for item in workbench.review_queue] == ["task-0003", "task-0004", "task-0002"]
    evidence_by_task = {item.task_id: item for item in workbench.evidence_stream}
    assert evidence_by_task["task-0002"].result_path == ".devflow/tasks/task-0002/result.md"
    assert evidence_by_task["task-0004"].verification_command == "/bin/sh -c 'test -f result.txt'"


def test_task_workbench_names_local_worker_model_and_scopes_commands(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "local evidence"]).exit_code == 0
    _write_local_patch_worker_evidence(tmp_path, "task-0001")

    workbench = build_task_workbench(tmp_path, project_id="demo")
    task = workbench.tasks[0]
    controls = _controls_by_intent(task)

    assert task.worker_model_label == "qwopus-implementer - qwopus:latest"
    assert task.local_worker_lane is not None
    assert task.local_worker_lane.model == "qwopus:latest"
    assert ".devflow/tasks/task-0001/agents/qwopus-implementer/run.json" in task.evidence_paths
    assert any(artifact.kind == "patch proposal" for artifact in task.review_detail.artifacts)
    assert controls["start_shell"].command == "devflow task run task-0001 --worker shell --project demo -- <command>"
    assert controls["inspect"].command == "devflow task show task-0001 --project demo"


def test_task_workbench_prefetches_hermes_agents_once_per_snapshot(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "first"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "second"]).exit_code == 0

    call_count = {"count": 0}

    def fake_configured_hermes_agents(_root):
        call_count["count"] += 1
        return []

    monkeypatch.setattr(task_workbench_module, "configured_hermes_agents", fake_configured_hermes_agents)

    task_workbench_module.build_task_workbench(tmp_path)
    assert call_count["count"] == 1


def test_task_workbench_reuses_workspace_scan_for_duplicate_workspaces(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "same workspace one"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "same workspace two"]).exit_code == 0

    first = get_task(tmp_path, "task-0001")
    second = get_task(tmp_path, "task-0002")
    second.workspace = first.workspace
    second.workspace_path = first.workspace
    save_task(task_dir(tmp_path, second.id), second)

    workspace_root = tmp_path / ".devflow" / "workspaces" / "task-0001"
    (workspace_root / "shared.txt").write_text("workspace", encoding="utf-8")
    (tmp_path / "shared.txt").write_text("repo", encoding="utf-8")

    call_count = {"scan": 0}

    original = evidence_review_detail_module._changed_workspace_files

    def counting_scan(
        root: Path,
        workspace_value: str,
        notes: list[str],
        *,
        limit: int = 20,
        workspace_scan_cache: dict[tuple[str, int], list[str]] | None = None,
    ) -> list[str]:
        workspace = root / workspace_value if not Path(workspace_value).is_absolute() else Path(workspace_value)
        workspace = workspace.resolve()
        workspace_key = evidence_review_detail_module._workspace_key(root, workspace)
        if workspace_scan_cache is None or (workspace_key, limit) not in workspace_scan_cache:
            call_count["scan"] += 1
        return original(
            root,
            workspace_value,
            notes,
            limit=limit,
            workspace_scan_cache=workspace_scan_cache,
        )

    monkeypatch.setattr(evidence_review_detail_module, "_changed_workspace_files", counting_scan)
    task_workbench_module.build_task_workbench(tmp_path)
    assert call_count["scan"] == 1


def test_task_workbench_reports_stale_task_lock_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "stale lock task"]).exit_code == 0
    _write_stale_task_lock(tmp_path, "task-0001")

    workbench = task_workbench_module.build_task_workbench(tmp_path)
    task = {item.id: item for item in workbench.tasks}["task-0001"]

    assert task.lock_status is not None
    assert task.lock_status.is_stale is True
    assert task.lock_status.status == "stale"
    assert task.lock_status.operation == "stale-run"
    assert task.lock_status.host == "other-host"
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / ".lock").exists()


def test_task_workbench_keeps_missing_workspace_note_per_task(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["task", "create", "missing workspace one"]).exit_code == 0
    assert runner.invoke(app, ["task", "create", "missing workspace two"]).exit_code == 0

    missing_workspace = ".devflow/workspaces/missing-shared"
    for task_id in ("task-0001", "task-0002"):
        task = get_task(tmp_path, task_id)
        task.workspace = missing_workspace
        task.workspace_path = missing_workspace
        save_task(task_dir(tmp_path, task.id), task)

    workbench = task_workbench_module.build_task_workbench(tmp_path)
    tasks = {task.id: task for task in workbench.tasks}
    expected_note = "workspace unavailable for review summary: .devflow/workspaces/missing-shared"

    assert expected_note in tasks["task-0001"].detail.notes
    assert expected_note in tasks["task-0002"].detail.notes


def test_changed_workspace_file_cache_keeps_limits_and_return_values_independent(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / ".devflow" / "workspaces" / "shared"
    workspace.mkdir(parents=True)
    (workspace / "a.txt").write_text("workspace a", encoding="utf-8")
    (workspace / "b.txt").write_text("workspace b", encoding="utf-8")

    cache: dict[tuple[str, int], list[str]] = {}
    notes: list[str] = []
    one_file = evidence_review_detail_module._changed_workspace_files(
        tmp_path,
        ".devflow/workspaces/shared",
        notes,
        limit=1,
        workspace_scan_cache=cache,
    )
    one_file.append("mutated-by-caller.txt")

    one_file_again = evidence_review_detail_module._changed_workspace_files(
        tmp_path,
        ".devflow/workspaces/shared",
        notes,
        limit=1,
        workspace_scan_cache=cache,
    )
    two_files = evidence_review_detail_module._changed_workspace_files(
        tmp_path,
        ".devflow/workspaces/shared",
        notes,
        limit=2,
        workspace_scan_cache=cache,
    )

    assert one_file_again == ["a.txt"]
    assert two_files == ["a.txt", "b.txt"]


def test_changed_file_preview_cache_preserves_unavailable_notes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / ".devflow" / "workspaces" / "shared"
    workspace.mkdir(parents=True)

    cache: dict[str, dict[str, str]] = {}
    notes: list[str] = []
    for _ in range(2):
        preview = evidence_review_detail_module._changed_file_contents(
            tmp_path,
            ".devflow/workspaces/shared",
            ["missing.txt"],
            notes,
            workspace_preview_cache=cache,
        )
        assert preview == ""

    unavailable_notes = [note for note in notes if note.startswith("missing.txt preview unavailable:")]
    assert len(unavailable_notes) == 2
