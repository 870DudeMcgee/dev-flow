from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.persistence import save_task
from devflow.control_room.service import create_task


def test_stable_routing_evidence_commands_resolve_ancestor_project_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / ".devflow/tasks").mkdir(parents=True)
    (tmp_path / ".devflow/workspaces").mkdir(parents=True)
    task = create_task(tmp_path, "Clean up documentation")
    save_task(tmp_path / ".devflow/tasks" / task.id, task)
    nested = tmp_path / "src" / "devflow" / "control_room"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    runner = CliRunner()
    commands = [
        ["task", "fit", task.id, "--json"],
        ["task", "scout", task.id, "--role", "risk", "--json"],
        ["task", "route", task.id, "--json"],
        ["task", "scorecard", task.id, "--json"],
    ]

    for command in commands:
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["task_id"] == task.id

    task_dir = tmp_path / ".devflow/tasks" / task.id
    assert (task_dir / "task-fit.yaml").exists()
    assert (task_dir / "scout-risk.yaml").exists()
    assert (task_dir / "routing-decision.yaml").exists()
    assert (task_dir / "routing-quality-scorecard.yaml").exists()


def test_stable_routing_evidence_commands_resolve_registered_project_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("DEVFLOW_HOME", (tmp_path / "home" / ".devflow").as_posix())
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"
    control_root.mkdir()
    runner = CliRunner()

    created_project = runner.invoke(
        app,
        [
            "project",
            "create",
            "Alpha App",
            "--projects-root",
            projects_root.as_posix(),
            "--source-control",
            "none",
        ],
    )
    assert created_project.exit_code == 0, created_project.output
    project_root = projects_root / "alpha-app"
    task = create_task(project_root, "Clean up documentation")
    save_task(project_root / ".devflow/tasks" / task.id, task)
    monkeypatch.chdir(control_root)

    fit = runner.invoke(app, ["task", "fit", task.id, "--project", "alpha-app", "--json"])
    scout = runner.invoke(app, ["task", "scout", task.id, "--project", "alpha-app", "--role", "risk", "--json"])
    route = runner.invoke(app, ["task", "route", task.id, "--project", "alpha-app", "--json"])
    scorecard = runner.invoke(app, ["task", "scorecard", task.id, "--project", "alpha-app", "--json"])
    context_pack = runner.invoke(
        app,
        [
            "agent",
            "context-pack",
            task.id,
            "qwopus-implementer",
            "--project",
            "alpha-app",
            "--role",
            "reviewer",
            "--json",
        ],
    )

    assert fit.exit_code == 0, fit.output
    assert scout.exit_code == 0, scout.output
    assert route.exit_code == 0, route.output
    assert scorecard.exit_code == 0, scorecard.output
    assert context_pack.exit_code == 0, context_pack.output

    fit_payload = json.loads(fit.output)
    scout_payload = json.loads(scout.output)
    route_payload = json.loads(route.output)
    scorecard_payload = json.loads(scorecard.output)
    pack_payload = json.loads(context_pack.output)
    assert set(fit_payload) == {"task_id", "artifact_path", "fit_data"}
    assert set(scout_payload) == {"task_id", "artifact_paths", "reports"}
    assert set(route_payload) == {"task_id", "artifact_path", "routing_decision"}
    assert set(scorecard_payload) == {"task_id", "artifact_path", "scorecard"}
    assert set(pack_payload) == {
        "agent_id",
        "estimated_chars",
        "estimated_tokens",
        "json_path",
        "markdown_path",
        "packet_path",
        "permission_mode",
        "role",
        "task_id",
    }

    rd = route_payload["routing_decision"]
    assert rd["recommended_next_commands"]["verifier"].startswith(
        f"devflow task verify {task.id} --project alpha-app"
    )
    assert rd["recommended_next_commands"]["planner"] == (
        f"devflow agent context-pack {task.id} <agent-id> --project alpha-app --role planner --json"
    )
    assert rd["recommended_next_commands"]["reviewer"] == (
        f"devflow agent context-pack {task.id} <agent-id> --project alpha-app --role reviewer --json"
    )

    task_dir = project_root / ".devflow/tasks" / task.id
    assert (task_dir / "task-fit.yaml").exists()
    assert (task_dir / "scout-risk.yaml").exists()
    assert (task_dir / "routing-decision.yaml").exists()
    assert (task_dir / "routing-quality-scorecard.yaml").exists()
    assert (task_dir / "context-packs" / "reviewer-qwopus-implementer.json").exists()
    assert not (control_root / ".devflow").exists()
