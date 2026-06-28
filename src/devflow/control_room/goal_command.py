from __future__ import annotations

from pathlib import Path

import typer


goal_app = typer.Typer(help="Manage goals and planning scaffolds")


@goal_app.command("init")
def goal_init(
    goal_id: str | None = typer.Argument(None, help="Explicit goal ID (e.g. G-0001)."),
    from_file: str = typer.Option(..., "--from", help="Path to the goal markdown brief."),
) -> None:
    """Initialize a durable goal scaffold from a markdown brief."""
    from devflow.control_room.goals import create_goal_from_markdown

    try:
        from_path = Path(from_file)
        record = create_goal_from_markdown(Path.cwd(), from_path, goal_id=goal_id)
        typer.echo(f"Initialized Goal {record.id}")
        typer.echo(f"Directory: .devflow/goals/{record.id}/")
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)


@goal_app.command("show")
def goal_show(goal_id: str) -> None:
    """Show a goal and its scaffolded artifacts."""
    from devflow.control_room.goals import render_goal_summary

    try:
        summary = render_goal_summary(Path.cwd(), goal_id)
        typer.echo(summary, nl=False)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)


@goal_app.command("list")
def goal_list() -> None:
    """List durable goals."""
    from devflow.control_room.goal_projection import render_goal_list

    typer.echo(render_goal_list(Path.cwd()), nl=False)


def _set_goal_lifecycle_command(goal_id: str, lifecycle: str, reason: str) -> None:
    from devflow.control_room.goal_lifecycle import (
        GoalLifecycleError,
        lifecycle_result,
        render_lifecycle_result,
        set_goal_lifecycle,
    )

    command = f"devflow goal {lifecycle if lifecycle != 'active' else 'activate'} {goal_id}"
    if reason:
        command = f"{command} --reason {reason!r}"
    try:
        state = set_goal_lifecycle(Path.cwd(), goal_id, lifecycle=lifecycle, reason=reason, command=command)
    except GoalLifecycleError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(render_lifecycle_result(lifecycle_result(Path.cwd(), state)), nl=False)


@goal_app.command("activate")
def goal_activate(
    goal_id: str,
    reason: str = typer.Option("", "--reason", help="Reason for activating this goal."),
) -> None:
    """Mark a goal active for freshness-loop projection."""
    _set_goal_lifecycle_command(goal_id, "active", reason)


@goal_app.command("pause")
def goal_pause(
    goal_id: str,
    reason: str = typer.Option(..., "--reason", help="Reason for pausing this goal."),
) -> None:
    """Pause goal execution without deleting evidence."""
    _set_goal_lifecycle_command(goal_id, "paused", reason)


@goal_app.command("block")
def goal_block(
    goal_id: str,
    reason: str = typer.Option(..., "--reason", help="Blocking reason."),
) -> None:
    """Block goal execution until a human decision or external repair."""
    _set_goal_lifecycle_command(goal_id, "blocked", reason)


@goal_app.command("complete")
def goal_complete(
    goal_id: str,
    reason: str = typer.Option(..., "--reason", help="Evidence-backed completion reason."),
) -> None:
    """Record human-approved goal completion."""
    _set_goal_lifecycle_command(goal_id, "complete", reason)


@goal_app.command("archive")
def goal_archive(
    goal_id: str,
    reason: str = typer.Option(..., "--reason", help="Archive reason."),
) -> None:
    """Archive a goal while preserving its evidence."""
    _set_goal_lifecycle_command(goal_id, "archived", reason)


@goal_app.command("status")
def goal_status(goal_id: str) -> None:
    """Show the status of a specific durable goal."""
    from devflow.control_room.goal_projection import render_goal_status

    typer.echo(render_goal_status(Path.cwd(), goal_id), nl=False)


@goal_app.command("next")
def goal_next(goal_id: str) -> None:
    """Recommend the next safest planning or implementation command for a goal."""
    from devflow.control_room.goal_projection import build_goal_status_projection

    try:
        proj = build_goal_status_projection(Path.cwd(), goal_id)
        typer.echo(f"Next action: {proj.next_action_label}")
        typer.echo(f"Command:     {proj.next_action_command or 'None'}")
        typer.echo(f"Reason:      {proj.next_action_reason}")
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)


@goal_app.command("slices")
def goal_slices(goal_id: str) -> None:
    """Show task slices from task-slices.yaml in a compact reviewable format."""
    from devflow.control_room.goal_tasks import render_goal_slices

    try:
        output = render_goal_slices(Path.cwd(), goal_id)
        typer.echo(output, nl=False)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)


@goal_app.command("create-task")
def goal_create_task(
    goal_id: str,
    slice_id: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be created without writing any task artifacts."),
) -> None:
    """Create a normal DevFlow task from a selected goal task slice."""
    from devflow.control_room.goal_tasks import get_goal_task_slice, create_task_from_goal_slice

    try:
        if dry_run:
            slice_data = get_goal_task_slice(Path.cwd(), goal_id, slice_id)
            typer.echo(f"[Dry Run] Would create task from {goal_id} / {slice_id}")
            typer.echo(f"Title: {slice_data.title}")
            return

        created = create_task_from_goal_slice(Path.cwd(), goal_id, slice_id)
        typer.echo(f"Created {created.task_id} from {created.goal_id} / {created.slice_id}\n")
        typer.echo("Task:")
        typer.echo(f"  {created.task_id} — {created.task_title}\n")
        typer.echo("Linked artifacts:")
        typer.echo(f"  goal: {created.goal_path}")
        typer.echo(f"  slice: {created.slice_id}")
        typer.echo(f"  task: {created.task_path}\n")
        typer.echo("Next:")
        typer.echo(f"  devflow task show {created.task_id}")

        slice_data = get_goal_task_slice(Path.cwd(), goal_id, slice_id)
        if slice_data.execution_mode == "HITL":
            typer.echo("\nThis slice is HITL. Human review is required before execution/promotion.")
        elif slice_data.execution_mode == "AFK":
            typer.echo("\nThis slice is AFK-classified, but execution is still explicit.")
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
