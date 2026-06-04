from __future__ import annotations

import subprocess
from pathlib import Path


def init_test_git_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "devflow-test@example.com"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "DevFlow Test"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    readme_path = path / "README.md"
    if not readme_path.exists():
        readme_path.write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "test baseline"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )


def setup_temp_git_repo(tmp_path: Path) -> Path:
    from tests.test_goal_projection import setup_temp_repo

    setup_temp_repo(tmp_path)
    init_test_git_repo(tmp_path)
    return tmp_path
