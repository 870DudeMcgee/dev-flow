from __future__ import annotations

import json
from pathlib import Path

import typer


local_model_app = typer.Typer(help="Manage local model server lifecycle")


@local_model_app.command("status")
def local_model_status_command(
    json_output: bool = typer.Option(False, "--json", help="Print local model server status as JSON."),
    include_ollama: bool = typer.Option(False, "--include-ollama", help="Include Ollama server processes in status."),
) -> None:
    """Show resident local model server processes."""
    from devflow.control_room import local_model_server

    payload = local_model_server.local_model_server_status(include_ollama=include_ollama)
    payload["action"] = "status"
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for line in local_model_server.render_local_model_server_lines(payload):
        typer.echo(line)


@local_model_app.command("stop")
def local_model_stop_command(
    profile: str | None = typer.Argument(None, help="Optional local server profile to stop, such as hermes-qwen32."),
    json_output: bool = typer.Option(False, "--json", help="Print stop result as JSON."),
    include_ollama: bool = typer.Option(False, "--include-ollama", help="Also stop Ollama server processes."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be stopped without sending signals."),
    timeout_seconds: float = typer.Option(15.0, "--timeout", min=0.0, help="Seconds to wait after SIGTERM."),
    no_kill: bool = typer.Option(False, "--no-kill", help="Do not escalate to SIGKILL after the timeout."),
) -> None:
    """Gracefully stop managed local model server processes."""
    from devflow.control_room import local_model_server

    try:
        payload = local_model_server.stop_local_model_servers(
            Path.cwd(),
            profile=profile,
            include_ollama=include_ollama,
            dry_run=dry_run,
            timeout_seconds=timeout_seconds,
            force_after_timeout=not no_kill,
        )
    except local_model_server.LocalModelServerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for line in local_model_server.render_local_model_server_lines(payload):
        typer.echo(line)


@local_model_app.command("start")
def local_model_start_command(
    profile: str = typer.Argument("hermes-qwen32", help="Local server profile to start."),
    json_output: bool = typer.Option(False, "--json", help="Print start result as JSON."),
    replace: bool = typer.Option(False, "--replace", help="Stop any managed local model server before starting this one."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the launch command without starting anything."),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host for the local model server."),
    port: int = typer.Option(8080, "--port", min=1, max=65535, help="Bind port for the local model server."),
    binary: str = typer.Option("llama-server", "--binary", help="llama-server executable path."),
    no_wait: bool = typer.Option(False, "--no-wait", help="Do not wait for /v1/models readiness."),
    ready_timeout_seconds: float = typer.Option(60.0, "--ready-timeout", min=0.0, help="Seconds to wait for readiness."),
) -> None:
    """Start a managed local model server."""
    from devflow.control_room import local_model_server

    try:
        payload = local_model_server.start_local_model_server(
            Path.cwd(),
            profile,
            host=host,
            port=port,
            binary=binary,
            replace=replace,
            dry_run=dry_run,
            wait_for_ready=not no_wait,
            ready_timeout_seconds=ready_timeout_seconds,
        )
    except local_model_server.LocalModelServerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for line in local_model_server.render_local_model_server_lines(payload):
        typer.echo(line)


@local_model_app.command("restart")
def local_model_restart_command(
    profile: str = typer.Argument("hermes-qwen32", help="Local server profile to restart."),
    json_output: bool = typer.Option(False, "--json", help="Print restart result as JSON."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the launch command without starting anything."),
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host for the local model server."),
    port: int = typer.Option(8080, "--port", min=1, max=65535, help="Bind port for the local model server."),
    binary: str = typer.Option("llama-server", "--binary", help="llama-server executable path."),
    no_wait: bool = typer.Option(False, "--no-wait", help="Do not wait for /v1/models readiness."),
    ready_timeout_seconds: float = typer.Option(60.0, "--ready-timeout", min=0.0, help="Seconds to wait for readiness."),
) -> None:
    """Stop the current managed local model server, then start the requested profile."""
    from devflow.control_room import local_model_server

    try:
        payload = local_model_server.restart_local_model_server(
            Path.cwd(),
            profile,
            host=host,
            port=port,
            binary=binary,
            dry_run=dry_run,
            wait_for_ready=not no_wait,
            ready_timeout_seconds=ready_timeout_seconds,
        )
    except local_model_server.LocalModelServerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    for line in local_model_server.render_local_model_server_lines(payload):
        typer.echo(line)
