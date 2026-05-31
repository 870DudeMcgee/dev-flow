from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.manual_worker import read_manual_agent_evidence
from devflow.control_room.service import create_task


runner = CliRunner()


def test_manual_codex_worker_run_creates_codex_ready_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    task = create_task(tmp_path, "Use the manual proof worker")

    result = runner.invoke(app, ["task", "run", task.id, "--worker", "devflow-manual-codex-worker"])

    assert result.exit_code == 0, result.output
    assert f"{task.id}: blocked" in result.output
    assert "manual_handoff_path: .devflow/tasks/task-0001/agents/devflow-manual-codex-worker/handoff.md" in result.output

    agent_dir = tmp_path / ".devflow/tasks" / task.id / "agents" / "devflow-manual-codex-worker"
    handoff = (agent_dir / "handoff.md").read_text(encoding="utf-8")
    assert "You are devflow-manual-codex-worker." in handoff
    assert "Role: implementation_worker" in handoff
    assert "Adapter: manual" in handoff
    assert "Execution mode: human_launched_agent" in handoff
    assert "Edit only files under <workspace>." in handoff
    assert "Do not edit <task>/task.yaml." in handoff
    assert "When complete, write <task>/agents/devflow-manual-codex-worker/result.md" in handoff
    assert "When blocked, append one JSON line to <task>/agents/devflow-manual-codex-worker/questions.jsonl" in handoff
    assert "When failed, write <task>/agents/devflow-manual-codex-worker/worker_failed.json" in handoff

    packet = json.loads((agent_dir / "packet.json").read_text(encoding="utf-8"))
    assert packet["agent_id"] == "devflow-manual-codex-worker"
    assert packet["allowed_writes"] == [
        "<workspace>/**",
        "<task>/agents/devflow-manual-codex-worker/result.md",
        "<task>/agents/devflow-manual-codex-worker/questions.jsonl",
        "<task>/agents/devflow-manual-codex-worker/worker_failed.json",
    ]


def test_manual_agent_complete_evidence_is_visible_in_task_show_and_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    task = create_task(tmp_path, "Manual complete visibility")
    runner.invoke(app, ["task", "run", task.id, "--worker", "devflow-manual-codex-worker"])
    agent_dir = tmp_path / ".devflow/tasks" / task.id / "agents" / "devflow-manual-codex-worker"
    (agent_dir / "result.md").write_text(
        "# Result\n\n"
        "status: complete\n"
        "summary: Implemented the assigned change in the isolated workspace.\n"
        "changed_files:\n"
        "- src/example.py\n"
        "verification_suggestion: pytest tests/test_example.py\n",
        encoding="utf-8",
    )

    evidence = read_manual_agent_evidence(tmp_path, task.id, "devflow-manual-codex-worker")
    assert evidence.state == "complete"
    assert evidence.summary == "Implemented the assigned change in the isolated workspace."

    show = runner.invoke(app, ["task", "show", task.id])
    assert show.exit_code == 0, show.output
    assert "manual_agent_state: complete" in show.output
    assert "manual_agent_result: .devflow/tasks/task-0001/agents/devflow-manual-codex-worker/result.md" in show.output
    assert "Dev-Flow verification required before promotion." in show.output

    dashboard = runner.invoke(app, ["dashboard"])
    assert dashboard.exit_code == 0, dashboard.output
    assert "manual_agent_state: complete" in dashboard.output

    workspace_file = tmp_path / ".devflow/workspaces" / task.id / "manual.txt"
    workspace_file.write_text("done\n", encoding="utf-8")
    verify = runner.invoke(app, ["task", "verify", task.id, "--shell", "test -f manual.txt"])
    assert verify.exit_code == 0, verify.output
    verified_show = runner.invoke(app, ["task", "show", task.id])
    assert "status: verified" in verified_show.output
    assert "manual_agent_state: complete" in verified_show.output
    assert "suggested_next_action: Task is verified." in verified_show.output


def test_manual_agent_blocked_question_contract_is_visible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    task = create_task(tmp_path, "Manual blocked visibility")
    runner.invoke(app, ["task", "run", task.id, "--worker", "devflow-manual-codex-worker"])
    agent_dir = tmp_path / ".devflow/tasks" / task.id / "agents" / "devflow-manual-codex-worker"
    question = {
        "type": "blocked_question",
        "task_id": task.id,
        "agent_id": "devflow-manual-codex-worker",
        "question": "Which API shape should I preserve?",
        "blocking_reason": "Two incompatible call sites exist.",
        "required_decision": "Choose the canonical call signature.",
    }
    with (agent_dir / "questions.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(question) + "\n")

    evidence = read_manual_agent_evidence(tmp_path, task.id, "devflow-manual-codex-worker")
    assert evidence.state == "blocked"
    assert evidence.question == "Which API shape should I preserve?"

    show = runner.invoke(app, ["task", "show", task.id])
    assert show.exit_code == 0, show.output
    assert "manual_agent_state: blocked" in show.output
    assert "manual_agent_question: Which API shape should I preserve?" in show.output

    dashboard = runner.invoke(app, ["dashboard"])
    assert dashboard.exit_code == 0, dashboard.output
    assert "manual_agent_state: blocked" in dashboard.output


def test_manual_agent_failed_evidence_contract_is_visible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    task = create_task(tmp_path, "Manual failed visibility")
    runner.invoke(app, ["task", "run", task.id, "--worker", "devflow-manual-codex-worker"])
    agent_dir = tmp_path / ".devflow/tasks" / task.id / "agents" / "devflow-manual-codex-worker"
    (agent_dir / "worker_failed.json").write_text(
        json.dumps(
            {
                "status": "worker_failed",
                "task_id": task.id,
                "agent_id": "devflow-manual-codex-worker",
                "summary": "Could not apply the patch cleanly.",
                "error_type": "patch_conflict",
                "evidence": ["src/example.py had incompatible edits"],
                "next_safe_action": "Ask the main control-room agent to split the task.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    evidence = read_manual_agent_evidence(tmp_path, task.id, "devflow-manual-codex-worker")
    assert evidence.state == "failed"
    assert evidence.summary == "Could not apply the patch cleanly."

    show = runner.invoke(app, ["task", "show", task.id])
    assert show.exit_code == 0, show.output
    assert "manual_agent_state: failed" in show.output
    assert "manual_agent_failure: Could not apply the patch cleanly." in show.output

    dashboard = runner.invoke(app, ["dashboard"])
    assert dashboard.exit_code == 0, dashboard.output
    assert "manual_agent_state: failed" in dashboard.output
