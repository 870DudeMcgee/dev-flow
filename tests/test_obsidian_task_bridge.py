from __future__ import annotations

import json
from pathlib import Path

import pytest

from devflow.control_room.obsidian_task_bridge import (
    build_curated_packet_preview,
    build_obsidian_task_preview,
    build_obsidian_scout_pack_preview,
    create_pipeline_run_from_curated_packet,
    create_task_from_obsidian_card,
    create_tasks_from_obsidian_scout_pack,
)
from tests.helpers import setup_temp_git_repo


def _events(root: Path, task_id: str) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (root / ".devflow" / "tasks" / task_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def test_obsidian_task_preview_does_not_mutate(tmp_path: Path) -> None:
    preview = build_obsidian_task_preview(
        {
            "card": {
                "id": "card-1",
                "title": "Fix worker lane copy",
                "path": "Inbox/worker-lane.md",
                "summary": "Tighten the wording",
                "next_action": "Update the backend copy",
                "evidence": "Operator note",
                "project": "[[Dev-Flow]]",
            }
        }
    )

    assert preview["ok"] is True
    assert preview["source"] == "obsidian"
    assert preview["title"] == "Fix worker lane copy"
    assert preview["source_path"] == "Inbox/worker-lane.md"
    assert preview["source_card_id"] == "card-1"
    assert preview["project"] == "[[Dev-Flow]]"
    assert "Review source note: Inbox/worker-lane.md." in preview["definition_of_done"]
    assert "Next action: Update the backend copy." in preview["definition_of_done"]
    assert not (tmp_path / ".devflow" / "tasks").exists()


def test_obsidian_task_create_creates_task_and_appends_link_event(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    created = create_task_from_obsidian_card(
        tmp_path,
        {
            "card": {
                "id": "card-9",
                "summary": "Route intake card into task creation",
                "path": "Inbox/task-bridge.md",
                "nextAction": "Create the real task",
                "evidence": "Scanned from Obsidian",
                "project": "[[Dev-Flow]]",
            }
        },
    )

    assert created["ok"] is True
    assert created["task_id"] == "task-0001"
    assert created["title"] == "Route intake card into task creation"
    assert created["event"] == "obsidian_card_linked"
    assert created["status"] == "created"
    assert created["last_event"] == "task_created"

    events = _events(tmp_path, created["task_id"])
    assert [event["event"] for event in events] == ["task_created", "obsidian_card_linked"]
    assert events[0]["definition_of_done"] == created["definition_of_done"]
    assert events[1]["source"] == "obsidian"
    assert events[1]["source_path"] == "Inbox/task-bridge.md"
    assert events[1]["source_card_id"] == "card-9"
    assert events[1]["project"] == "[[Dev-Flow]]"


def test_obsidian_scout_pack_preview_returns_five_task_definitions(tmp_path: Path) -> None:
    payload = {
        "card": {
            "id": "card-scout-pack-1",
            "title": "Scout deck",
            "path": "Inbox/scout-pack.md",
            "summary": "Run a grouped review across scout disciplines",
            "next_action": "Review five focus areas",
            "evidence": "Captured from architecture + UX pass",
            "project": "[[Dev-Flow]]",
        }
    }

    preview = build_obsidian_scout_pack_preview(payload)

    assert preview["ok"] is True
    assert preview["source"] == "obsidian"
    assert preview["source_path"] == "Inbox/scout-pack.md"
    assert preview["source_card_id"] == "card-scout-pack-1"
    assert preview["project"] == "[[Dev-Flow]]"
    tasks = preview["tasks"]
    assert isinstance(tasks, list) and len(tasks) == 5
    assert preview["task_count"] == 5
    assert [task["title"] for task in tasks] == [
        "Architecture Scout",
        "UX Scout",
        "Data Truth Scout",
        "Verification Scout",
        "Dead Code Scout",
    ]
    assert not (tmp_path / ".devflow" / "tasks").exists()


def test_obsidian_scout_pack_create_makes_five_tasks_and_link_events(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    created = create_tasks_from_obsidian_scout_pack(
        tmp_path,
        {
            "card": {
                "id": "card-scout-pack-2",
                "title": "Scout pack for launch",
                "path": "Inbox/scout-pack-create.md",
                "summary": "Generate five visible tasks from this card",
                "nextAction": "Create all five scouts",
                "evidence": "Scanned card with grouped instruction",
                "project": "[[Dev-Flow]]",
            }
        },
    )

    created_tasks = created["tasks"]
    assert created["task_count"] == 5
    assert created["event"] == "obsidian_scout_pack_linked"
    assert len(created_tasks) == 5
    assert [item["title"] for item in created_tasks] == [
        "Architecture Scout",
        "UX Scout",
        "Data Truth Scout",
        "Verification Scout",
        "Dead Code Scout",
    ]
    assert [item["status"] for item in created_tasks] == ["created"] * 5
    assert [item["event"] for item in created_tasks] == ["obsidian_scout_pack_linked"] * 5
    assert [item["last_event"] for item in created_tasks] == ["task_created"] * 5

    for item in created_tasks:
        events = _events(tmp_path, item["task_id"])
        assert [event["event"] for event in events] == ["task_created", "obsidian_scout_pack_linked"]
        assert events[1]["source"] == "obsidian"
        assert events[1]["source_path"] == "Inbox/scout-pack-create.md"
        assert events[1]["source_card_id"] == "card-scout-pack-2"
        assert events[1]["project"] == "[[Dev-Flow]]"


def test_curated_packet_preview_validates_required_fields() -> None:
    with pytest.raises(ValueError):
        build_curated_packet_preview({"repo": "test"})
    with pytest.raises(ValueError):
        build_curated_packet_preview({"source": "obsidian", "repo": "test"})


def test_curated_packet_preview_returns_fields(tmp_path: Path) -> None:
    payload = {
        "source": "obsidian-handoff",
        "repo": "/tmp/test-repo",
        "operator_intent": "Refactor the handler module",
        "constraints": "No breaking changes",
        "acceptance_criteria": "All tests pass",
        "suggested_preset": "builder-judge",
        "known_docs_files": ["docs/arch.md"],
    }
    preview = build_curated_packet_preview(payload)
    assert preview["ok"] is True
    assert preview["source"] == "obsidian-handoff"
    assert preview["operator_intent"] == "Refactor the handler module"
    assert preview["will_create_run"] is True
    assert not (tmp_path / ".devflow").exists()


def test_curated_packet_create_creates_pipeline_run(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    payload = {
        "source": "obsidian-handoff",
        "repo": str(tmp_path),
        "operator_intent": "Extract handler methods",
        "constraints": None,
        "acceptance_criteria": "Tests pass",
        "suggested_preset": "refactor-recovery",
        "known_docs_files": [],
    }
    result = create_pipeline_run_from_curated_packet(tmp_path, payload)
    assert result["ok"] is True
    assert result["run_id"]
    assert result["status"] == "created"
    runs_dir = tmp_path / ".devflow" / "pipeline-runs" / result["run_id"]
    assert (runs_dir / "intent.md").exists()
    assert (runs_dir / "source.json").exists()
