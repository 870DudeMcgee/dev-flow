from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
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
