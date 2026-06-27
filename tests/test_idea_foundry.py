from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

import devflow.control_room.idea_foundry as idea_foundry
from devflow.cli import app
from devflow.control_room.idea_foundry import (
    IdeaFoundryError,
    archive_idea,
    capture_idea,
    classify_idea,
    list_ideas,
    promote_idea,
    show_idea,
)


runner = CliRunner()


def test_capture_creates_inbox_idea_with_raw_evidence(tmp_path: Path) -> None:
    item = capture_idea(
        tmp_path,
        "Build an intake queue for rough ideas before they become tasks.",
        title="Idea intake queue",
        source="chat",
        tags=["planning"],
    )

    assert item["schema_version"] == 1
    assert item["id"] == "I-0001"
    assert item["title"] == "Idea intake queue"
    assert item["status"] == "inbox"
    assert item["maturity"] == "spark"
    assert item["source"] == "chat"
    assert item["tags"] == ["planning"]
    idea_dir = tmp_path / ".devflow" / "ideas" / item["id"]
    assert (idea_dir / "idea.json").exists()
    assert (idea_dir / "raw.md").read_text(encoding="utf-8").startswith(
        "Build an intake queue"
    )
    assert '"event": "created"' in (idea_dir / "events.jsonl").read_text(encoding="utf-8")


def test_list_show_classify_promote_and_archive_idea(tmp_path: Path) -> None:
    item = capture_idea(tmp_path, "Turn release notes into a repeatable checklist.")

    listed = list_ideas(tmp_path)
    assert [entry["id"] for entry in listed] == [item["id"]]

    classified = classify_idea(
        tmp_path,
        item["id"],
        maturity="goal_ready",
        note="Worth shaping into a goal after release-readiness work.",
        tags=["release", "checklist"],
    )
    assert classified["status"] == "classified"
    assert classified["maturity"] == "goal_ready"
    assert classified["tags"] == ["release", "checklist"]

    shown, raw, classification, promotion = show_idea(tmp_path, item["id"])
    assert shown["id"] == item["id"]
    assert "release-readiness" in classification
    assert raw.startswith("Turn release notes")
    assert promotion == ""

    promoted = promote_idea(
        tmp_path,
        item["id"],
        target="goal",
        rationale="The idea is ready to become a reviewed goal brief.",
        title="Release notes checklist goal",
    )
    assert promoted["status"] == "promoted"
    assert promoted["promotion_target"] == "goal"
    assert not (tmp_path / ".devflow" / "goals").exists()
    assert not (tmp_path / ".devflow" / "tasks").exists()

    archived = archive_idea(tmp_path, item["id"], reason="Superseded by a written goal.")
    assert archived["status"] == "archived"
    assert (tmp_path / ".devflow" / "ideas" / item["id"] / "promotion.md").exists()
    assert (tmp_path / ".devflow" / "ideas" / item["id"] / "raw.md").exists()


def test_promote_requires_matching_maturity(tmp_path: Path) -> None:
    item = capture_idea(tmp_path, "This is only a loose concept.")
    classify_idea(tmp_path, item["id"], maturity="candidate", note="Not ready yet.")

    try:
        promote_idea(tmp_path, item["id"], target="goal", rationale="Too soon.")
    except IdeaFoundryError as exc:
        assert "goal_ready" in str(exc)
    else:
        raise AssertionError("expected promotion to fail")


def test_park_idea_preserves_evidence_and_marks_safe_later(tmp_path: Path) -> None:
    item = capture_idea(
        tmp_path,
        "Build a voice capture inbox for ideas.",
        title="Voice idea capture",
    )

    parked = idea_foundry.park_idea(
        tmp_path,
        item["id"],
        reason="Great idea, not active this week.",
    )

    assert parked["status"] == "parked"
    assert parked["park_reason"] == "Great idea, not active this week."
    assert parked["parked_at"] is not None
    idea_dir = tmp_path / ".devflow" / "ideas" / item["id"]
    assert (idea_dir / "raw.md").exists()
    assert '"event": "parked"' in (idea_dir / "events.jsonl").read_text(encoding="utf-8")


def test_greenhouse_lane_projection_uses_existing_status_and_maturity(tmp_path: Path) -> None:
    greenhouse_lane_for_idea = idea_foundry.greenhouse_lane_for_idea
    raw = capture_idea(tmp_path, "Raw thought")
    concept = capture_idea(tmp_path, "Needs clarification")
    classify_idea(tmp_path, concept["id"], maturity="concept", note="Needs sharper scope.")
    candidate = capture_idea(tmp_path, "Promising candidate")
    classify_idea(
        tmp_path,
        candidate["id"],
        maturity="candidate",
        note="Looks promising.",
    )
    ready = capture_idea(tmp_path, "Task-sized idea")
    classify_idea(
        tmp_path,
        ready["id"],
        maturity="task_ready",
        note="Ready for task promotion.",
    )
    promote_idea(tmp_path, ready["id"], target="task", rationale="Human approved.")
    parked = capture_idea(tmp_path, "Later idea")
    idea_foundry.park_idea(tmp_path, parked["id"], reason="Later.")

    lanes = {item["id"]: greenhouse_lane_for_idea(item) for item in list_ideas(tmp_path)}

    assert lanes[raw["id"]] == "raw"
    assert lanes[concept["id"]] == "clarify"
    assert lanes[candidate["id"]] == "candidate"
    assert lanes[ready["id"]] == "promoted"
    assert lanes[parked["id"]] == "parked"


