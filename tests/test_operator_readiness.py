from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import get_task, save_task
from tests.helpers import setup_temp_git_repo


runner = CliRunner()


def _operator_fixture(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    project_dir = tmp_path / ".devflow" / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "id": "operator-console",
                "project_id": "operator-console",
                "name": "Operator Console",
                "root_path": tmp_path.as_posix(),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    brief = tmp_path / "goal.md"
    brief.write_text("## Goal Brief\nMake the operating layer truthful.\n", encoding="utf-8")
    goal = runner.invoke(app, ["goal", "init", "G-0004", "--from", str(brief)])
    assert goal.exit_code == 0, goal.output

    slices_path = tmp_path / ".devflow" / "goals" / "G-0004" / "task-slices.yaml"
    slices_path.write_text(
        yaml.safe_dump(
            {
                "task_slices": [
                    {
                        "task_id": "TS-0002",
                        "title": "Reconcile operating-layer state",
                        "summary": "Align counts, lifecycle blockers, warnings, and next actions.",
                        "parallel_safe": True,
                        "shared_files": ["src/devflow/control_room/operator_readiness.py"],
                        "risk": "low",
                        "execution_mode": "AFK",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    generated = runner.invoke(app, ["task", "create", "G-0004 • Slice 2"])
    assert generated.exit_code == 0, generated.output
    descriptive = runner.invoke(app, ["task", "create", "Implement lifecycle readiness gate"])
    assert descriptive.exit_code == 0, descriptive.output

    linked_task = get_task(tmp_path, "task-0001")
    linked_task.status = "created"
    save_task(tmp_path / ".devflow" / "tasks" / linked_task.id, linked_task)
    (tmp_path / ".devflow" / "tasks" / linked_task.id / "goal-link.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "goal_id": "G-0004",
                "goal_path": ".devflow/goals/G-0004",
                "slice_id": "TS-0002",
                "slice_source_path": ".devflow/goals/G-0004/task-slices.yaml",
                "created_from_goal_slice": True,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    (tmp_path / ".devflow" / "goals" / "G-0004" / "goal-state.yaml").unlink()

    stale_snapshot = {
        "schema_version": 1,
        "status": "ok",
        "goal_loop": [
            {
                "goal_id": "G-0004",
                "title": "Make the operating layer truthful",
                "goal_state": "active",
                "loop_state": "ready_for_parallel_task_creation",
                "next_action": "Parallel batch PB-0001: devflow freshness create-batch G-0004 PB-0001",
                "parallel_batches": [
                    {
                        "batch_id": "PB-0001",
                        "lane_ids": ["TS-0002"],
                        "commands": ["devflow goal create-task G-0004 TS-0002"],
                        "shared_files": ["src/devflow/control_room/operator_readiness.py"],
                        "reason": "stale recommendation captured before lifecycle state disappeared",
                    }
                ],
            }
        ],
        "next_action": "Continue.",
    }
    freshness_dir = tmp_path / ".devflow" / "freshness"
    freshness_dir.mkdir(parents=True, exist_ok=True)
    (freshness_dir / "latest.json").write_text(json.dumps(stale_snapshot, indent=2) + "\n", encoding="utf-8")


def _operator_snapshot(root: Path):
    from devflow.control_room.operator_readiness import build_operator_readiness_snapshot

    return build_operator_readiness_snapshot(root).model_dump(mode="json")


def test_missing_goal_lifecycle_is_visible_without_tasks(tmp_path: Path, monkeypatch) -> None:
    setup_temp_git_repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    brief = tmp_path / "goal.md"
    brief.write_text("## Goal Brief\nMake lifecycle state visible.\n", encoding="utf-8")
    goal = runner.invoke(app, ["goal", "init", "G-0001", "--from", str(brief)])
    assert goal.exit_code == 0, goal.output
    (tmp_path / ".devflow" / "goals" / "G-0001" / "goal-state.yaml").unlink()

    payload = _operator_snapshot(tmp_path)

    assert payload["counts"]["total_tasks"] == 0
    assert payload["counts"]["lifecycle_blocked"] == 1
    assert payload["next_safe_action"]["kind"] == "repair_goal_lifecycle"
    assert payload["next_safe_action"]["command"].startswith("devflow goal activate G-0001")
    assert payload["warnings"][0]["code"] == "goal_lifecycle_missing"

    dashboard = runner.invoke(app, ["dashboard"])
    assert dashboard.exit_code == 0, dashboard.output
    assert "Lifecycle blocked: 1" in dashboard.output
    assert "Goal lifecycle repair is required before worker dispatch." in dashboard.output
    assert "Control room is clean" not in dashboard.output


def test_generated_task_uses_descriptive_label_with_ids_as_secondary_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _operator_fixture(tmp_path, monkeypatch)

    payload = _operator_snapshot(tmp_path)

    assert payload["project"]["display_name"] == "Operator Console"
    tasks = {task["task_id"]: task for task in payload["tasks"]}
    generated = tasks["task-0001"]
    assert generated["display"]["primary"] == "Reconcile operating-layer state"
    assert generated["display"]["raw_title"] == "G-0004 • Slice 2"
    assert generated["display"]["ids"] == {
        "task_id": "task-0001",
        "goal_id": "G-0004",
        "slice_id": "TS-0002",
    }
    assert "task-0001" in generated["display"]["secondary"]
    assert "G-0004" in generated["display"]["secondary"]
    assert "TS-0002" in generated["display"]["secondary"]

    descriptive = tasks["task-0002"]
    assert descriptive["display"]["primary"] == "Implement lifecycle readiness gate"
    assert descriptive["display"]["raw_title"] == "Implement lifecycle readiness gate"


def test_missing_lifecycle_blocks_goal_linked_task_readiness(tmp_path: Path, monkeypatch) -> None:
    _operator_fixture(tmp_path, monkeypatch)

    payload = _operator_snapshot(tmp_path)

    tasks = {task["task_id"]: task for task in payload["tasks"]}
    linked = tasks["task-0001"]
    unlinked = tasks["task-0002"]

    assert linked["readiness"]["state"] == "blocked"
    assert linked["readiness"]["blocked_by"][0]["code"] == "goal_lifecycle_missing"
    assert linked["readiness"]["blocked_by"][0]["goal_id"] == "G-0004"
    assert linked["readiness"]["worker_ready"] is False

    assert unlinked["readiness"]["state"] == "worker_ready"
    assert unlinked["readiness"]["worker_ready"] is True
    assert payload["counts"]["worker_ready"] == 1
    assert payload["counts"]["lifecycle_blocked"] == 1


def test_next_safe_action_prioritizes_lifecycle_repair_and_warns_on_stale_directives(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _operator_fixture(tmp_path, monkeypatch)

    payload = _operator_snapshot(tmp_path)

    assert payload["next_safe_action"]["kind"] == "repair_goal_lifecycle"
    assert payload["next_safe_action"]["command"].startswith("devflow goal activate G-0004")
    assert "lifecycle" in payload["next_safe_action"]["reason"].lower()
    assert "devflow task run task-0002" not in payload["next_safe_action"]["command"]

    warnings = {warning["code"]: warning for warning in payload["warnings"]}
    stale = warnings["stale_freshness_directive"]
    assert stale["goal_id"] == "G-0004"
    assert stale["blocked_by"] == "goal_lifecycle_missing"
    assert stale["stale_command"] == "devflow goal create-task G-0004 TS-0002"
    assert "Reconcile operating-layer state" in stale["message"]


def test_scheduler_status_uses_operator_readiness_counts_and_next_action(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room.scheduler_projection import build_scheduler_snapshot

    _operator_fixture(tmp_path, monkeypatch)

    payload = build_scheduler_snapshot(tmp_path).model_dump(mode="json")

    assert payload["operator_readiness"]["counts"]["worker_ready"] == 1
    assert payload["operator_readiness"]["counts"]["lifecycle_blocked"] == 1
    assert payload["operator_readiness"]["next_safe_action"]["kind"] == "repair_goal_lifecycle"
    assert payload["counts"]["ready"] == 1
    assert payload["counts"]["blocked"] == 1
    assert payload["next_safe_action"].startswith("devflow goal activate G-0004")


def test_status_json_exposes_shared_operator_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _operator_fixture(tmp_path, monkeypatch)

    result = runner.invoke(app, ["status", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["operator_readiness"]["counts"]["worker_ready"] == 1
    assert payload["operator_readiness"]["counts"]["lifecycle_blocked"] == 1
    assert payload["operator_readiness"]["next_safe_action"]["command"].startswith("devflow goal activate G-0004")
    assert payload["scheduler"]["next_safe_action"].startswith("devflow goal activate G-0004")


def test_dashboard_json_exposes_shared_operator_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _operator_fixture(tmp_path, monkeypatch)

    result = runner.invoke(app, ["dashboard", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["operator_readiness"]["counts"]["worker_ready"] == 1
    assert payload["operator_readiness"]["counts"]["lifecycle_blocked"] == 1
    assert payload["operator_readiness"]["next_safe_action"]["kind"] == "repair_goal_lifecycle"
    assert payload["next_action"]["command"].startswith("devflow goal activate G-0004")

    text = runner.invoke(app, ["dashboard"])
    assert text.exit_code == 0, text.output
    assert "Operator Readiness" in text.output
    assert "Lifecycle blocked: 1" in text.output
    assert "devflow goal activate G-0004" in text.output


def test_supervisor_packet_exposes_shared_operator_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _operator_fixture(tmp_path, monkeypatch)

    result = runner.invoke(app, ["supervisor", "packet", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)

    assert payload["operator_readiness"]["counts"]["worker_ready"] == 1
    assert payload["operator_readiness"]["counts"]["lifecycle_blocked"] == 1
    assert payload["operator_readiness"]["next_safe_action"]["command"].startswith("devflow goal activate G-0004")
    assert payload["scheduler"]["next_safe_action"].startswith("devflow goal activate G-0004")


def test_operating_layer_snapshot_exposes_shared_operator_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room.operating_layer import build_operating_layer_snapshot

    _operator_fixture(tmp_path, monkeypatch)

    payload = build_operating_layer_snapshot(tmp_path).model_dump(mode="json")

    assert payload["operator_readiness"]["counts"]["worker_ready"] == 1
    assert payload["operator_readiness"]["counts"]["lifecycle_blocked"] == 1
    assert payload["operator_readiness"]["next_safe_action"]["kind"] == "repair_goal_lifecycle"
    assert payload["next_action"]["command"].startswith("devflow goal activate G-0004")
