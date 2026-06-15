from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.df_telegram_bridge import run_telegram_to_devflow_pipeline
from devflow.control_room.idea_foundry import capture_idea


runner = CliRunner()


def _files_under(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    )


def test_clear_request_previews_reviewable_goal_and_task_scaffold(tmp_path: Path) -> None:
    from devflow.control_room.intent_scaffold import preview_scaffold_from_idea

    idea = capture_idea(
        tmp_path,
        "build a search plugin",
        title="Build search plugin",
        source="operator-message",
        tags=["intent"],
    )

    proposal = preview_scaffold_from_idea(tmp_path, idea["id"])

    assert proposal["schema_version"] == 1
    assert proposal["status"] == "ready_for_review"
    assert proposal["source_idea"]["id"] == idea["id"]
    assert proposal["normalized_intent"]["title"] == "Build search plugin"
    assert proposal["proposed_goal"]["title"] == "Build search plugin"
    assert len(proposal["proposed_goal"]["acceptance_criteria"]) >= 3
    assert {"cli", "plugin", "tests"}.issubset(set(proposal["affected_areas"]))
    assert len(proposal["task_slices"]) >= 2
    assert {slice_["id"] for slice_ in proposal["task_slices"]} >= {"TS-0001", "TS-0002"}
    assert all(slice_["acceptance_criteria"] for slice_ in proposal["task_slices"])
    assert all(slice_["verification_policy"]["commands"] for slice_ in proposal["task_slices"])
    assert proposal["next_commands"] == [
        f"devflow idea scaffold-goal {idea['id']}",
        f"devflow idea promote {idea['id']} --to goal --rationale \"human reviewed scaffold\"",
        f"devflow idea create-goal {idea['id']}",
    ]
    assert not (tmp_path / ".devflow" / "goals").exists()
    assert not (tmp_path / ".devflow" / "tasks").exists()


def test_idea_scaffold_goal_command_writes_review_evidence_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(
        app,
        [
            "idea",
            "capture",
            "build a search plugin",
            "--title",
            "Build search plugin",
            "--source",
            "operator-message",
            "--tag",
            "intent",
        ],
    )
    before = _files_under(tmp_path)

    dry_run = runner.invoke(app, ["idea", "scaffold-goal", "I-0001", "--dry-run"])
    after_dry_run = _files_under(tmp_path)
    written = runner.invoke(app, ["idea", "scaffold-goal", "I-0001"])

    assert dry_run.exit_code == 0, dry_run.output
    assert "would_write_scaffold: yes" in dry_run.output
    assert before == after_dry_run
    assert written.exit_code == 0, written.output
    assert "status: ready_for_review" in written.output
    assert "scaffold_path: .devflow/ideas/I-0001/scaffold-goal.json" in written.output
    assert "created_goal: no" in written.output
    assert "created_task: no" in written.output
    assert "worker_ran: no" in written.output
    assert (tmp_path / ".devflow" / "ideas" / "I-0001" / "scaffold-goal.json").exists()
    assert (tmp_path / ".devflow" / "ideas" / "I-0001" / "scaffold-goal.md").exists()
    assert not (tmp_path / ".devflow" / "goals").exists()
    assert not (tmp_path / ".devflow" / "tasks").exists()


def test_ambiguous_request_returns_questions_without_goal_or_task_writes(tmp_path: Path) -> None:
    from devflow.control_room.intent_scaffold import preview_scaffold_from_idea

    idea = capture_idea(
        tmp_path,
        "make it better",
        title="Make it better",
        source="operator-message",
        tags=["intent"],
    )
    before = _files_under(tmp_path)

    proposal = preview_scaffold_from_idea(tmp_path, idea["id"])
    after = _files_under(tmp_path)

    assert proposal["status"] == "needs_questions"
    assert proposal["proposed_goal"] is None
    assert proposal["task_slices"] == []
    assert proposal["questions"]
    assert any("what should change" in question.lower() for question in proposal["questions"])
    assert proposal["next_commands"] == [f"devflow idea show {idea['id']}"]
    assert before == after
    assert not (tmp_path / ".devflow" / "goals").exists()
    assert not (tmp_path / ".devflow" / "tasks").exists()


def test_raw_df_telegram_message_returns_scaffold_pending_action_without_mutation(
    tmp_path: Path,
) -> None:
    before = _files_under(tmp_path)

    result = run_telegram_to_devflow_pipeline("/df build a search plugin", tmp_path)
    after = _files_under(tmp_path)

    assert result["status"] == "pending_approval"
    assert result["pipeline_step"] == "intent_scaffold_pending"
    assert result["raw_message"] == "/df build a search plugin"
    assert result["pending_action"]["kind"] == "intent_scaffold"
    assert result["pending_action"]["approval_required"] is True
    assert result["pending_action"]["source"] == "telegram"
    assert result["pending_action"]["proposal"]["normalized_intent"]["title"] == "Build search plugin"
    assert "devflow idea capture" in result["pending_action"]["approval_commands"][0]
    assert "devflow idea scaffold-goal" in result["pending_action"]["approval_commands"][-1]
    assert result.get("goal_id") is None
    assert result.get("task_ids") in (None, [])
    assert before == after
    assert not (tmp_path / ".devflow" / "goals").exists()
    assert not (tmp_path / ".devflow" / "tasks").exists()


def test_supervisor_route_message_exposes_scaffold_pending_action_read_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    before = _files_under(tmp_path)

    result = runner.invoke(app, ["supervisor", "route-message", "build a search plugin", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    after = _files_under(tmp_path)

    assert payload["route"] == "implementation"
    assert payload["action"] == "scaffold_goal"
    assert payload["operator_plan"]["next_step"] == "request_human_approval"
    assert payload["operator_plan"]["approval_required"] is True
    pending = payload["operator_plan"]["pending_action"]
    assert pending["kind"] == "intent_scaffold"
    assert pending["approval_required"] is True
    assert pending["source"] == "supervisor_route_message"
    assert pending["proposal"]["normalized_intent"]["title"] == "Build search plugin"
    assert "devflow idea capture" in pending["approval_commands"][0]
    assert "devflow idea scaffold-goal" in pending["approval_commands"][-1]
    assert before == after
    assert not (tmp_path / ".devflow" / "goals").exists()
    assert not (tmp_path / ".devflow" / "tasks").exists()
