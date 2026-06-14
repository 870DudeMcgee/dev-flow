from __future__ import annotations

import os
import re
import subprocess
import sys


ANSI_RE = re.compile(r"\x1B\[[0-9;?]*[ -/]*[@-~]")


def _has_command(help_text: str, command: str) -> bool:
    clean_help = ANSI_RE.sub("", help_text)
    return re.search(rf"(^|[^A-Za-z0-9_-]){re.escape(command)}([^A-Za-z0-9_-]|$)", clean_help) is not None


def test_subprocess_standard_help_hides_experimental_commands() -> None:
    # Build env without DEVFLOW_EXPERIMENTAL
    env = {k: v for k, v in os.environ.items() if k != "DEVFLOW_EXPERIMENTAL"}

    # 1. Main app help
    res_main = subprocess.run(
        [sys.executable, "-m", "devflow.cli", "--help"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_main.returncode == 0
    assert "supervise" not in res_main.stdout
    assert "context" not in res_main.stdout
    assert "[EXPERIMENTAL-" not in res_main.stdout

    # 2. Task app help
    res_task = subprocess.run(
        [sys.executable, "-m", "devflow.cli", "task", "--help"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_task.returncode == 0
    for cmd in ["fit", "scout", "route", "scorecard"]:
        assert _has_command(res_task.stdout, cmd)
    assert not _has_command(res_task.stdout, "pack")
    assert "[EXPERIMENTAL-" not in res_task.stdout


def test_subprocess_experimental_env_exposes_commands() -> None:
    # Build env with DEVFLOW_EXPERIMENTAL=1
    env = {**os.environ, "DEVFLOW_EXPERIMENTAL": "1"}

    # 1. Main app help
    res_main = subprocess.run(
        [sys.executable, "-m", "devflow.cli", "--help"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_main.returncode == 0
    assert "supervise" in res_main.stdout
    assert "context" in res_main.stdout
    assert "[EXPERIMENTAL-MANUAL]" in res_main.stdout
    assert "[EXPERIMENTAL-READONLY]" in res_main.stdout

    # 2. Task app help
    res_task = subprocess.run(
        [sys.executable, "-m", "devflow.cli", "task", "--help"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_task.returncode == 0
    for cmd in ["fit", "scout", "route", "scorecard"]:
        assert _has_command(res_task.stdout, cmd)
    assert _has_command(res_task.stdout, "pack")
    assert "[EXPERIMENTAL-READONLY]" in res_task.stdout


def test_subprocess_experimental_execution_refused_without_env() -> None:
    # Build env without DEVFLOW_EXPERIMENTAL
    env = {k: v for k, v in os.environ.items() if k != "DEVFLOW_EXPERIMENTAL"}

    res = subprocess.run(
        [sys.executable, "-m", "devflow.cli", "context"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1
    assert "Error: Command 'context' is experimental and restricted to transition planning aids." in res.stderr
    assert "To run this command, please set the environment variable DEVFLOW_EXPERIMENTAL=1." in res.stderr
