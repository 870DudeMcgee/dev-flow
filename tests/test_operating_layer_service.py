from __future__ import annotations

import plistlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.operating_layer_service import install_operating_layer_launch_agent


runner = CliRunner()


def test_operating_layer_install_service_writes_project_launch_agent(tmp_path: Path) -> None:
    launch_agents_dir = tmp_path / "LaunchAgents"
    logs_dir = tmp_path / "logs"

    result = install_operating_layer_launch_agent(
        tmp_path,
        host="127.0.0.1",
        port=8765,
        launch_agents_dir=launch_agents_dir,
        logs_dir=logs_dir,
        python_executable=Path("/usr/bin/python3"),
        load=False,
    )

    payload = plistlib.loads(result.plist_path.read_bytes())
    assert result.url == "http://127.0.0.1:8765"
    assert result.loaded is False
    assert result.plist_path == launch_agents_dir / "com.devflow.operating-layer.plist"
    assert payload["Label"] == "com.devflow.operating-layer"
    assert payload["RunAtLoad"] is True
    assert payload["WorkingDirectory"] == str(tmp_path.resolve())
    assert payload["ProgramArguments"] == [
        "/usr/bin/python3",
        "-m",
        "devflow.cli",
        "operating-layer",
        "serve",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ]
    assert payload["EnvironmentVariables"]["PYTHONUNBUFFERED"] == "1"
    assert payload["EnvironmentVariables"]["PYTHONPATH"] == f"{tmp_path.resolve() / 'src'}:{tmp_path.resolve()}"
    assert payload["StandardOutPath"] == str(logs_dir / "operating-layer.out.log")
    assert payload["StandardErrorPath"] == str(logs_dir / "operating-layer.err.log")


def test_operating_layer_install_service_rejects_network_host_without_opt_in(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-loopback"):
        install_operating_layer_launch_agent(
            tmp_path,
            host="0.0.0.0",
            port=8765,
            launch_agents_dir=tmp_path / "LaunchAgents",
            logs_dir=tmp_path / "logs",
            python_executable=Path("/usr/bin/python3"),
            load=False,
        )


def test_operating_layer_install_service_can_load_launch_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    calls: list[list[str]] = []

    def fake_run(args: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    result = install_operating_layer_launch_agent(
        tmp_path,
        launch_agents_dir=tmp_path / "LaunchAgents",
        logs_dir=tmp_path / "logs",
        python_executable=Path("/usr/bin/python3"),
        load=True,
        run_command=fake_run,
    )

    assert result.loaded is True
    assert calls[0][0:2] == ["launchctl", "bootout"]
    assert calls[1] == ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(result.plist_path)]
    assert calls[2][0:2] == ["launchctl", "enable"]


def test_operating_layer_install_service_cli_writes_launch_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    launch_agents_dir = tmp_path / "LaunchAgents"
    logs_dir = tmp_path / "logs"

    cli = runner.invoke(
        app,
        [
            "operating-layer",
            "install-service",
            "--launch-agents-dir",
            str(launch_agents_dir),
            "--logs-dir",
            str(logs_dir),
            "--python",
            "/usr/bin/python3",
        ],
    )

    assert cli.exit_code == 0, cli.output
    assert "Installed LaunchAgent:" in cli.output
    assert "http://127.0.0.1:8765" in cli.output
    assert "Loaded now: no" in cli.output
    assert (launch_agents_dir / "com.devflow.operating-layer.plist").exists()
