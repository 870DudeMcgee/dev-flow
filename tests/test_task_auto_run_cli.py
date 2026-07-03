from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from devflow.cli import app


runner = CliRunner()


def _stub_auto_run_routing(monkeypatch, worker_id: str = "shell") -> None:
    fit_data = {
        "task_fit": {
            "archetype_id": "unknown",
            "requires_vision": False,
            "requires_thinking": "optional",
        },
        "repo_scan": {"total_context_estimate": 0},
    }
    decision_data = {
        "routing_decision": {
            "selected": {"worker": worker_id},
            "reason": [f"worker selected: {worker_id} (score=1)"],
            "unresolved": [],
        }
    }
    monkeypatch.setattr("devflow.control_room.estimator.estimate_task_fit", lambda *_args, **_kwargs: fit_data)
    monkeypatch.setattr("devflow.control_room.estimator.save_task_fit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("devflow.control_room.router.route_task", lambda *_args, **_kwargs: decision_data)
    monkeypatch.setattr("devflow.control_room.router.save_routing_decision", lambda *_args, **_kwargs: None)


def test_task_auto_run_experimental_dry_run_routes_without_executing(monkeypatch) -> None:
    monkeypatch.setenv("DEVFLOW_EXPERIMENTAL", "1")
    _stub_auto_run_routing(monkeypatch)
    executed = []

    def fail_if_executed(*args, **kwargs):
        executed.append((args, kwargs))
        raise AssertionError("dry-run must not execute a worker")

    monkeypatch.setattr("devflow.control_room.task_auto_run_command.task_service.run_shell_task", fail_if_executed)

    result = runner.invoke(app, ["task", "auto-run", "task-0001", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "selected_worker: shell" in result.output
    assert "Dry-run mode" in result.output
    assert "devflow task run task-0001 --worker shell" in result.output
    assert executed == []


def test_task_auto_run_project_option_uses_raw_cli_project_for_routing_and_hint(monkeypatch) -> None:
    monkeypatch.setenv("DEVFLOW_EXPERIMENTAL", "1")
    _stub_auto_run_routing(monkeypatch)
    captured = {}

    monkeypatch.setattr(
        "devflow.cli._resolve_task_project_root",
        lambda project: SimpleNamespace(root=Path.cwd(), project_id="normalized-project"),
    )

    def fake_route_task(*_args, **kwargs):
        captured["project_id"] = kwargs.get("project_id")
        return {
            "routing_decision": {
                "selected": {"worker": "shell"},
                "reason": ["worker selected: shell (score=1)"],
                "unresolved": [],
            }
        }

    monkeypatch.setattr("devflow.control_room.router.route_task", fake_route_task)

    result = runner.invoke(app, ["task", "auto-run", "task-0001", "--dry-run", "--project", "typed-project"])

    assert result.exit_code == 0, result.output
    assert captured["project_id"] == "typed-project"
    assert "devflow task run task-0001 --project typed-project --worker shell" in result.output


def test_task_auto_run_experimental_execution_uses_service_facade(monkeypatch) -> None:
    monkeypatch.setenv("DEVFLOW_EXPERIMENTAL", "1")
    _stub_auto_run_routing(monkeypatch)
    calls = []

    monkeypatch.setattr(
        "devflow.control_room.agent_registry.load_agent_registry",
        lambda *_args, **_kwargs: SimpleNamespace(agents={}),
    )

    def fake_run_shell_task(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(
            id="task-0001",
            status="complete",
            log_path=".devflow/tasks/task-0001/logs/worker.log",
            latest_log_line=None,
            last_exit_code=0,
        )

    monkeypatch.setattr("devflow.control_room.task_auto_run_command.task_service.run_shell_task", fake_run_shell_task)

    result = runner.invoke(app, ["task", "auto-run", "task-0001"])

    assert result.exit_code == 0, result.output
    assert "Executing worker: shell" in result.output
    assert "status: complete" in result.output
    assert len(calls) == 1
    assert calls[0][0][1] == "task-0001"
    assert calls[0][0][2] == []
    assert calls[0][1]["worker_adapter"] == "shell"
