from __future__ import annotations

import json
from pathlib import Path

import pytest

from devflow.control_room.service import create_task
from devflow.control_room.task_show_summary import (
    TaskShowSummary,
    TaskShowSummaryError,
    build_task_show_summary,
    render_task_show_summary,
)
from tests.helpers import setup_temp_git_repo


def _create_task(root: Path) -> None:
    setup_temp_git_repo(root)
    create_task(root, "summary task")


def _snapshot_devflow_files(root: Path) -> dict[str, bytes]:
    devflow_root = root / ".devflow"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(devflow_root.rglob("*"))
        if path.is_file()
    }


def test_created_task_rendering_uses_stable_labels(tmp_path: Path) -> None:
    _create_task(tmp_path)

    summary = build_task_show_summary(tmp_path, "task-0001")
    lines = render_task_show_summary(summary)

    assert isinstance(summary, TaskShowSummary)
    assert lines[0] == "task: task-0001"
    assert "title: summary task" in lines
    assert "status: created" in lines
    assert "worker: shell" in lines
    assert "workspace: .devflow/workspaces/task-0001" in lines
    assert "verification_status: not_run" in lines
    assert "packet_artifact: missing" in lines
    assert "latest_events:" in lines
    assert "result_summary:" in lines


def test_build_task_show_summary_is_read_only(tmp_path: Path) -> None:
    _create_task(tmp_path)
    before = _snapshot_devflow_files(tmp_path)

    summary = build_task_show_summary(tmp_path, "task-0001")

    assert render_task_show_summary(summary)
    assert _snapshot_devflow_files(tmp_path) == before


def test_missing_task_raises_user_facing_error(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    with pytest.raises(TaskShowSummaryError) as excinfo:
        build_task_show_summary(tmp_path, "task-9999")

    assert "Task not found: task-9999" in str(excinfo.value)


def test_malformed_events_are_rendered_without_hiding_promoted_changes(tmp_path: Path) -> None:
    _create_task(tmp_path)
    events_path = tmp_path / ".devflow" / "tasks" / "task-0001" / "events.jsonl"
    events_path.write_text(
        events_path.read_text(encoding="utf-8")
        + json.dumps(
            {
                "timestamp": "2026-06-25T00:00:00+00:00",
                "event": "task_promoted",
                "added": ["new.txt"],
                "modified": ["changed.txt"],
                "deleted_applied": ["old.txt"],
            },
            sort_keys=True,
        )
        + "\n"
        + "this is a malformed json line\n",
        encoding="utf-8",
    )

    lines = render_task_show_summary(build_task_show_summary(tmp_path, "task-0001"))

    assert "promoted_changes:" in lines
    assert "  added: new.txt" in lines
    assert "  modified: changed.txt" in lines
    assert "  deleted_applied: old.txt" in lines
    assert "  this is a malformed json line" in lines


def test_artifact_and_evidence_sections_render_from_existing_files(tmp_path: Path) -> None:
    _create_task(tmp_path)
    task_path = tmp_path / ".devflow" / "tasks" / "task-0001"
    (task_path / "packet.json").write_text('{"task_id":"task-0001"}\n', encoding="utf-8")
    run_dir = task_path / "local-model-runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "response.md").write_text("local evidence", encoding="utf-8")
    (run_dir / "proposal.json").write_text(
        json.dumps(
            {
                "classification": "advisory_only",
                "has_patch_candidate": False,
                "proposal_path": ".devflow/tasks/task-0001/local-model-runs/run-1/proposal.md",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    lines = render_task_show_summary(build_task_show_summary(tmp_path, "task-0001"))

    assert "packet_artifact: exists" in lines
    assert "packet_path: .devflow/tasks/task-0001/packet.json" in lines
    assert "Local Model Runs:" in lines
    assert "  latest: .devflow/tasks/task-0001/local-model-runs/run-1/response.md" in lines
    assert "Normalized Proposals:" in lines
    assert "  classification: advisory_only" in lines
