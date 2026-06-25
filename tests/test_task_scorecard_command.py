from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from devflow.control_room.task_scorecard_command import (
    TaskScorecardCommandError,
    build_task_scorecard_result,
    render_task_scorecard_json,
    render_task_scorecard_lines,
)


def test_build_task_scorecard_result_saves_updates_profile_and_renders_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scorecard_data: dict[str, Any] = {
        "scorecard": {
            "task_id": "task-0042",
            "decision_mode": "evidence_only",
            "verification_passed": True,
            "promotion_ready": False,
            "selected_roles": ["planner", "worker"],
            "unresolved_roles": [],
            "state_mutation": "none",
            "overall_quality_rating": 0.85,
            "first_run_pass": True,
            "boundary_violations": False,
            "frontier_escalation_needed": False,
            "frontier_escalation_avoided": True,
            "context_limit_exceeded": False,
            "review_mistakes_found": "unknown",
            "latency_seconds": 17,
            "cost_avoided_usd": 1.2,
        },
        "routing_decision": {
            "selected": {
                "worker": "qwopus-implementer",
            }
        },
        "repo_scan": {
            "total_context_estimate": 12345,
        },
    }
    saved_path = tmp_path / ".devflow/tasks/task-0042/routing-quality-scorecard.yaml"
    calls: dict[str, Any] = {}

    def fake_generate_scorecard(root: Path, task_id: str) -> dict[str, Any]:
        calls["generate"] = (root, task_id)
        return scorecard_data

    def fake_save_scorecard(root: Path, task_id: str, data: dict[str, Any]) -> Path:
        calls["save"] = (root, task_id, data)
        return saved_path

    def fake_update_from_scorecard(**kwargs: Any) -> None:
        calls["profile"] = kwargs

    monkeypatch.setattr("devflow.control_room.task_scorecard_command.generate_scorecard", fake_generate_scorecard)
    monkeypatch.setattr("devflow.control_room.task_scorecard_command.save_scorecard", fake_save_scorecard)
    monkeypatch.setattr(
        "devflow.control_room.model_runtime_profiles.update_from_scorecard",
        fake_update_from_scorecard,
    )

    result = build_task_scorecard_result(tmp_path, "task-0042", project_id="alpha-app")

    assert calls["generate"] == (tmp_path, "task-0042")
    assert calls["save"] == (tmp_path, "task-0042", scorecard_data)
    assert calls["profile"] == {
        "root": tmp_path,
        "scorecard": scorecard_data,
        "model_id": "qwopus-implementer",
        "context_estimate": 12345,
        "latency_seconds": 17,
    }
    assert result.artifact_path == ".devflow/tasks/task-0042/routing-quality-scorecard.yaml"

    expected_payload = {
        "artifact_path": ".devflow/tasks/task-0042/routing-quality-scorecard.yaml",
        "scorecard": scorecard_data["scorecard"],
        "task_id": "task-0042",
    }
    assert render_task_scorecard_json(result) == json.dumps(expected_payload, indent=2, sort_keys=True)

    assert render_task_scorecard_lines(result) == (
        "Compiled routing-quality scorecard for task: alpha-app:task-0042",
        "--------------------------------------------------",
        "Decision Mode:              evidence_only",
        "Verification Passed:        yes",
        "Promotion Ready:            no",
        "Selected Roles:             planner, worker",
        "Unresolved Roles:           none",
        "State Mutation:             none",
        "Overall Quality Rating:     85.0%",
        "First-Run Verification Pass: yes",
        "Boundary Violations:        no",
        "Frontier Escalation Needed: no",
        "Frontier Escalation Avoided: yes",
        "Context Ceiling Exceeded:   no",
        "Review Mistakes Found:      unknown",
        "Latency:                    17 seconds",
        "Cost Avoided:               $1.20 USD",
        "--------------------------------------------------",
        "Wrote routing-quality-scorecard.yaml under .devflow/tasks/task-0042/",
    )


def test_render_task_scorecard_lines_preserves_optional_and_unknown_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scorecard_data = {
        "scorecard": {
            "task_id": "task-0001",
            "decision_mode": "evidence_only",
            "verification_passed": "unknown",
            "promotion_ready": "unknown",
            "selected_roles": [],
            "unresolved_roles": ["worker"],
            "state_mutation": "none",
            "overall_quality_rating": "unknown",
            "first_run_pass": "unknown",
            "boundary_violations": "unknown",
            "frontier_escalation_needed": False,
            "context_limit_exceeded": None,
            "review_mistakes_found": False,
            "latency_seconds": "unknown",
            "cost_avoided_usd": None,
        }
    }
    monkeypatch.setattr(
        "devflow.control_room.task_scorecard_command.generate_scorecard",
        lambda *_args, **_kwargs: scorecard_data,
    )
    monkeypatch.setattr(
        "devflow.control_room.task_scorecard_command.save_scorecard",
        lambda root, task_id, _data: root / ".devflow/tasks" / task_id / "routing-quality-scorecard.yaml",
    )

    result = build_task_scorecard_result(tmp_path, "task-0001")
    lines = render_task_scorecard_lines(result)

    assert "Frontier Escalation Avoided: unknown" not in lines
    assert lines == (
        "Compiled routing-quality scorecard for task: task-0001",
        "--------------------------------------------------",
        "Decision Mode:              evidence_only",
        "Verification Passed:        unknown",
        "Promotion Ready:            unknown",
        "Selected Roles:             none",
        "Unresolved Roles:           worker",
        "State Mutation:             none",
        "Overall Quality Rating:     unknown",
        "First-Run Verification Pass: unknown",
        "Boundary Violations:        unknown",
        "Frontier Escalation Needed: no",
        "Context Ceiling Exceeded:   unknown",
        "Review Mistakes Found:      no",
        "Latency:                    unknown seconds",
        "Cost Avoided:               unknown",
        "--------------------------------------------------",
        "Wrote routing-quality-scorecard.yaml under .devflow/tasks/task-0001/",
    )


def test_build_task_scorecard_result_ignores_runtime_profile_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scorecard_data = {
        "scorecard": {"task_id": "task-0001", "latency_seconds": 5},
        "routing_decision": {"selected": {"worker": "qwopus-implementer"}},
    }
    monkeypatch.setattr(
        "devflow.control_room.task_scorecard_command.generate_scorecard",
        lambda *_args, **_kwargs: scorecard_data,
    )
    monkeypatch.setattr(
        "devflow.control_room.task_scorecard_command.save_scorecard",
        lambda root, task_id, _data: root / ".devflow/tasks" / task_id / "routing-quality-scorecard.yaml",
    )

    def fail_update_from_scorecard(**_kwargs: Any) -> None:
        raise RuntimeError("profile store unavailable")

    monkeypatch.setattr(
        "devflow.control_room.model_runtime_profiles.update_from_scorecard",
        fail_update_from_scorecard,
    )

    result = build_task_scorecard_result(tmp_path, "task-0001")

    assert result.scorecard == scorecard_data["scorecard"]


def test_build_task_scorecard_result_maps_scorecard_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_generate_scorecard(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("missing task")

    monkeypatch.setattr("devflow.control_room.task_scorecard_command.generate_scorecard", fail_generate_scorecard)

    with pytest.raises(TaskScorecardCommandError, match="missing task"):
        build_task_scorecard_result(tmp_path, "task-missing")