def test_operating_layer_idea_projection_exposes_brainstorm_lineage(tmp_path: Path) -> None:
    from devflow.control_room.brainstorm import start_brainstorm_from_idea
    from devflow.control_room.idea_greenhouse_projection import _idea_card

    idea = capture_idea(tmp_path, "Project this brainstorm link.", title="Projected lineage")
    session = start_brainstorm_from_idea(tmp_path, idea["id"])["session_id"]
    metadata, _, _, _ = show_idea(tmp_path, idea["id"])

    card = _idea_card(metadata, "raw")

    assert card.metadata["lineage"]["source_idea_id"] == idea["id"]
    assert card.metadata["lineage"]["latest_brainstorm_session_id"] == session
    assert card.metadata["lineage"]["latest_brainstorm_session_path"] == f".devflow/brainstorms/{session}"
    assert f".devflow/brainstorms/{session}" in card.evidence_paths


def test_invalid_idea_id_fails_cleanly(tmp_path: Path) -> None:
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["idea", "show", "../bad"])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 1
    assert "Invalid idea id" in result.output


def test_idea_cli_capture_list_show_classify_promote_archive(tmp_path: Path) -> None:
    old_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        captured = runner.invoke(
            app,
            [
                "idea",
                "capture",
                "Make release readiness easier to repeat.",
                "--title",
                "Release readiness repeatability",
                "--source",
                "chat",
                "--tag",
                "release",
            ],
        )
        assert captured.exit_code == 0, captured.output
        idea_id = captured.output.split("idea_id:", 1)[1].strip().splitlines()[0]

        listed = runner.invoke(app, ["idea", "list"])
        shown = runner.invoke(app, ["idea", "show", idea_id])
        classified = runner.invoke(
            app,
            [
                "idea",
                "classify",
                idea_id,
                "--maturity",
                "goal_ready",
                "--note",
                "Ready to become a goal brief.",
                "--tag",
                "checklist",
            ],
        )
        promoted = runner.invoke(
            app,
            [
                "idea",
                "promote",
                idea_id,
                "--to",
                "goal",
                "--rationale",
                "Human reviewed and ready for goal shaping.",
            ],
        )
        archived = runner.invoke(app, ["idea", "archive", idea_id, "--reason", "Recorded in a goal brief."])
    finally:
        os.chdir(old_cwd)

    assert listed.exit_code == 0, listed.output
    assert idea_id in listed.output
    assert shown.exit_code == 0, shown.output
    assert "Release readiness repeatability" in shown.output
    assert classified.exit_code == 0, classified.output
    assert "status: classified" in classified.output
    assert promoted.exit_code == 0, promoted.output
    assert "created_goal: no" in promoted.output
    assert "created_task: no" in promoted.output
    assert archived.exit_code == 0, archived.output
    assert "status: archived" in archived.output


def test_cli_park_idea(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["idea", "capture", "Save this for later", "--title", "Later idea"])

    result = runner.invoke(app, ["idea", "park", "I-0001", "--reason", "Not this week."])
    shown = runner.invoke(app, ["idea", "show", "I-0001"])

    assert result.exit_code == 0, result.output
    assert "status: parked" in result.output
    assert "evidence_deleted: no" in result.output
    assert "status: parked" in shown.output


def test_cli_create_goal_from_promoted_idea(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["idea", "capture", "Build release gate", "--title", "Release gate"])
    runner.invoke(app, ["idea", "classify", "I-0001", "--maturity", "goal_ready", "--note", "Ready"])
    runner.invoke(app, ["idea", "promote", "I-0001", "--to", "goal", "--rationale", "Goal-sized"])

    result = runner.invoke(app, ["idea", "create-goal", "I-0001"])

    assert result.exit_code == 0
    assert "created_goal_id: G-0001" in result.output
    assert "next: devflow goal show G-0001" in result.output
    assert (tmp_path / ".devflow" / "goals" / "G-0001" / "idea-link.yaml").exists()


def test_cli_create_task_from_promoted_idea_and_show_refs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["idea", "capture", "Add release report command", "--title", "Release report command"])
    runner.invoke(app, ["idea", "classify", "I-0001", "--maturity", "task_ready", "--note", "Task-sized"])
    runner.invoke(app, ["idea", "promote", "I-0001", "--to", "task", "--rationale", "Task-sized"])

    result = runner.invoke(app, ["idea", "create-task", "I-0001"])
    shown = runner.invoke(app, ["idea", "show", "I-0001"])

    assert result.exit_code == 0
    assert "created_task_id: task-0001" in result.output
    assert "next: devflow task show task-0001" in result.output
    assert "created_task_id: task-0001" in shown.output
    assert (tmp_path / ".devflow" / "tasks" / "task-0001" / "idea-link.yaml").exists()


def test_cli_create_dry_run_does_not_mutate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["idea", "capture", "Build release gate", "--title", "Release gate"])
    runner.invoke(app, ["idea", "classify", "I-0001", "--maturity", "goal_ready", "--note", "Ready"])
    runner.invoke(app, ["idea", "promote", "I-0001", "--to", "goal", "--rationale", "Goal-sized"])
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())

    result = runner.invoke(app, ["idea", "create-goal", "I-0001", "--dry-run"])
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())

    assert result.exit_code == 0
    assert "would_create_goal: yes" in result.output
    assert "created_goal_id: G-0001" in result.output
    assert before == after
