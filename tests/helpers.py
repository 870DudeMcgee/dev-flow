from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )


def init_test_git_repo(path: Path) -> None:
    """Initialise a git repo with a baseline commit.
    """
    readme_path = path / "README.md"
    if not readme_path.exists():
        readme_path.write_text("# Test Repo\n", encoding="utf-8")

    _run_git(path, "init", "-b", "main")
    _run_git(path, "config", "user.email", "devflow-test@example.com")
    _run_git(path, "config", "user.name", "DevFlow Test")
    _run_git(path, "add", "README.md")
    _run_git(path, "commit", "-m", "test baseline")
    _run_git(path, "rev-parse", "--verify", "HEAD")


def git_init(path: Path) -> None:
    """Initialise a git repo with test identity but no commit.

    For tests that need to create files before the first commit.
    """
    _run_git(path, "init", "-b", "main")
    _run_git(path, "config", "user.email", "devflow-test@example.com")
    _run_git(path, "config", "user.name", "DevFlow Test")


def git_commit(path: Path, message: str = "init", add_all: bool = True) -> None:
    """Stage and commit in one subprocess call.
    """
    if add_all:
        _run_git(path, "add", ".")
    _run_git(path, "commit", "-m", message)


def setup_temp_git_repo(tmp_path: Path) -> Path:
    """Scaffold a .devflow control room + git repo in *tmp_path*.

    Calls :func:`setup_temp_repo` (direct Python, no CliRunner) then
    :func:`init_test_git_repo` (batched git).
    """
    setup_temp_repo(tmp_path)
    init_test_git_repo(tmp_path)
    return tmp_path


def setup_temp_repo(tmp_path: Path) -> Path:
    """Initialize standard .devflow control room scaffolding in temp path.

    Direct-call replacement for ``CliRunner().invoke(app, ["init"])`` —
    produces the same .devflow/ directory + seed files without booting
    the full Typer CLI app (~21ms → ~5ms per invocation).
    """
    from devflow.control_room.task_creation import initialize_control_room

    initialize_control_room(tmp_path)

    # Create docs/ for context pointer scanning (matching the old CliRunner path)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(exist_ok=True)
    (docs_dir / "architecture.md").write_text("Standard architecture notes.", encoding="utf-8")

    return tmp_path
