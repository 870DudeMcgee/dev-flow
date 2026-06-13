from __future__ import annotations

from pathlib import Path

import yaml

from devflow.control_room.idea_execution_bridge import (
    IdeaExecutionBridgeError,
    create_goal_from_idea,
    create_task_from_idea,
    preview_goal_from_idea,
    preview_task_from_idea,
)
from devflow.control_room.idea_foundry import capture_idea, classify_idea, promote_idea, show_idea


def _promoted_goal_idea(root: Path) -> str:
    item = capture_idea(
        root,
        "Build a release gate that checks docs, tests, dogfood evidence, and stale context.",
        title="Release gate",
        tags=["release"],
    )
    classify_idea(root, item["id"], maturity="goal_ready", note="Ready to become a goal.", tags=["release"])
    promote_idea(root, item["id"], target="goal", rationale="This is broad enough to track as a goal.")
    return item["id"]


def _promoted_task_idea(root: Path) -> str:
    item = capture_idea(
        root,
        "Add a command that prints the latest release readiness report path.",
        title="Release readiness report path",
        tags=["release"],
    )
    classify_idea(root, item["id"], maturity="task_ready", note="Narrow task.", tags=["release"])
    promote_idea(root, item["id"], target="task", rationale="This is ready as one task.")
    return item["id"]


def test_create_goal_from_promoted_idea_links_both_sides(tmp_path: Path) -> None:
    idea_id = _promoted_goal_idea(tmp_path)

    created = create_goal_from_idea(tmp_path, idea_id)

    assert created.target == "goal"
    assert created.created_id == "G-0001"
    goal_dir = tmp_path / ".devflow" / "goals" / "G-0001"
    assert (goal_dir / "goal.yaml").exists()
    assert (goal_dir / "goal.md").exists()
    link = yaml.safe_load((goal_dir / "idea-link.yaml").read_text(encoding="utf-8"))
    assert link["idea_id"] == idea_id
    assert link["promotion_target"] == "goal"
    assert link["created_from_idea"] is True

    metadata, raw, classification, promotion = show_idea(tmp_path, idea_id)
    assert metadata["created_goal_id"] == "G-0001"
    assert metadata["created_goal_path"] == ".devflow/goals/G-0001"
    assert metadata["created_task_id"] is None
    assert "release gate" in raw.lower()
    assert "Ready to become a goal" in classification
    assert "target: goal" in promotion
    assert (tmp_path / ".devflow" / "ideas" / idea_id / "goal-brief.md").exists()
    assert not (tmp_path / ".devflow" / "tasks").exists()


def test_create_task_from_promoted_idea_creates_task_without_running_worker(tmp_path: Path) -> None:
    idea_id = _promoted_task_idea(tmp_path)

    created = create_task_from_idea(tmp_path, idea_id)

    assert created.target == "task"
    assert created.created_id == "task-0001"
    task_dir = tmp_path / ".devflow" / "tasks" / "task-0001"
    assert (task_dir / "task.yaml").exists()
    assert (task_dir / "idea.md").exists()
    link = yaml.safe_load((task_dir / "idea-link.yaml").read_text(encoding="utf-8"))
    assert link["idea_id"] == idea_id
    assert link["promotion_target"] == "task"
    assert link["created_from_idea"] is True

    task_yaml = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    assert task_yaml["status"] == "created"
    assert task_yaml["verification_status"] == "not_run"
    assert (task_dir / "logs" / "worker.log").read_text(encoding="utf-8") == ""
    assert (task_dir / "logs" / "verify.log").read_text(encoding="utf-8") == ""

    metadata, _, _, _ = show_idea(tmp_path, idea_id)
    assert metadata["created_task_id"] == "task-0001"
    assert metadata["created_task_path"] == ".devflow/tasks/task-0001"
    assert metadata["created_goal_id"] is None


def test_bridge_refuses_missing_promotion_wrong_target_and_duplicates(tmp_path: Path) -> None:
    item = capture_idea(tmp_path, "Loose thought", title="Loose thought")
    classify_idea(tmp_path, item["id"], maturity="goal_ready", note="Maybe later.")

    try:
        create_goal_from_idea(tmp_path, item["id"])
    except IdeaExecutionBridgeError as exc:
        assert "must be promoted to goal" in str(exc)
    else:
        raise AssertionError("expected unpromoted idea to be refused")

    promote_idea(tmp_path, item["id"], target="goal", rationale="Now ready.")

    try:
        create_task_from_idea(tmp_path, item["id"])
    except IdeaExecutionBridgeError as exc:
        assert "not task" in str(exc)
    else:
        raise AssertionError("expected wrong target to be refused")

    create_goal_from_idea(tmp_path, item["id"])

    try:
        create_goal_from_idea(tmp_path, item["id"])
    except IdeaExecutionBridgeError as exc:
        assert "already created goal G-0001" in str(exc)
    else:
        raise AssertionError("expected duplicate goal creation to be refused")


def test_dry_run_previews_do_not_write(tmp_path: Path) -> None:
    goal_idea = _promoted_goal_idea(tmp_path)
    task_idea = _promoted_task_idea(tmp_path)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())

    goal_preview = preview_goal_from_idea(tmp_path, goal_idea)
    task_preview = preview_task_from_idea(tmp_path, task_idea, git_worktree=True)
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file())

    assert goal_preview.target == "goal"
    assert goal_preview.would_create is True
    assert goal_preview.created_id == "G-0001"
    assert task_preview.target == "task"
    assert task_preview.would_create is True
    assert task_preview.git_worktree is True
    assert task_preview.created_id == "task-0001"
    assert before == after
