from __future__ import annotations

from pathlib import Path

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


def test_build_spec_board_projects_slices_and_references(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    goal_dir = _create_goal(tmp_path)
    (tmp_path / "docs" / "architecture").mkdir(parents=True)
    (tmp_path / "PRODUCT_NORTH_STAR.md").write_text("# Product North Star\n", encoding="utf-8")
    (tmp_path / "docs" / "control-room-mvp.md").write_text("# Control Room MVP\n", encoding="utf-8")
    (tmp_path / "docs" / "mvp-contract.md").write_text("# MVP Contract\n", encoding="utf-8")
    (tmp_path / "docs" / "architecture" / "agent-registry-and-adapter-runtime.md").write_text(
        "# Agent Registry\n",
        encoding="utf-8",
    )
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

- [MVP](../../../docs/mvp-contract.md)
- [Registry](../../../docs/architecture/agent-registry-and-adapter-runtime.md)
""".lstrip(),
        encoding="utf-8",
    )
    (goal_dir / "context").mkdir(exist_ok=True)
    (goal_dir / "context" / "relevant-files.md").write_text(
        "# Relevant Files\n\n- PRODUCT_NORTH_STAR.md\n- docs/control-room-mvp.md\n",
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
    assert "PRODUCT_NORTH_STAR.md" in reference_paths
    assert "docs/control-room-mvp.md" in reference_paths
    assert "docs/standards.md" in reference_paths
    assert "docs/mvp-contract.md" in reference_paths
    assert board[0].references[0].kind == "goal_reference"
    assert any(reference.title == "Python Control Room Standard" for reference in board[0].references)
