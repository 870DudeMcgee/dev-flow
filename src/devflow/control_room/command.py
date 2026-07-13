"""V2 status board CLI commands.

Usage:
  devflow status serve [--host 127.0.0.1] [--port 8770]

The browser combines pipeline status, bounded operator controls, and brainstorm
chat. Hermes remains the messaging/tool/orchestration harness.
"""

from __future__ import annotations

from pathlib import Path

import typer

status_app = typer.Typer(help="DevFlow pipeline status board — live view of what's happening.")


@status_app.command("serve")
def status_serve_command(
    host: str = typer.Option("127.0.0.1", "--host", help="Host for the status board server."),
    port: int = typer.Option(8770, "--port", min=0, help="Port for the status board server."),
) -> None:
    """Start the pipeline status board web surface."""
    from devflow.control_room.server import run_server

    repo_root = Path.cwd()

    typer.echo("Starting status board...")
    typer.echo(f"  repo: {repo_root}")
    run_server(repo_root, host=host, port=port)
