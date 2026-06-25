from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from devflow.control_room.task_routing_command import (
    TaskRoutingCommandError,
    build_task_routing_result,
    render_task_routing_json,
    render_task_routing_lines,
)


def test_build_task_routing_result_saves_and_renders_all_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planner_next = (
        "devflow agent context-pack task-0042 <agent-id> "
        "--project alpha-app --role planner --json"
    )
    decision_data: dict[str, Any] = {
        "routing_decision": {
            "task_id": "task-0042",
            "policy_version": 2,
            "selected": {
                "worker": "qwopus-implementer",
                "reviewer": "qwen-review",
                "verifier": "deterministic-shell",
            },
            "reason": [
                "evidence-only routing records recommendations",
                "worker selected: qwopus-implementer (score=125)",
            ],
            "rejected": [
                {
                    "role": "worker",
                    "agent": "remote-worker",
                    "reason": "remote provider execution is blocked",
                },
            ],
            "blocked": [
                {
                    "role": "worker",
                    "agent": "remote-worker",
                    "status": "blocked_runtime",
                    "reason": "remote provider execution is blocked",
                },
            ],
            "unresolved": [
                {
                    "role": "planner",
                    "status": "not_selected_evidence_only",
                    "reason": "build role-scoped context evidence",
                    "next_command": planner_next,
                },
            ],
            "recommended_next_commands": {
                "worker": "devflow task run task-0042 --project alpha-app --worker qwopus-implementer",
                "verifier": 'devflow task verify task-0042 --project alpha-app --shell "pytest"',
                "planner": planner_next,
            },
        }
    }
    calls: dict[str, Any] = {}

    def fake_route_task(root: Path, task_id: str, *, project_id: str | None = None) -> dict[str, Any]:
        calls["route"] = (root, task_id, project_id)
        return decision_data

    def fake_save_routing_decision(root: Path, task_id: str, data: dict[str, Any]) -> None:
        calls["save"] = (root, task_id, data)

    monkeypatch.setattr("devflow.control_room.task_routing_command.route_task", fake_route_task)
    monkeypatch.setattr(
        "devflow.control_room.task_routing_command.save_routing_decision",
        fake_save_routing_decision,
    )

    result = build_task_routing_result(tmp_path, "task-0042", project_id="alpha-app")

    assert calls["route"] == (tmp_path, "task-0042", "alpha-app")
    assert calls["save"] == (tmp_path, "task-0042", decision_data)
    assert result.artifact_path == ".devflow/tasks/task-0042/routing-decision.yaml"

    expected_payload = {
        "artifact_path": ".devflow/tasks/task-0042/routing-decision.yaml",
        "routing_decision": decision_data["routing_decision"],
        "task_id": "task-0042",
    }
    assert render_task_routing_json(result) == json.dumps(expected_payload, indent=2, sort_keys=True)

    assert render_task_routing_lines(result) == (
        "Executed routing mapping for task: alpha-app:task-0042",
        "--------------------------------------------------",
        "Policy Version:              2",
        "",
        "Selected Agent Assignments:",
        "  reviewer    : qwen-review",
        "  verifier    : deterministic-shell",
        "  worker      : qwopus-implementer",
        "",
        "Recorded Reasons:",
        "  - evidence-only routing records recommendations",
        "  - worker selected: qwopus-implementer (score=125)",
        "",
        "Rejected Agents:",
        "  - agent:  remote-worker",
        "    reason: remote provider execution is blocked",
        "",
        "Blocked Candidates:",
        "  - role:   worker",
        "    agent:  remote-worker",
        "    status: blocked_runtime",
        "    reason: remote provider execution is blocked",
        "",
        "Unresolved Decisions:",
        "  - role:   planner",
        "    status: not_selected_evidence_only",
        "    reason: build role-scoped context evidence",
        f"    next:   {planner_next}",
        "",
        "Recommended Next Commands:",
        f"  planner     : {planner_next}",
        '  verifier    : devflow task verify task-0042 --project alpha-app --shell "pytest"',
        "  worker      : devflow task run task-0042 --project alpha-app --worker qwopus-implementer",
        "--------------------------------------------------",
        "Wrote routing-decision.yaml under .devflow/tasks/task-0042/",
    )


def test_render_task_routing_lines_preserves_empty_section_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision_data = {
        "routing_decision": {
            "task_id": "task-0001",
            "policy_version": 2,
            "selected": {},
            "reason": [],
            "rejected": [],
            "blocked": [],
            "unresolved": [],
            "recommended_next_commands": {},
        }
    }
    monkeypatch.setattr(
        "devflow.control_room.task_routing_command.route_task",
        lambda *_args, **_kwargs: decision_data,
    )
    monkeypatch.setattr(
        "devflow.control_room.task_routing_command.save_routing_decision",
        lambda *_args, **_kwargs: None,
    )

    result = build_task_routing_result(tmp_path, "task-0001")
    lines = render_task_routing_lines(result)

    assert lines == (
        "Executed routing mapping for task: task-0001",
        "--------------------------------------------------",
        "Policy Version:              2",
        "",
        "Selected Agent Assignments:",
        "  - none",
        "",
        "Recorded Reasons:",
        "",
        "Rejected Agents:",
        "  - none",
        "",
        "Blocked Candidates:",
        "  - none",
        "",
        "Unresolved Decisions:",
        "  - none",
        "",
        "Recommended Next Commands:",
        "  - none",
        "--------------------------------------------------",
        "Wrote routing-decision.yaml under .devflow/tasks/task-0001/",
    )


def test_build_task_routing_result_maps_router_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_route_task(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("missing task")

    monkeypatch.setattr("devflow.control_room.task_routing_command.route_task", fail_route_task)

    with pytest.raises(TaskRoutingCommandError, match="missing task"):
        build_task_routing_result(tmp_path, "task-missing")
