from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.control_room.loop_command import loop_app


def test_loop_command_init_show_and_list_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    initialized = runner.invoke(loop_app, ["init", "daily", "--template", "goal-autopilot"])

    assert initialized.exit_code == 0, initialized.output
    config_path = tmp_path / ".devflow" / "loops" / "daily" / "loop.yaml"
    assert config_path.exists()

    shown = runner.invoke(loop_app, ["show", "daily", "--json"])

    assert shown.exit_code == 0, shown.output
    definition = json.loads(shown.output)
    assert definition["loop_id"] == "daily"
    assert definition["template"] == "goal-autopilot"

    listed = runner.invoke(loop_app, ["list", "--json"])

    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["loops"] == ["daily"]
