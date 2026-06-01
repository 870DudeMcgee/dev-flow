from __future__ import annotations

import os
import subprocess
import sys


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
    for cmd in ["fit", "pack", "scout", "route", "scorecard"]:
        assert cmd in res_task.stdout
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
