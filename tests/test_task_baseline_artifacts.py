from __future__ import annotations

import json
from pathlib import Path

import yaml

from devflow.control_room.df_telegram_bridge import decompose_goal_into_tasks
from devflow.control_room.goal_tasks import create_task_from_goal_slice
from devflow.control_room.idea_execution_bridge import create_task_from_idea
from devflow.control_room.idea_foundry import capture_idea, classify_idea, promote_idea
from devflow.control_room.service import create_task


BASELINE_ARTIFACTS = {
    "task.yaml",
    "events.jsonl",
    "questions.jsonl",
    "result.md",
    "verification.json",
    "logs/worker.log",
    "logs/verify.log",
    "merge-readiness.json",
}


def _assert_baseline(root: Path, task_id: str) -> None:
    task_path = root / ".devflow" / "tasks" / task_id
    missing = [name for name in sorted(BASELINE_ARTIFACTS) if not (task_path / name).exists()]
    assert missing == []

    verification = json.loads((task_path / "verification.json").read_text(encoding="utf-8"))
    readiness = json.loads((task_path / "merge-readiness.json").read_text(encoding="utf-8"))
    assert verification["task_id"] == task_id
    assert verification["status"] == "not_run"
    assert readiness["task_id"] == task_id
    assert readiness["ready"] is False


def test_create_task_writes_complete_baseline_artifacts(tmp_path: Path) -> None:
    task = create_task(tmp_path, "complete baseline")

    _assert_baseline(tmp_path, task.id)


def test_goal_idea_and_telegram_task_paths_share_complete_baseline(tmp_path: Path) -> None:
    goal_path = tmp_path / ".devflow" / "goals" / "G-0001"
    goal_path.mkdir(parents=True)
    (goal_path / "task-slices.yaml").write_text(
        yaml.safe_dump(
            {
                "task_slices": [
                    {
                        "task_id": "TS-0001",
                        "title": "Goal slice task",
                        "summary": "Create a task from a goal slice.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    from_goal = create_task_from_goal_slice(tmp_path, "G-0001", "TS-0001")
    _assert_baseline(tmp_path, from_goal.task_id)

    idea = capture_idea(tmp_path, "Turn this idea into a task", title="Idea task")
    classify_idea(tmp_path, idea["id"], maturity="task_ready", note="ready")
    promote_idea(tmp_path, idea["id"], target="task", rationale="approved")
    from_idea = create_task_from_idea(tmp_path, idea["id"])
    _assert_baseline(tmp_path, from_idea.created_id)

    telegram_goal = tmp_path / ".devflow" / "goals" / "G-0002"
    telegram_goal.mkdir(parents=True)
    (telegram_goal / "intent-metadata.yaml").write_text(
        "priority: medium\neffort: small\nsuggested_roles: [implementer]\n",
        encoding="utf-8",
    )
    telegram_ids = decompose_goal_into_tasks("G-0002", telegram_goal, tmp_path)
    assert len(telegram_ids) == 1
    _assert_baseline(tmp_path, telegram_ids[0])
