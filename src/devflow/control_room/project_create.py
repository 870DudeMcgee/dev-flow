from __future__ import annotations

import subprocess
from pathlib import Path

from pydantic import BaseModel

from devflow.control_room.project_models import (
    ProjectMetadata,
    ProjectPrivacy,
    ProjectPublicationPolicy,
    ProjectSourceControl,
    ProjectSourceControlMode,
    ProjectTaskDefaults,
)
from devflow.control_room.project_registry import (
    ProjectRegistryError,
    build_project_record,
    default_projects_root,
    infer_remote_provider,
    load_project_metadata,
    normalize_project_id,
    normalize_source_control_mode,
    register_project,
    set_projects_root,
    source_control_from_git,
    track_devflow_context_policy,
)
from devflow.control_room.service import init_control_room


class ProjectCreateResult(BaseModel):
    project_id: str
    name: str
    path: str
    source_control_mode: ProjectSourceControlMode
    remote_url: str | None = None


def create_project(
    name: str,
    *,
    projects_root: Path | None = None,
    source_control: str = "local_git",
    private_context: bool = False,
    remote_url: str | None = None,
) -> ProjectCreateResult:
    mode = normalize_source_control_mode(source_control)
    if remote_url and mode not in {"remote_git", "github_managed"}:
        raise ProjectRegistryError("--remote-url requires --source-control remote-git or github-managed.")
    if mode in {"remote_git", "github_managed"} and not remote_url:
        raise ProjectRegistryError(f"--source-control {mode.replace('_', '-')} requires --remote-url.")

    root = (projects_root or default_projects_root()).expanduser().resolve()
    set_projects_root(root)
    project_id = normalize_project_id(name)
    project_root = root / project_id
    if project_root.exists():
        raise ProjectRegistryError(f"Project path already exists: {project_root}")
    project_root.mkdir(parents=True)

    source = _source_control_policy(mode, remote_url)
    metadata = _project_metadata(
        project_id=project_id,
        name=name,
        root=project_root,
        source_control=source,
        private_context=private_context,
    )
    _seed_project_files(project_root, name=name, private_context=private_context)
    if source.local_repo:
        _init_git_repo(project_root)
        if source.remote_url:
            _run_git(project_root, "remote", "add", "origin", source.remote_url)

    init_control_room(project_root, project_seed=metadata)
    register_project(build_project_record(metadata))
    return ProjectCreateResult(
        project_id=project_id,
        name=name,
        path=project_root.as_posix(),
        source_control_mode=metadata.source_control.mode,
        remote_url=metadata.source_control.remote_url,
    )


def import_project(
    root: Path,
    *,
    project_id: str | None = None,
    name: str | None = None,
    private_context: bool = False,
) -> ProjectCreateResult:
    project_root = root.expanduser().resolve()
    if not project_root.exists() or not project_root.is_dir():
        raise ProjectRegistryError(f"Project path does not exist: {project_root}")

    metadata: ProjectMetadata | None = None
    try:
        metadata = load_project_metadata(project_root)
    except ProjectRegistryError:
        pass

    if metadata is None:
        resolved_id = normalize_project_id(project_id or project_root.name)
        resolved_name = name or _title_from_project_id(resolved_id)
        metadata = _project_metadata(
            project_id=resolved_id,
            name=resolved_name,
            root=project_root,
            source_control=source_control_from_git(project_root),
            private_context=private_context,
        )
        if not (project_root / ".gitignore").exists():
            (project_root / ".gitignore").write_text(
                render_gitignore(private_context=private_context),
                encoding="utf-8",
            )
        init_control_room(project_root, project_seed=metadata)
    else:
        if project_id and normalize_project_id(project_id) != metadata.project_id:
            raise ProjectRegistryError(
                f"Imported metadata uses project_id {metadata.project_id}; cannot register as {project_id}."
            )

    register_project(build_project_record(metadata))
    return ProjectCreateResult(
        project_id=metadata.project_id,
        name=metadata.name,
        path=metadata.root_path,
        source_control_mode=metadata.source_control.mode,
        remote_url=metadata.source_control.remote_url,
    )


def render_gitignore(*, private_context: bool = False) -> str:
    if private_context:
        devflow_lines = [
            "# DevFlow local control-room state",
            ".devflow/",
        ]
    else:
        devflow_lines = [
            "# DevFlow runtime / local evidence",
            ".devflow/tasks/",
            ".devflow/workspaces/",
            ".devflow/worktrees/",
            ".devflow/system/",
            ".devflow/reports/",
            ".devflow/freshness/",
            ".devflow/dogfood/runs/",
            ".devflow/outcome-validations/",
        ]
    shared_lines = [
        "",
        "# Python / build / local",
        "__pycache__/",
        "*.py[cod]",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        ".venv/",
        "build/",
        "dist/",
        "*.egg-info/",
        ".DS_Store",
        "",
    ]
    return "\n".join(devflow_lines + shared_lines)


def _project_metadata(
    *,
    project_id: str,
    name: str,
    root: Path,
    source_control: ProjectSourceControl,
    private_context: bool,
) -> ProjectMetadata:
    return ProjectMetadata(
        id=project_id,
        project_id=project_id,
        name=name,
        purpose=f"{name} project managed by DevFlow.",
        root_path=root.as_posix(),
        source_control=source_control,
        remote_publication=ProjectPublicationPolicy(),
        task_defaults=ProjectTaskDefaults(),
        privacy=ProjectPrivacy(
            default_visibility="local_only",
            allow_github_upload=False,
            allow_remote_provider_context=False,
        ),
        version_control=track_devflow_context_policy(private_context),
    )


def _source_control_policy(mode: ProjectSourceControlMode, remote_url: str | None) -> ProjectSourceControl:
    if mode == "none":
        return ProjectSourceControl(mode="none", local_repo=False, remote_provider="none", remote_url=None)
    if remote_url:
        return ProjectSourceControl(
            mode=mode,
            local_repo=True,
            remote_provider=infer_remote_provider(remote_url),
            remote_url=remote_url,
        )
    return ProjectSourceControl(mode=mode, local_repo=True, remote_provider="none", remote_url=None)


def _seed_project_files(project_root: Path, *, name: str, private_context: bool) -> None:
    readme = project_root / "README.md"
    if not readme.exists():
        readme.write_text(f"# {name}\n", encoding="utf-8")
    gitignore = project_root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(render_gitignore(private_context=private_context), encoding="utf-8")
    (project_root / "src").mkdir(exist_ok=True)
    (project_root / "tests").mkdir(exist_ok=True)
    (project_root / "docs").mkdir(exist_ok=True)


def _init_git_repo(root: Path) -> None:
    proc = subprocess.run(["git", "init", "-b", "main"], cwd=root, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return
    subprocess.run(["git", "init"], cwd=root, capture_output=True, text=True, check=True)
    _run_git(root, "branch", "-M", "main")


def _run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)


def _title_from_project_id(project_id: str) -> str:
    return " ".join(part.capitalize() for part in project_id.split("-"))
