import json
from pathlib import Path

import typer


scheduler_app = typer.Typer(help="Inspect simple scheduler queue and retry evidence")


@scheduler_app.command("status")
def scheduler_status(json_output: bool = typer.Option(False, "--json", help="Print scheduler status as JSON.")) -> None:
    """Show the derived simple scheduler projection."""
    from devflow.legacy.control_room import scheduler_projection

    snapshot = scheduler_projection.build_scheduler_snapshot(Path.cwd())
    if json_output:
        typer.echo(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        typer.echo(scheduler_projection.render_scheduler_snapshot(snapshot), nl=False)


@scheduler_app.command("retry")
def scheduler_retry(
    task_id: str = typer.Argument(..., help="Task ID to mark for manual retry."),
    reason: str = typer.Option(..., "--reason", help="Human-readable retry reason."),
    json_output: bool = typer.Option(False, "--json", help="Print retry request as JSON."),
) -> None:
    """Write explicit retry-request evidence without rerunning work."""
    from devflow.legacy.control_room import scheduler_projection

    try:
        request = scheduler_projection.request_scheduler_retry(Path.cwd(), task_id, reason=reason)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(request.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        typer.echo(f"retry_request: {request.retry_request_path}")
        typer.echo(f"next_safe_action: {request.recommended_next_command}")
