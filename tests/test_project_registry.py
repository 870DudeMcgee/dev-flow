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


def _modify_patch(path: str, old: str = "old", new: str = "new") -> str:
    return f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-{old}
+{new}
"""


def _commit_all(root: Path, message: str) -> str:
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=root, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


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
    assert ".devflow/freshness/" in gitignore
    assert ".devflow/project/" not in gitignore

    doctor = runner.invoke(app, ["project", "doctor", "factory-scheduler"])
    assert doctor.exit_code == 0, doctor.output
    assert "ok: project metadata" in doctor.output
    assert "ok: no remote" in doctor.output


def test_project_task_create_requires_initial_git_baseline(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"

    created = runner.invoke(app, ["project", "create", "Baseline Required", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    project_root = projects_root / "baseline-required"

    no_baseline = runner.invoke(app, ["task", "create", "--project", "baseline-required", "first task"])
    assert no_baseline.exit_code == 1, no_baseline.output
    assert "Project local Git baseline is missing" in no_baseline.output
    assert "devflow git checkpoint --message \"chore: initialize project baseline\" --yes" in no_baseline.output
    assert not (project_root / ".devflow" / "tasks" / "task-0001").exists()

    baseline = _commit_all(project_root, "project baseline")
    with_baseline = runner.invoke(app, ["task", "create", "--project", "baseline-required", "first task"])
    assert with_baseline.exit_code == 0, with_baseline.output

    task = yaml.safe_load((project_root / ".devflow/tasks/task-0001/task.yaml").read_text(encoding="utf-8"))
    assert task["workspace_commit"] == baseline
    assert task["workspace_dirty"] is False


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

    alpha_root = projects_root / "alpha-app"
    _commit_all(alpha_root, "project baseline")
    create_task(alpha_root, "dashboard task")
    shutil.rmtree(projects_root / "beta-app")

    result = runner.invoke(app, ["dashboard", "--all-projects"])

    assert result.exit_code == 0, result.output
    assert "Dev-Flow Multi-Project Control Room" in result.output
    assert "Total projects: 2" in result.output
    assert "Missing projects: 1" in result.output
    assert "alpha-app" in result.output
    assert "beta-app" in result.output
    assert "project path is missing" in result.output


def test_project_archive_hides_default_list_but_keeps_audit_visibility(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"

    created = runner.invoke(app, ["project", "create", "Beta App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output

    archived = runner.invoke(app, ["project", "archive", "beta-app"])
    default_list = runner.invoke(app, ["project", "list"])
    audit_list = runner.invoke(app, ["project", "list", "--include-archived"])
    task_list = runner.invoke(app, ["task", "list", "--project", "beta-app"])

    assert archived.exit_code == 0, archived.output
    assert "Archived project beta-app" in archived.output
    assert default_list.exit_code == 0, default_list.output
    assert "beta-app" not in default_list.output
    assert audit_list.exit_code == 0, audit_list.output
    assert "beta-app" in audit_list.output
    assert "archived" in audit_list.output
    assert task_list.exit_code == 1
    assert "Project is archived: beta-app" in task_list.output


def test_project_remove_registry_only_preserves_project_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    project_root = projects_root / "alpha-app"

    refused = runner.invoke(app, ["project", "remove", "alpha-app"])
    removed = runner.invoke(app, ["project", "remove", "alpha-app", "--registry-only"])
    shown = runner.invoke(app, ["project", "show", "alpha-app"])

    assert refused.exit_code == 1
    assert "project remove requires --registry-only" in refused.output
    assert project_root.is_dir()
    assert removed.exit_code == 0, removed.output
    assert "Removed project alpha-app from registry" in removed.output
    assert project_root.is_dir()
    assert shown.exit_code == 1
    assert "Project not found: alpha-app" in shown.output

    registry = json.loads((home / "registry" / "projects.json").read_text(encoding="utf-8"))
    assert registry["projects"] == []
    events = (home / "events.jsonl").read_text(encoding="utf-8")
    assert '"event": "project_removed"' in events
    assert '"project_id": "alpha-app"' in events


def test_task_create_project_writes_under_registered_project_root(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"
    control_root.mkdir()

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    _commit_all(projects_root / "alpha-app", "project baseline")

    old_cwd = Path.cwd()
    try:
        os.chdir(control_root)
        result = runner.invoke(app, ["task", "create", "project scoped task", "--project", "alpha-app"])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 0, result.output
    assert "Created alpha-app:task-0001: project scoped task" in result.output
    assert (projects_root / "alpha-app" / ".devflow" / "tasks" / "task-0001" / "task.yaml").is_file()
    assert (projects_root / "alpha-app" / ".devflow" / "workspaces" / "task-0001").is_dir()
    assert not (control_root / ".devflow" / "tasks" / "task-0001").exists()


def test_task_list_and_show_project_read_registered_project_root(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"
    control_root.mkdir()

    alpha = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    beta = runner.invoke(app, ["project", "create", "Beta App", "--projects-root", projects_root.as_posix()])
    assert alpha.exit_code == 0, alpha.output
    assert beta.exit_code == 0, beta.output
    _commit_all(projects_root / "alpha-app", "alpha baseline")
    _commit_all(projects_root / "beta-app", "beta baseline")
    create_task(projects_root / "alpha-app", "alpha task")
    create_task(projects_root / "beta-app", "beta task")

    old_cwd = Path.cwd()
    try:
        os.chdir(control_root)
        listing = runner.invoke(app, ["task", "list", "--project", "alpha-app"])
        shown = runner.invoke(app, ["task", "show", "task-0001", "--project", "alpha-app"])
    finally:
        os.chdir(old_cwd)

    assert listing.exit_code == 0, listing.output
    assert "alpha-app:task-0001" in listing.output
    assert "alpha task" in listing.output
    assert "beta task" not in listing.output
    assert shown.exit_code == 0, shown.output
    assert "task: alpha-app:task-0001" in shown.output
    assert "title: alpha task" in shown.output


def test_task_commands_from_nested_project_directory_use_project_local_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    project_root = projects_root / "alpha-app"
    _commit_all(project_root, "project baseline")
    nested = project_root / "src" / "feature" / "deep"
    nested.mkdir(parents=True)
    create_task(project_root, "root task")

    old_cwd = Path.cwd()
    try:
        os.chdir(nested)
        listing = runner.invoke(app, ["task", "list"])
        shown = runner.invoke(app, ["task", "show", "task-0001"])
        new_task = runner.invoke(app, ["task", "create", "nested task"])
    finally:
        os.chdir(old_cwd)

    assert listing.exit_code == 0, listing.output
    assert "alpha-app:task-0001" in listing.output
    assert "root task" in listing.output
    assert shown.exit_code == 0, shown.output
    assert "task: alpha-app:task-0001" in shown.output
    assert new_task.exit_code == 0, new_task.output
    assert "Created alpha-app:task-0002: nested task" in new_task.output
    assert (project_root / ".devflow" / "tasks" / "task-0002" / "task.yaml").is_file()
    assert not (nested / ".devflow").exists()


def test_project_local_task_state_survives_missing_registry_entry(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    project_root = projects_root / "alpha-app"
    _commit_all(project_root, "project baseline")
    nested = project_root / "docs" / "notes"
    nested.mkdir(parents=True)
    create_task(project_root, "local authoritative task")

    removed = runner.invoke(app, ["project", "remove", "alpha-app", "--registry-only"])
    assert removed.exit_code == 0, removed.output

    old_cwd = Path.cwd()
    try:
        os.chdir(nested)
        listing = runner.invoke(app, ["task", "list"])
        shown = runner.invoke(app, ["task", "show", "task-0001"])
    finally:
        os.chdir(old_cwd)

    assert listing.exit_code == 0, listing.output
    assert "alpha-app:task-0001" in listing.output
    assert "local authoritative task" in listing.output
    assert shown.exit_code == 0, shown.output
    assert "task: alpha-app:task-0001" in shown.output
    assert "title: local authoritative task" in shown.output


def test_task_run_and_verify_project_use_registered_project_root(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"
    control_root.mkdir()

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    _commit_all(projects_root / "alpha-app", "project baseline")
    create_task(projects_root / "alpha-app", "alpha task")

    old_cwd = Path.cwd()
    try:
        os.chdir(control_root)
        run = runner.invoke(
            app,
            [
                "task",
                "run",
                "task-0001",
                "--project",
                "alpha-app",
                "--shell",
                "printf alpha > worker.txt && echo alpha-run",
            ],
        )
        verify = runner.invoke(
            app,
            [
                "task",
                "verify",
                "task-0001",
                "--project",
                "alpha-app",
                "--shell",
                "test -f worker.txt && echo alpha-verify",
            ],
        )
    finally:
        os.chdir(old_cwd)

    assert run.exit_code == 0, run.output
    assert "alpha-app:task-0001: complete" in run.output
    assert verify.exit_code == 0, verify.output
    assert "alpha-app:task-0001: verification passed" in verify.output
    assert (projects_root / "alpha-app" / ".devflow" / "workspaces" / "task-0001" / "worker.txt").read_text(
        encoding="utf-8"
    ) == "alpha"
    assert "alpha-run" in (
        projects_root / "alpha-app" / ".devflow" / "tasks" / "task-0001" / "logs" / "worker.log"
    ).read_text(encoding="utf-8")
    assert "alpha-verify" in (
        projects_root / "alpha-app" / ".devflow" / "tasks" / "task-0001" / "logs" / "verify.log"
    ).read_text(encoding="utf-8")
    assert not (control_root / ".devflow" / "tasks" / "task-0001").exists()


def test_task_log_project_reads_registered_project_root_not_cwd(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    _commit_all(projects_root / "alpha-app", "project baseline")
    create_task(projects_root / "alpha-app", "alpha task")
    create_task(control_root, "cwd task")
    (projects_root / "alpha-app" / ".devflow" / "tasks" / "task-0001" / "logs" / "worker.log").write_text(
        "alpha log\n", encoding="utf-8"
    )
    (control_root / ".devflow" / "tasks" / "task-0001" / "logs" / "worker.log").write_text(
        "cwd log\n", encoding="utf-8"
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(control_root)
        result = runner.invoke(app, ["task", "log", "task-0001", "--project", "alpha-app", "--tail", "1"])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 0, result.output
    assert result.output == "alpha log\n"


def test_task_packet_project_reads_registered_project_root_not_cwd(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    _commit_all(projects_root / "alpha-app", "project baseline")
    create_task(projects_root / "alpha-app", "alpha packet task")
    create_task(control_root, "cwd packet task")

    old_cwd = Path.cwd()
    try:
        os.chdir(control_root)
        result = runner.invoke(app, ["task", "packet", "task-0001", "--project", "alpha-app"])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["task"]["title"] == "alpha packet task"
    assert "cwd packet task" not in result.output


def test_task_review_and_next_action_project_read_registered_project_root(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    _commit_all(projects_root / "alpha-app", "project baseline")
    create_task(projects_root / "alpha-app", "alpha review task")
    create_task(control_root, "cwd review task")
    agent_dir = projects_root / "alpha-app" / ".devflow" / "tasks" / "task-0001" / "agents" / "qwopus-implementer"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "proposal.patch").write_text("diff --git a/a.txt b/a.txt\n", encoding="utf-8")

    old_cwd = Path.cwd()
    try:
        os.chdir(control_root)
        next_action = runner.invoke(app, ["task", "next-action", "task-0001", "--project", "alpha-app", "--json"])
        review = runner.invoke(app, ["task", "review", "task-0001", "--project", "alpha-app", "--json"])
    finally:
        os.chdir(old_cwd)

    assert next_action.exit_code == 0, next_action.output
    next_action_payload = json.loads(next_action.output)
    assert (
        next_action_payload["recommended_command"]
        == "devflow task review-patch task-0001 --project alpha-app --agent qwopus-implementer"
    )

    assert review.exit_code == 0, review.output
    review_payload = json.loads(review.output)
    assert review_payload["task"]["title"] == "alpha review task"
    assert review_payload["patch_proposal"]["has_proposal_patch"] is True
    assert (
        review_payload["next_action"]["recommended_command"]
        == "devflow task review-patch task-0001 --project alpha-app --agent qwopus-implementer"
    )
    assert "cwd review task" not in review.output


def test_task_review_patch_project_writes_registered_project_evidence(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    _commit_all(projects_root / "alpha-app", "project baseline")
    create_task(projects_root / "alpha-app", "alpha patch task")
    create_task(control_root, "cwd patch task")

    project_agent_dir = (
        projects_root / "alpha-app" / ".devflow" / "tasks" / "task-0001" / "agents" / "qwopus-implementer"
    )
    project_agent_dir.mkdir(parents=True, exist_ok=True)
    (project_agent_dir / "proposal.patch").write_text(_modify_patch("docs/agent.md"), encoding="utf-8")

    cwd_agent_dir = control_root / ".devflow" / "tasks" / "task-0001" / "agents" / "qwopus-implementer"
    cwd_agent_dir.mkdir(parents=True, exist_ok=True)
    (cwd_agent_dir / "proposal.patch").write_text(_modify_patch("docs/cwd.md"), encoding="utf-8")

    old_cwd = Path.cwd()
    try:
        os.chdir(control_root)
        result = runner.invoke(
            app,
            ["task", "review-patch", "task-0001", "--project", "alpha-app", "--agent", "qwopus-implementer"],
        )
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 0, result.output
    assert "Patch Review for alpha-app:task-0001" in result.output
    project_review_path = (
        projects_root
        / "alpha-app"
        / ".devflow"
        / "tasks"
        / "task-0001"
        / "local-model-runs"
        / "agent-qwopus-implementer"
        / "patch-review.json"
    )
    cwd_review_path = (
        control_root
        / ".devflow"
        / "tasks"
        / "task-0001"
        / "local-model-runs"
        / "agent-qwopus-implementer"
        / "patch-review.json"
    )
    assert project_review_path.is_file()
    assert not cwd_review_path.exists()
    review = json.loads(project_review_path.read_text(encoding="utf-8"))
    assert review["files_touched"] == ["docs/agent.md"]
    assert review["next_action"]["command"] == "devflow task show task-0001 --project alpha-app"


def test_task_patch_dry_run_project_writes_registered_project_evidence(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    _commit_all(projects_root / "alpha-app", "project baseline")
    create_task(projects_root / "alpha-app", "alpha dry-run task")
    create_task(control_root, "cwd dry-run task")

    workspace_file = projects_root / "alpha-app" / ".devflow" / "workspaces" / "task-0001" / "docs" / "agent.md"
    workspace_file.parent.mkdir(parents=True, exist_ok=True)
    workspace_file.write_text("old\n", encoding="utf-8")

    project_agent_dir = (
        projects_root / "alpha-app" / ".devflow" / "tasks" / "task-0001" / "agents" / "qwopus-implementer"
    )
    project_agent_dir.mkdir(parents=True, exist_ok=True)
    (project_agent_dir / "proposal.patch").write_text(_modify_patch("docs/agent.md"), encoding="utf-8")

    old_cwd = Path.cwd()
    try:
        os.chdir(control_root)
        review = runner.invoke(
            app,
            ["task", "review-patch", "task-0001", "--project", "alpha-app", "--agent", "qwopus-implementer"],
        )
        result = runner.invoke(
            app,
            ["task", "patch-dry-run", "task-0001", "--project", "alpha-app", "--agent", "qwopus-implementer"],
        )
    finally:
        os.chdir(old_cwd)

    assert review.exit_code == 0, review.output
    assert result.exit_code == 0, result.output
    assert "Patch Dry-run Preview for alpha-app:task-0001" in result.output
    dry_run_path = (
        projects_root
        / "alpha-app"
        / ".devflow"
        / "tasks"
        / "task-0001"
        / "local-model-runs"
        / "agent-qwopus-implementer"
        / "patch-dry-run.json"
    )
    assert dry_run_path.is_file()
    assert not (
        control_root
        / ".devflow"
        / "tasks"
        / "task-0001"
        / "local-model-runs"
        / "agent-qwopus-implementer"
        / "patch-dry-run.json"
    ).exists()
    dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
    assert dry_run["dry_run_status"] == "would_apply_cleanly"
    assert dry_run["files_would_modify"] == ["docs/agent.md"]
    assert dry_run["next_action"]["command"] == "devflow task show task-0001 --project alpha-app"
    assert workspace_file.read_text(encoding="utf-8") == "old\n"


def test_task_apply_patch_project_mutates_registered_project_workspace(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    _commit_all(projects_root / "alpha-app", "project baseline")
    create_task(projects_root / "alpha-app", "alpha apply task")
    create_task(control_root, "cwd apply task")

    project_workspace_file = projects_root / "alpha-app" / ".devflow" / "workspaces" / "task-0001" / "docs" / "agent.md"
    project_workspace_file.parent.mkdir(parents=True, exist_ok=True)
    project_workspace_file.write_text("old\n", encoding="utf-8")
    project_agent_dir = (
        projects_root / "alpha-app" / ".devflow" / "tasks" / "task-0001" / "agents" / "qwopus-implementer"
    )
    project_agent_dir.mkdir(parents=True, exist_ok=True)
    (project_agent_dir / "proposal.patch").write_text(
        _modify_patch("docs/agent.md", old="old", new="project-new"),
        encoding="utf-8",
    )

    cwd_workspace_file = control_root / ".devflow" / "workspaces" / "task-0001" / "docs" / "agent.md"
    cwd_workspace_file.parent.mkdir(parents=True, exist_ok=True)
    cwd_workspace_file.write_text("old\n", encoding="utf-8")
    cwd_agent_dir = control_root / ".devflow" / "tasks" / "task-0001" / "agents" / "qwopus-implementer"
    cwd_agent_dir.mkdir(parents=True, exist_ok=True)
    (cwd_agent_dir / "proposal.patch").write_text(
        _modify_patch("docs/agent.md", old="old", new="cwd-new"),
        encoding="utf-8",
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(control_root)
        cwd_review = runner.invoke(app, ["task", "review-patch", "task-0001", "--agent", "qwopus-implementer"])
        cwd_dry_run = runner.invoke(app, ["task", "patch-dry-run", "task-0001", "--agent", "qwopus-implementer"])
        project_review = runner.invoke(
            app,
            ["task", "review-patch", "task-0001", "--project", "alpha-app", "--agent", "qwopus-implementer"],
        )
        project_dry_run = runner.invoke(
            app,
            ["task", "patch-dry-run", "task-0001", "--project", "alpha-app", "--agent", "qwopus-implementer"],
        )
        result = runner.invoke(
            app,
            ["task", "apply-patch", "task-0001", "--project", "alpha-app", "--agent", "qwopus-implementer"],
        )
    finally:
        os.chdir(old_cwd)

    assert cwd_review.exit_code == 0, cwd_review.output
    assert cwd_dry_run.exit_code == 0, cwd_dry_run.output
    assert project_review.exit_code == 0, project_review.output
    assert project_dry_run.exit_code == 0, project_dry_run.output
    assert result.exit_code == 0, result.output
    assert (
        "Successfully applied patch from agent 'qwopus-implementer' "
        "to task workspace 'alpha-app:task-0001'."
    ) in result.output
    assert "project_root:" in result.output
    assert "devflow task verify task-0001 --project alpha-app --shell \"<command>\"" in result.output
    assert project_workspace_file.read_text(encoding="utf-8") == "project-new\n"
    assert cwd_workspace_file.read_text(encoding="utf-8") == "old\n"
    assert (
        projects_root / "alpha-app" / ".devflow" / "tasks" / "task-0001" / "patch-application.json"
    ).is_file()
    assert not (control_root / ".devflow" / "tasks" / "task-0001" / "patch-application.json").exists()


def test_task_promote_preview_project_reads_registered_project_root_not_cwd(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"
    control_root.mkdir()

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    project_root = projects_root / "alpha-app"
    (project_root / "promote.txt").write_text("project-main\n", encoding="utf-8")
    (control_root / "promote.txt").write_text("cwd-main\n", encoding="utf-8")
    _commit_all(project_root, "project baseline")
    create_task(project_root, "alpha promote task")
    create_task(control_root, "cwd promote task")

    project_workspace_file = project_root / ".devflow" / "workspaces" / "task-0001" / "promote.txt"
    cwd_workspace_file = control_root / ".devflow" / "workspaces" / "task-0001" / "promote.txt"
    project_workspace_file.write_text("project-workspace\n", encoding="utf-8")
    cwd_workspace_file.write_text("cwd-workspace\n", encoding="utf-8")
    project_task_yaml = project_root / ".devflow" / "tasks" / "task-0001" / "task.yaml"
    task_yaml_before = project_task_yaml.read_text(encoding="utf-8")

    old_cwd = Path.cwd()
    try:
        os.chdir(control_root)
        result = runner.invoke(app, ["task", "promote-preview", "task-0001", "--project", "alpha-app"])
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 0, result.output
    assert "task: alpha-app:task-0001" in result.output
    assert f"project_root: {project_root}" in result.output
    assert "Modified files:" in result.output
    assert "  - promote.txt" in result.output
    assert "-project-main" in result.output
    assert "+project-workspace" in result.output
    assert "cwd-main" not in result.output
    assert "cwd-workspace" not in result.output
    assert "from the project_root above" in result.output
    assert project_task_yaml.read_text(encoding="utf-8") == task_yaml_before
    assert (project_root / ".devflow" / "tasks" / "task-0001" / "promotion-preview.json").exists()
    assert not (control_root / ".devflow" / "tasks" / "task-0001" / "promotion-preview.json").exists()


def test_task_promote_project_promotes_registered_project_root_not_cwd(tmp_path: Path, monkeypatch) -> None:
    _devflow_home(tmp_path, monkeypatch)
    projects_root = tmp_path / "projects"
    control_root = tmp_path / "control-room"
    control_root.mkdir()

    created = runner.invoke(app, ["project", "create", "Alpha App", "--projects-root", projects_root.as_posix()])
    assert created.exit_code == 0, created.output
    project_root = projects_root / "alpha-app"
    (project_root / "promote.txt").write_text("project-main\n", encoding="utf-8")
    (control_root / "promote.txt").write_text("cwd-main\n", encoding="utf-8")
    _commit_all(project_root, "project baseline")

    create_task(project_root, "alpha promote task")
    create_task(control_root, "cwd promote task")
    project_workspace_file = project_root / ".devflow" / "workspaces" / "task-0001" / "promote.txt"
    cwd_workspace_file = control_root / ".devflow" / "workspaces" / "task-0001" / "promote.txt"
    project_workspace_file.write_text("project-promoted\n", encoding="utf-8")
    cwd_workspace_file.write_text("cwd-workspace\n", encoding="utf-8")

    verify = runner.invoke(
        app,
        ["task", "verify", "task-0001", "--project", "alpha-app", "--shell", "test -f promote.txt"],
    )
    assert verify.exit_code == 0, verify.output

    old_cwd = Path.cwd()
    try:
        os.chdir(control_root)
        result = runner.invoke(app, ["task", "promote", "task-0001", "--project", "alpha-app"], input="y\n")
    finally:
        os.chdir(old_cwd)

    assert result.exit_code == 0, result.output
    assert "task: alpha-app:task-0001" in result.output
    assert f"project_root: {project_root}" in result.output
    assert "Promotion complete." in result.output
    assert project_root.joinpath("promote.txt").read_text(encoding="utf-8") == "project-promoted\n"
    assert control_root.joinpath("promote.txt").read_text(encoding="utf-8") == "cwd-main\n"
    assert (control_root / ".devflow" / "workspaces" / "task-0001" / "promote.txt").read_text(
        encoding="utf-8"
    ) == "cwd-workspace\n"
    project_task = yaml.safe_load(
        (project_root / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8")
    )
    cwd_task = yaml.safe_load((control_root / ".devflow" / "tasks" / "task-0001" / "task.yaml").read_text(encoding="utf-8"))
    assert project_task["status"] == "promoted"
    assert cwd_task["status"] == "created"


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
