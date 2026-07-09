from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from devflow.legacy.control_room.maintenance import repair_state, reset_dogfood_state, reset_test_state


maintenance_app = typer.Typer(help="Repair or reset ignored Dev-Flow runtime state")


@maintenance_app.command("reset-dogfood-state")
def maintenance_reset_dogfood_state(
    preview: bool = typer.Option(False, "--preview", help="Preview ignored runtime artifact removal."),
    yes: bool = typer.Option(False, "--yes", help="Apply ignored runtime artifact removal."),
) -> None:
    """Reset disposable dogfood/task runtime artifacts while preserving generated seed state."""
    if preview == yes:
        typer.echo("Choose exactly one of --preview or --yes.", err=True)
        raise typer.Exit(code=1)
    result = reset_dogfood_state(Path.cwd(), apply=yes)
    typer.echo(f"mode: {'apply' if yes else 'preview'}")
    _echo_maintenance_result(result)
    if result.refused:
        raise typer.Exit(code=1)


@maintenance_app.command("reset-test-state")
def maintenance_reset_test_state(
    preview: bool = typer.Option(False, "--preview", help="Preview local test runtime artifact removal."),
    yes: bool = typer.Option(False, "--yes", help="Apply local test runtime artifact removal."),
) -> None:
    """Reset local test task/workspace/worktree artifacts while preserving project state."""
    if preview == yes:
        typer.echo("Choose exactly one of --preview or --yes.", err=True)
        raise typer.Exit(code=1)
    result = reset_test_state(Path.cwd(), apply=yes)
    typer.echo(f"mode: {'apply' if yes else 'preview'}")
    _echo_maintenance_result(result)
    if result.refused:
        raise typer.Exit(code=1)


@maintenance_app.command("repair-state")
def maintenance_repair_state(
    preview: bool = typer.Option(False, "--preview", help="Preview missing task baseline artifact repair."),
    yes: bool = typer.Option(False, "--yes", help="Restore missing task baseline artifacts."),
) -> None:
    """Restore missing task baseline artifacts without overwriting existing evidence."""
    if preview == yes:
        typer.echo("Choose exactly one of --preview or --yes.", err=True)
        raise typer.Exit(code=1)
    result = repair_state(Path.cwd(), apply=yes)
    typer.echo(f"mode: {'apply' if yes else 'preview'}")
    _echo_maintenance_result(result)
    if result.refused:
        raise typer.Exit(code=1)


def _echo_maintenance_result(result: Any) -> None:
    for path in result.would_remove:
        typer.echo(f"would_remove: {path}")
    for path in result.removed:
        typer.echo(f"removed: {path}")
    for path in result.would_repair:
        typer.echo(f"would_repair: {path}")
    for path in result.repaired:
        typer.echo(f"repaired: {path}")
    for item in result.refused:
        typer.echo(f"refused: {item}")
    if not (
        result.would_remove
        or result.removed
        or result.would_repair
        or result.repaired
        or result.refused
    ):
        typer.echo("nothing_to_do: yes")
