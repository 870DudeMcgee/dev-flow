from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import yaml
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.service import create_task


runner = CliRunner()


def _devflow_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home" / ".devflow"
    monkeypatch.setenv("DEVFLOW_HOME", home.as_posix())
    return home


def _git_remote(root: Path) -> str | None:
    proc = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def test_project_create_defaults_to_separate_local_git_without_remote(tmp_path: Path, monkeypatch) -> None:
    home = _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"

    result = runner.invoke(
        app,
        ["project", "create", "Factory Scheduler", "--projects-root", projects_root.as_posix()],
    )

    assert result.exit_code == 0, result.output
    project_root = projects_root / "factory-scheduler"
    assert project_root.is_dir()
    assert (project_root / ".git").is_dir()
    assert _git_remote(project_root) is None
    assert (project_root / ".devflow" / "project" / "project.yaml").is_file()

    metadata = yaml.safe_load((project_root / ".devflow/project/project.yaml").read_text(encoding="utf-8"))
    assert metadata["project_id"] == "factory-scheduler"
    assert metadata["name"] == "Factory Scheduler"
    assert metadata["root_path"] == project_root.as_posix()
    assert metadata["source_control"]["mode"] == "local_git"
    assert metadata["source_control"]["remote_provider"] == "none"
    assert metadata["source_control"]["remote_url"] is None
    assert metadata["remote_publication"]["push_allowed"] is False
    assert metadata["privacy"]["allow_github_upload"] is False

    registry = json.loads((home / "registry" / "projects.json").read_text(encoding="utf-8"))
    assert registry["projects_root"] == projects_root.as_posix()
    assert registry["projects"][0]["project_id"] == "factory-scheduler"
    assert registry["projects"][0]["path"] == project_root.as_posix()

    gitignore = (project_root / ".gitignore").read_text(encoding="utf-8")
    assert ".devflow/tasks/" in gitignore
    assert ".devflow/workspaces/" in gitignore
    assert ".devflow/project/" not in gitignore

    doctor = runner.invoke(app, ["project", "doctor", "factory-scheduler"])
    assert doctor.exit_code == 0, doctor.output
    assert "ok: project metadata" in doctor.output
    assert "ok: no remote" in doctor.output


def test_project_create_source_control_none_and_private_context(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"

    result = runner.invoke(
        app,
        [
            "project",
            "create",
            "Local Experiment",
            "--projects-root",
            projects_root.as_posix(),
            "--source-control",
            "none",
            "--private-context",
        ],
    )

    assert result.exit_code == 0, result.output
    project_root = projects_root / "local-experiment"
    assert not (project_root / ".git").exists()
    metadata = yaml.safe_load((project_root / ".devflow/project/project.yaml").read_text(encoding="utf-8"))
    assert metadata["source_control"]["mode"] == "none"
    assert metadata["source_control"]["local_repo"] is False
    assert metadata["version_control"]["track_devflow_context"] is False
    assert ".devflow/" in (project_root / ".gitignore").read_text(encoding="utf-8")


def test_project_registry_refuses_duplicate_project_id(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    first = runner.invoke(app, ["project", "create", "Client App", "--projects-root", projects_root.as_posix()])
    assert first.exit_code == 0, first.output

    second = runner.invoke(app, ["project", "create", "Client App", "--projects-root", projects_root.as_posix()])

    assert second.exit_code == 1
    assert "Project path already exists" in second.output


def test_project_import_registers_existing_repo_without_github_policy(tmp_path: Path, monkeypatch) -> None:
    home = _devflow_home(tmp_path, monkeypatch)
    existing = tmp_path / "existing"
    existing.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=existing, capture_output=True, text=True, check=True)

    result = runner.invoke(app, ["project", "import", existing.as_posix(), "--name", "Existing Repo"])

    assert result.exit_code == 0, result.output
    metadata = yaml.safe_load((existing / ".devflow/project/project.yaml").read_text(encoding="utf-8"))
    assert metadata["source_control"]["mode"] == "local_git"
    assert metadata["remote_publication"]["push_allowed"] is False
    registry = json.loads((home / "registry" / "projects.json").read_text(encoding="utf-8"))
    assert registry["projects"][0]["project_id"] == "existing"


def test_multi_project_dashboard_reports_registered_and_missing_projects(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    first = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    second = runner.invoke(app, ["project", "create", "Beta App", "--projects-root", projects_root.as_posix()])
    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output

    create_task(projects_root / "alpha-app", "dashboard task")
    shutil.rmtree(projects_root / "beta-app")

    result = runner.invoke(app, ["dashboard", "--all-projects"])

    assert result.exit_code == 0, result.output
    assert "Dev-Flow Multi-Project Control Room" in result.output
    assert "Total projects: 2" in result.output
    assert "Missing projects: 1" in result.output
    assert "alpha-app" in result.output
    assert "beta-app" in result.output
    assert "project path is missing" in result.output


def test_push_main_refuses_project_policy_when_push_disabled(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    created = runner.invoke(app, ["project", "create", "Push Guard", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output

    old_cwd = Path.cwd()
    try:
        os.chdir(projects_root / "push-guard")
        result = runner.invoke(app, ["push-main"])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 1
    assert "project policy disallows remote publication" in result.output
