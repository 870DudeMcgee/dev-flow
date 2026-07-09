from __future__ import annotations

from pathlib import Path

import typer

from devflow.legacy.control_room.project_create import create_project as create_managed_project
from devflow.legacy.control_room.project_create import import_project as import_managed_project
from devflow.legacy.control_room.project_registry import (
    ProjectRegistryError,
    archive_project,
    doctor_project,
    remove_project,
    render_project_list,
    render_project_show,
    render_project_status,
    update_project_remote_policy,
)


project_app = typer.Typer(help="Create and manage registered projects")


@project_app.command("create")
def project_create_command(
    name: str = typer.Argument(..., help="Project display name."),
    projects_root: str | None = typer.Option(None, "--projects-root", help="Directory that will contain managed projects."),
    source_control: str = typer.Option("local-git", "--source-control", help="none, local-git, remote-git, or github-managed."),
    private_context: bool = typer.Option(False, "--private-context", help="Ignore all .devflow/ context in the new repo."),
    remote_url: str | None = typer.Option(None, "--remote-url", help="Explicit remote URL for remote-git/github-managed projects."),
) -> None:
    """Create a separate local project root and register it with DevFlow."""
    try:
        result = create_managed_project(
            name,
            projects_root=Path(projects_root) if projects_root else None,
            source_control=source_control,
            private_context=private_context,
            remote_url=remote_url,
        )
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Created project {result.project_id}")
    typer.echo(f"path: {result.path}")
    typer.echo(f"source_control: {result.source_control_mode}")
    typer.echo(f"remote_url: {result.remote_url or 'none'}")
    typer.echo("github: disabled unless explicitly connected/published")


@project_app.command("import")
def project_import_command(
    path: str = typer.Argument(..., help="Existing project directory to register."),
    project_id: str | None = typer.Option(None, "--project-id", help="Explicit registry id when metadata does not exist."),
    name: str | None = typer.Option(None, "--name", help="Display name when metadata does not exist."),
    private_context: bool = typer.Option(False, "--private-context", help="Ignore all .devflow/ context if metadata is created."),
) -> None:
    """Register an existing project root with DevFlow."""
    try:
        result = import_managed_project(
            Path(path),
            project_id=project_id,
            name=name,
            private_context=private_context,
        )
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Imported project {result.project_id}")
    typer.echo(f"path: {result.path}")
    typer.echo(f"source_control: {result.source_control_mode}")
    typer.echo(f"remote_url: {result.remote_url or 'none'}")


@project_app.command("list")
def project_list_command(
    include_archived: bool = typer.Option(False, "--include-archived", help="Include archived projects."),
) -> None:
    """List registered projects."""
    try:
        typer.echo(render_project_list(include_archived=include_archived), nl=False)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@project_app.command("show")
def project_show_command(project_id: str) -> None:
    """Show registry and project-local metadata for one project."""
    try:
        typer.echo(render_project_show(project_id), nl=False)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@project_app.command("status")
def project_status_command(project_id: str) -> None:
    """Show task health for one registered project."""
    try:
        typer.echo(render_project_status(project_id), nl=False)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@project_app.command("doctor")
def project_doctor_command(project_id: str) -> None:
    """Check one registered project's metadata and source-control policy."""
    try:
        checks = doctor_project(project_id)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    failed = False
    for name, ok, detail in checks:
        marker = "ok" if ok else "missing"
        typer.echo(f"{marker}: {name} ({detail})")
        failed = failed or not ok
    if failed:
        raise typer.Exit(code=1)


@project_app.command("archive")
def project_archive_command(project_id: str) -> None:
    """Archive a project in the registry without deleting files."""
    try:
        record = archive_project(project_id)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Archived project {record.project_id}")


@project_app.command("remove")
def project_remove_command(
    project_id: str,
    registry_only: bool = typer.Option(False, "--registry-only", help="Remove only the registry entry; project files are never deleted."),
) -> None:
    """Remove a project from the registry without deleting its directory."""
    if not registry_only:
        typer.echo("Error: project remove requires --registry-only. DevFlow does not delete project directories.", err=True)
        raise typer.Exit(code=1)
    try:
        record = remove_project(project_id)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Removed project {record.project_id} from registry")


@project_app.command("connect-github")
def project_connect_github_command(
    project_id: str,
    remote_url: str = typer.Option(..., "--remote-url", help="Existing GitHub repository URL."),
    allow_push: bool = typer.Option(False, "--allow-push", help="Opt in to devflow push-main for this project."),
) -> None:
    """Attach an explicit GitHub remote policy to a registered local Git project."""
    try:
        metadata = update_project_remote_policy(project_id, remote_url=remote_url, push_allowed=allow_push)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Connected GitHub remote for {metadata.project_id}")
    typer.echo(f"remote_url: {metadata.source_control.remote_url}")
    typer.echo(f"push_allowed: {'yes' if metadata.remote_publication.push_allowed else 'no'}")
