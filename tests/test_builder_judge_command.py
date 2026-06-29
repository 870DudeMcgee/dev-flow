from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from devflow.control_room.builder_judge_command import builder_judge_app


def _write_run(root: Path, loop_id: str, payload: dict[str, Any]) -> None:
    run_dir = root / ".devflow" / "builder-judge-loops" / loop_id
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps(payload), encoding="utf-8")


def test_builder_judge_list_json_returns_loop_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_run(
        tmp_path,
        "bj-old",
        {
            "loop_id": "bj-old",
            "run_id": "run-old",
            "status": "passed",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:01:00Z",
            "final_score": 91,
            "rounds": [{"round_number": 1}],
            "config": {
                "definition_of_done": "Old bar",
                "builder_profile_id": "builder-a",
                "judge_profile_id": "judge-a",
            },
        },
    )
    _write_run(
        tmp_path,
        "bj-new",
        {
            "loop_id": "bj-new",
            "run_id": "run-new",
            "status": "max_rounds",
            "started_at": "2026-01-02T00:00:00Z",
            "finished_at": "2026-01-02T00:03:00Z",
            "final_score": 72,
            "rounds": [{"round_number": 1}, {"round_number": 2}],
            "config": {
                "definition_of_done": "New bar",
                "builder_profile_id": "builder-b",
                "judge_profile_id": "judge-b",
            },
        },
    )
    runner = CliRunner()

    result = runner.invoke(builder_judge_app, ["list", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "loops": [
            {
                "loop_id": "bj-new",
                "run_id": "run-new",
                "status": "max_rounds",
                "started_at": "2026-01-02T00:00:00Z",
                "finished_at": "2026-01-02T00:03:00Z",
                "final_score": 72,
                "rounds_completed": 2,
                "definition_of_done": "New bar",
                "builder_profile_id": "builder-b",
                "judge_profile_id": "judge-b",
            },
            {
                "loop_id": "bj-old",
                "run_id": "run-old",
                "status": "passed",
                "started_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:01:00Z",
                "final_score": 91,
                "rounds_completed": 1,
                "definition_of_done": "Old bar",
                "builder_profile_id": "builder-a",
                "judge_profile_id": "judge-a",
            },
        ],
    }


def test_builder_judge_show_json_returns_stored_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = {
        "loop_id": "bj-show",
        "run_id": "run-show",
        "status": "passed",
        "started_at": "2026-01-03T00:00:00Z",
        "finished_at": "2026-01-03T00:01:00Z",
        "final_score": 95,
        "rounds": [{"round_number": 1, "score": 95, "passed": True}],
        "config": {
            "definition_of_done": "Stored payload",
            "builder_profile_id": "builder-c",
            "judge_profile_id": "judge-c",
        },
    }
    _write_run(tmp_path, "bj-show", payload)
    runner = CliRunner()

    result = runner.invoke(builder_judge_app, ["show", "bj-show", "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == payload


def test_builder_judge_show_missing_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(builder_judge_app, ["show", "missing", "--json"])

    assert result.exit_code == 1
    assert "Error: Loop not found: missing" in result.output


def test_builder_judge_run_json_outputs_passed_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    captured: dict[str, Any] = {}

    class FakeRun:
        status = "passed"

        def model_dump(self, *, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return {"loop_id": "bj-run", "status": self.status}

    def fake_run_builder_judge_loop(root: Path, config: Any) -> FakeRun:
        captured["root"] = root
        captured["config"] = config
        return FakeRun()

    monkeypatch.setattr(
        "devflow.control_room.builder_judge_loop.run_builder_judge_loop",
        fake_run_builder_judge_loop,
    )
    runner = CliRunner()

    result = runner.invoke(builder_judge_app, ["run", "--dod", "Do the thing", "--json"])

    assert result.exit_code == 0, result.output
    assert captured["root"] == tmp_path
    config = captured["config"]
    assert config.definition_of_done == "Do the thing"
    assert config.starting_point is None
    assert config.builder_profile_id == "hermes-qwen37plus"
    assert config.judge_profile_id == "hermes-opus48"
    assert config.pass_threshold == 85
    assert config.max_rounds == 5
    assert config.escalate_on_max_rounds is True
    assert json.loads(result.output) == {"loop_id": "bj-run", "status": "passed"}


def test_builder_judge_run_json_exits_2_for_non_passing_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    class FakeRun:
        status = "max_rounds"

        def model_dump(self, *, mode: str) -> dict[str, Any]:
            assert mode == "json"
            return {"loop_id": "bj-run", "status": self.status}

    monkeypatch.setattr(
        "devflow.control_room.builder_judge_loop.run_builder_judge_loop",
        lambda root, config: FakeRun(),
    )
    runner = CliRunner()

    result = runner.invoke(builder_judge_app, ["run", "--dod", "Do the thing", "--json"])

    assert result.exit_code == 2
    assert json.loads(result.output) == {"loop_id": "bj-run", "status": "max_rounds"}
