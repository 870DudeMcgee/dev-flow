from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.freshness import run_freshness_loop
from devflow.control_room.goal_lifecycle import ensure_goal_lifecycle
from devflow.control_room.goal_spec_projection import build_goal_board, build_spec_board


runner = CliRunner()


def _create_goal(root: Path) -> Path:
    brief = root / "brief.md"
    brief.write_text("# Operating layer goal\n", encoding="utf-8")
    result = runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief)])
    assert result.exit_code == 0, result.output
    ensure_goal_lifecycle(root, "G-0001")
    return root / ".devflow" / "goals" / "G-0001"


def test_build_goal_board_projects_lanes_batches_and_scoped_commands(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    goal_dir = _create_goal(tmp_path)
    (goal_dir / "task-slices.yaml").write_text(
        """
task_slices:
  - task_id: TS-0001
    title: "Snapshot contract"
    summary: "Project the goal board."
    risk: "medium"
    execution_mode: "HITL"
    parallel_safe: true
    shared_files:
      - src/devflow/control_room/operating_layer.py
  - task_id: TS-0002
    title: "Blocked shell"
    summary: "Wait for the first slice."
    blocked_by:
      - TS-0001
  - task_id: TS-0003
    title: "Existing task"
    summary: "Exercise linked task scoping."
    parallel_safe: true
""".lstrip(),
        encoding="utf-8",
    )
    created = runner.invoke(app, ["goal", "create-task", "G-0001", "TS-0003"])
    assert created.exit_code == 0, created.output

    freshness = run_freshness_loop(tmp_path, write_snapshot=False)
    board = build_goal_board(tmp_path, freshness, project_id="demo")

    assert board[0].goal_id == "G-0001"
    assert board[0].lifecycle == "active"
    assert board[0].ready_parallel_batch_count == 1
    assert board[0].parallel_batches[0].lane_ids == ["TS-0001"]
    assert board[0].parallel_batches[0].actions[0].command == "devflow goal create-task G-0001 TS-0001"
    assert board[0].ready_lanes[0].command == "devflow goal create-task G-0001 TS-0001"
    assert board[0].blocked_lanes[0].blockers == ["TS-0001"]
    linked_lane = next(lane for lane in board[0].lanes if lane.slice_id == "TS-0003")
    assert linked_lane.actions[-1].command == "devflow task show task-0001 --project demo"


def test_build_goal_board_with_lifecycle_projection_failure_appends_warning_and_uses_fallback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _create_goal(tmp_path)

    def _broken_projection(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("projection failed")

    monkeypatch.setattr(
        "devflow.control_room.goal_projection.build_goal_status_projection",
        _broken_projection,
    )

    freshness = run_freshness_loop(tmp_path, write_snapshot=False)
    fallback = next(goal.goal_state for goal in freshness.goal_loop if goal.goal_id == "G-0001")
    expected = "missing" if fallback == "missing_lifecycle" else fallback
    warnings: list[str] = []
    board = build_goal_board(tmp_path, freshness, project_id="demo", warnings=warnings)

    assert board[0].goal_id == "G-0001"
    assert board[0].lifecycle == expected
    assert board[0].lifecycle_reason == ""
    assert any("goal lifecycle projection failed for G-0001" in warning for warning in warnings)


def test_build_spec_board_projects_slices_and_references(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    goal_dir = _create_goal(tmp_path)
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "DEVFLOW_SOURCE_OF_TRUTH.md").write_text("# DevFlow Source of Truth\n", encoding="utf-8")
    (tmp_path / "docs" / "README.md").write_text("# DevFlow Docs\n", encoding="utf-8")
    standards_dir = tmp_path / ".devflow" / "standards"
    standards_dir.mkdir(parents=True)
    (tmp_path / "docs" / "standards.md").write_text("# Python Control Room Standard\n", encoding="utf-8")
    (standards_dir / "index.yml").write_text(
        """
standards:
  - path: docs/standards.md
    title: Python Control Room Standard
""".lstrip(),
        encoding="utf-8",
    )
    contracts_dir = tmp_path / ".devflow" / "layers" / "architecture"
    contracts_dir.mkdir(parents=True)
    (contracts_dir / "contracts.md").write_text(
        """
# Contracts

- [Source of Truth](../../../docs/DEVFLOW_SOURCE_OF_TRUTH.md)
- [Docs Index](../../../docs/README.md)
""".lstrip(),
        encoding="utf-8",
    )
    (goal_dir / "context").mkdir(exist_ok=True)
    (goal_dir / "context" / "relevant-files.md").write_text(
        "# Relevant Files\n\n- docs/DEVFLOW_SOURCE_OF_TRUTH.md\n- docs/README.md\n",
        encoding="utf-8",
    )
    (goal_dir / "task-slices.yaml").write_text(
        """
task_slices:
  - task_id: TS-0001
    title: "Snapshot contract"
    summary: "Project the spec board."
    risk: "medium"
    execution_mode: "HITL"
    parallel_safe: true
  - task_id: TS-0002
    title: "Browser shell"
    summary: "Wait for the first slice."
    blocked_by:
      - TS-0001
""".lstrip(),
        encoding="utf-8",
    )

    freshness = run_freshness_loop(tmp_path, write_snapshot=False)
    board = build_spec_board(tmp_path, freshness)

    assert board[0].goal_id == "G-0001"
    assert board[0].slice_count == 2
    assert board[0].slices[0].state == "parallel_candidate"
    assert board[0].slices[1].state == "blocked"
    reference_paths = {reference.path for reference in board[0].references}
    assert "docs/DEVFLOW_SOURCE_OF_TRUTH.md" in reference_paths
    assert "docs/README.md" in reference_paths
    assert "docs/standards.md" in reference_paths
    assert board[0].references[0].kind == "goal_reference"
    assert any(reference.title == "Python Control Room Standard" for reference in board[0].references)


def test_build_spec_board_with_malformed_task_slices_yaml_does_not_crash_and_warns(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    goal_dir = _create_goal(tmp_path)
    (goal_dir / "task-slices.yaml").write_text("task_slices: [\n  - task_id: TS-0001\n", encoding="utf-8")
    warnings: list[str] = []

    freshness = run_freshness_loop(tmp_path, write_snapshot=False)
    board = build_spec_board(tmp_path, freshness, warnings=warnings)

    assert board[0].goal_id == "G-0001"
    assert board[0].slice_count == 0
    assert board[0].slices == []
    assert any("task-slices.yaml" in warning and "failed to parse" in warning for warning in warnings)


def test_build_spec_board_with_wrong_task_slices_shape_warns(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    goal_dir = _create_goal(tmp_path)
    (goal_dir / "task-slices.yaml").write_text("task_slices:\n  bad: shape\n", encoding="utf-8")
    warnings: list[str] = []

    freshness = run_freshness_loop(tmp_path, write_snapshot=False)
    board = build_spec_board(tmp_path, freshness, warnings=warnings)

    assert board[0].slice_count == 0
    assert any("task-slices.yaml task_slices must be a list" in warning for warning in warnings)


@pytest.mark.parametrize("standards_path", ("index.yml", "index.json"))
def test_build_spec_board_with_malformed_standards_index_yaml_or_json(
    tmp_path: Path,
    monkeypatch,
    standards_path: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    goal_dir = _create_goal(tmp_path)
    (goal_dir / "task-slices.yaml").write_text(
        """
task_slices:
  - task_id: TS-0001
    title: "Snapshot contract"
    summary: "Project the spec board."
    risk: "medium"
""".lstrip(),
        encoding="utf-8",
    )
    standards_dir = tmp_path / ".devflow" / "standards"
    standards_dir.mkdir(parents=True)
    (standards_dir / standards_path).write_text("standards: [", encoding="utf-8")
    warnings: list[str] = []

    freshness = run_freshness_loop(tmp_path, write_snapshot=False)
    board = build_spec_board(tmp_path, freshness, warnings=warnings)

    assert board[0].goal_id == "G-0001"
    assert board[0].slice_count == 1
    assert board[0].references == []
    assert any("standards" in warning and "failed to parse" in warning for warning in warnings)


def test_build_spec_board_with_wrong_standards_index_shape_warns(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    goal_dir = _create_goal(tmp_path)
    (goal_dir / "task-slices.yaml").write_text("task_slices: []\n", encoding="utf-8")
    standards_dir = tmp_path / ".devflow" / "standards"
    standards_dir.mkdir(parents=True)
    (standards_dir / "index.yml").write_text("standards: not-a-list\n", encoding="utf-8")
    warnings: list[str] = []

    freshness = run_freshness_loop(tmp_path, write_snapshot=False)
    board = build_spec_board(tmp_path, freshness, warnings=warnings)

    assert board[0].references == []
    assert any("standards index entries must be a list" in warning for warning in warnings)
