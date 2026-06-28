from __future__ import annotations

from pathlib import Path

import typer


idea_app = typer.Typer(help="Capture and review raw ideas before they become goals or tasks")


@idea_app.command("capture")
def idea_capture(
    text: str,
    title: str | None = typer.Option(None, "--title", help="Optional title override."),
    source: str = typer.Option("manual", "--source", help="Source label for this idea."),
    tag: list[str] = typer.Option([], "--tag", help="Repeatable idea tag."),
) -> None:
    """Capture a raw idea as local, human-reviewed intake evidence."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, capture_idea

        item = capture_idea(Path.cwd(), text, title=title, source=source, tags=tag)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo(f"maturity: {item['maturity']}")
    typer.echo(f"path: .devflow/ideas/{item['id']}/idea.json")
    typer.echo("created_goal: no")
    typer.echo("created_task: no")


@idea_app.command("list")
def idea_list(
    status: str | None = typer.Option(None, "--status", help="Filter by idea status."),
) -> None:
    """List local Idea Foundry items."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, list_ideas, render_idea_list

        typer.echo(render_idea_list(list_ideas(Path.cwd(), status=status)), nl=False)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@idea_app.command("show")
def idea_show(idea_id: str) -> None:
    """Show one Idea Foundry item and its evidence notes."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, render_idea_show, show_idea

        metadata, raw, classification, promotion = show_idea(Path.cwd(), idea_id)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(render_idea_show(metadata, raw, classification, promotion), nl=False)


@idea_app.command("classify")
def idea_classify(
    idea_id: str,
    maturity: str = typer.Option(..., "--maturity", help="spark, concept, candidate, goal_ready, or task_ready."),
    note: str = typer.Option("", "--note", help="Human classification note."),
    tag: list[str] = typer.Option([], "--tag", help="Repeatable replacement tag."),
) -> None:
    """Classify an idea with human-supplied maturity and tags."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, classify_idea

        item = classify_idea(Path.cwd(), idea_id, maturity=maturity, note=note, tags=tag)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo(f"maturity: {item['maturity']}")
    typer.echo("model_called: no")


@idea_app.command("promote")
def idea_promote(
    idea_id: str,
    target: str = typer.Option(..., "--to", help="Promotion target: goal or task."),
    rationale: str = typer.Option(..., "--rationale", help="Human rationale for the promotion decision."),
    title: str | None = typer.Option(None, "--title", help="Optional suggested goal/task title."),
) -> None:
    """Record a human promotion decision without creating goals or tasks."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, promote_idea

        item = promote_idea(Path.cwd(), idea_id, target=target, rationale=rationale, title=title)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo(f"promotion_target: {item['promotion_target']}")
    typer.echo("created_goal: no")
    typer.echo("created_task: no")


@idea_app.command("create-goal")
def idea_create_goal(
    idea_id: str,
    title: str | None = typer.Option(None, "--title", help="Optional goal title override."),
    goal_id: str | None = typer.Option(None, "--goal-id", help="Optional explicit goal id."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without creating goal artifacts."),
) -> None:
    """Create a durable goal scaffold from a promoted goal-ready idea."""
    try:
        from devflow.control_room.idea_execution_bridge import (
            IdeaExecutionBridgeError,
            create_goal_from_idea,
            preview_goal_from_idea,
        )

        result = (
            preview_goal_from_idea(Path.cwd(), idea_id, title=title, goal_id=goal_id)
            if dry_run
            else create_goal_from_idea(Path.cwd(), idea_id, title=title, goal_id=goal_id)
        )
    except IdeaExecutionBridgeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if dry_run:
        typer.echo("would_create_goal: yes")
    typer.echo(f"idea_id: {result.idea_id}")
    typer.echo(f"created_goal_id: {result.created_id}")
    typer.echo(f"created_goal_path: {result.created_path}")
    typer.echo(f"link_path: {result.link_path}")
    typer.echo(f"next: {result.next_command}")
    typer.echo("worker_ran: no")
    typer.echo("verification_ran: no")


@idea_app.command("scaffold-goal")
def idea_scaffold_goal(
    idea_id: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing scaffold evidence."),
) -> None:
    """Create reviewable intent-to-goal scaffold evidence from an idea."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError
        from devflow.control_room.intent_scaffold import (
            preview_scaffold_from_idea,
            write_scaffold_from_idea,
        )

        proposal = (
            preview_scaffold_from_idea(Path.cwd(), idea_id)
            if dry_run
            else write_scaffold_from_idea(Path.cwd(), idea_id)
        )
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if dry_run:
        typer.echo("would_write_scaffold: yes")
    typer.echo(f"idea_id: {idea_id}")
    typer.echo(f"status: {proposal['status']}")
    typer.echo(f"title: {proposal['normalized_intent']['title']}")
    if not dry_run and proposal["status"] == "ready_for_review":
        typer.echo(f"scaffold_path: .devflow/ideas/{idea_id}/scaffold-goal.json")
    for command in proposal.get("next_commands") or []:
        typer.echo(f"next: {command}")
    typer.echo("created_goal: no")
    typer.echo("created_task: no")
    typer.echo("worker_ran: no")
    typer.echo("verification_ran: no")


@idea_app.command("create-task")
def idea_create_task(
    idea_id: str,
    title: str | None = typer.Option(None, "--title", help="Optional task title override."),
    git_worktree: bool = typer.Option(
        False,
        "--git-worktree",
        help="Create the task with the existing Git-native worktree lane.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without creating task artifacts."),
) -> None:
    """Create a Dev-Flow task from a promoted task-ready idea."""
    try:
        from devflow.control_room.idea_execution_bridge import (
            IdeaExecutionBridgeError,
            create_task_from_idea,
            preview_task_from_idea,
        )

        result = (
            preview_task_from_idea(Path.cwd(), idea_id, title=title, git_worktree=git_worktree)
            if dry_run
            else create_task_from_idea(Path.cwd(), idea_id, title=title, git_worktree=git_worktree)
        )
    except IdeaExecutionBridgeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if dry_run:
        typer.echo("would_create_task: yes")
    typer.echo(f"idea_id: {result.idea_id}")
    typer.echo(f"created_task_id: {result.created_id}")
    typer.echo(f"created_task_path: {result.created_path}")
    typer.echo(f"link_path: {result.link_path}")
    typer.echo(f"git_worktree: {'yes' if result.git_worktree else 'no'}")
    typer.echo(f"next: {result.next_command}")
    typer.echo("worker_ran: no")
    typer.echo("verification_ran: no")


@idea_app.command("park")
def idea_park(
    idea_id: str,
    reason: str = typer.Option("No reason supplied.", "--reason", help="Why this idea is safe to revisit later."),
) -> None:
    """Park an idea without losing its evidence."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, park_idea

        item = park_idea(Path.cwd(), idea_id, reason=reason)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo("evidence_deleted: no")


@idea_app.command("archive")
def idea_archive(
    idea_id: str,
    reason: str = typer.Option("No reason supplied.", "--reason", help="Human archive reason."),
) -> None:
    """Archive an idea while preserving its evidence."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, archive_idea

        item = archive_idea(Path.cwd(), idea_id, reason=reason)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo("evidence_deleted: no")
