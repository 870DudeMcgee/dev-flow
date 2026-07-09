from __future__ import annotations

from pathlib import Path

import typer


operating_layer_app = typer.Typer(help="Local operating-layer UI and supervisor-safe controls")


@operating_layer_app.command("snapshot")
def operating_layer_snapshot_command(
    json_output: bool = typer.Option(False, "--json", help="Print the operating-layer snapshot as JSON."),
) -> None:
    """Render the local operating-layer snapshot."""
    from devflow.legacy.control_room.operating_layer import (
        build_operating_layer_snapshot,
        render_operating_layer_snapshot_json,
    )

    if json_output:
        typer.echo(render_operating_layer_snapshot_json(Path.cwd()), nl=False)
        return

    snapshot = build_operating_layer_snapshot(Path.cwd())
    typer.echo("Dev-Flow Operating Layer")
    typer.echo(f"Project: {snapshot.project.root}")
    typer.echo(f"Tasks: {snapshot.health.total_tasks} total, {snapshot.health.active_tasks} active")
    typer.echo(f"Goals: {len(snapshot.goals)}")
    typer.echo(f"Next: {snapshot.next_action.command or 'None'}")


@operating_layer_app.command("serve")
def operating_layer_serve_command(
    host: str = typer.Option("127.0.0.1", "--host", help="Host for the local UI server."),
    port: int = typer.Option(8765, "--port", min=0, help="Port for the local UI server. Use 0 for an ephemeral port."),
    open_browser: bool = typer.Option(False, "--open", help="Open the local UI in the default browser."),
) -> None:
    """Serve the local operating-layer UI and supervisor-safe controls."""
    from devflow.legacy.control_room.operating_layer_server import run_operating_layer_server

    def _ready(server: object) -> None:
        address = getattr(server, "server_address")
        typer.echo(f"Dev-Flow Operating Layer: http://{address[0]}:{address[1]}")
        typer.echo("Control layer active. Press Ctrl+C to stop.")

    try:
        run_operating_layer_server(
            Path.cwd(),
            host=host,
            port=port,
            open_browser=open_browser,
            ready_callback=_ready,
        )
    except KeyboardInterrupt:
        typer.echo("Stopped Dev-Flow Operating Layer")


@operating_layer_app.command("health")
def operating_layer_health_command(
    host: str = typer.Option("127.0.0.1", "--host", help="Host of the running UI server."),
    port: int = typer.Option(8765, "--port", min=1, max=65535, help="Port of the running UI server."),
) -> None:
    """Probe a running operating-layer server's real data path (/healthz + /api/snapshot)."""
    from devflow.legacy.control_room.operating_layer_server import check_server_health, find_listening_pids

    pids = find_listening_pids(port)
    health = check_server_health(host, port)
    typer.echo(f"server: http://{host}:{port}")
    typer.echo(f"listening pids: {', '.join(str(p) for p in pids) if pids else 'none'}")
    typer.echo(f"healthz: {'ok' if health['healthz_ok'] else 'FAIL'}")
    typer.echo(
        f"snapshot: {'ok' if health['snapshot_ok'] else 'FAIL'} ({health['snapshot_bytes']} bytes)"
    )
    if health["detail"]:
        typer.echo(f"detail: {health['detail']}")
    if not health["overall_ok"]:
        if pids:
            typer.echo("hint: server is up but its data path is broken - run 'devflow operating-layer restart'")
        raise typer.Exit(code=1)


@operating_layer_app.command("restart")
def operating_layer_restart_command(
    host: str = typer.Option("127.0.0.1", "--host", help="Host for the local UI server."),
    port: int = typer.Option(8765, "--port", min=0, help="Port for the local UI server. Use 0 for an ephemeral port."),
    open_browser: bool = typer.Option(False, "--open", help="Open the local UI in the default browser."),
) -> None:
    """Stop any stale server on the port, then serve a fresh operating-layer UI.

    Kills only the process(es) listening on the target TCP port - never unrelated
    work. This is the fix for the stale-server trap where the browser shows a
    frozen/empty control room because an old process is serving outdated code.
    """
    from devflow.legacy.control_room.operating_layer_server import (
        run_operating_layer_server,
        stop_listening_processes,
    )

    if port:
        stopped = stop_listening_processes(port)
        if stopped:
            typer.echo(f"stopped stale server pid(s): {', '.join(str(p) for p in stopped)}")
        else:
            typer.echo(f"no existing server found on port {port}")

    def _ready(server: object) -> None:
        address = getattr(server, "server_address")
        typer.echo(f"Dev-Flow Operating Layer: http://{address[0]}:{address[1]}")
        typer.echo("Control layer active. Press Ctrl+C to stop.")

    try:
        run_operating_layer_server(
            Path.cwd(),
            host=host,
            port=port,
            open_browser=open_browser,
            ready_callback=_ready,
        )
    except KeyboardInterrupt:
        typer.echo("Stopped Dev-Flow Operating Layer")


@operating_layer_app.command("install-service")
def operating_layer_install_service_command(
    host: str = typer.Option("127.0.0.1", "--host", help="Host for the login service UI server."),
    port: int = typer.Option(8765, "--port", min=1, max=65535, help="Port for the login service UI server."),
    label: str = typer.Option("com.devflow.operating-layer", "--label", help="macOS LaunchAgent label."),
    launch_agents_dir: Path | None = typer.Option(None, "--launch-agents-dir", help="LaunchAgents directory override."),
    logs_dir: Path | None = typer.Option(None, "--logs-dir", help="Service log directory override."),
    python_executable: Path | None = typer.Option(None, "--python", help="Python executable for launchd."),
    load: bool = typer.Option(False, "--load", help="Load the LaunchAgent immediately with launchctl."),
    open_browser: bool = typer.Option(False, "--open", help="Open the browser when launchd starts the service."),
    allow_network_host: bool = typer.Option(
        False,
        "--allow-network-host",
        help="Allow installing a service bound to a non-loopback host for a trusted private network.",
    ),
) -> None:
    """Install a macOS LaunchAgent for the local operating-layer UI."""
    from devflow.legacy.control_room.operating_layer_service import install_operating_layer_launch_agent

    try:
        result = install_operating_layer_launch_agent(
            Path.cwd(),
            host=host,
            port=port,
            label=label,
            launch_agents_dir=launch_agents_dir,
            logs_dir=logs_dir,
            python_executable=python_executable,
            load=load,
            open_browser=open_browser,
            allow_network_host=allow_network_host,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Installed LaunchAgent: {result.plist_path}")
    typer.echo(f"Label: {result.label}")
    typer.echo(f"URL: {result.url}")
    typer.echo("Starts at login: yes")
    typer.echo(f"Loaded now: {'yes' if result.loaded else 'no'}")
    typer.echo(f"Stdout log: {result.stdout_path}")
    typer.echo(f"Stderr log: {result.stderr_path}")
    if not result.loaded:
        typer.echo("To start now, rerun with --load or log out and back in.")


@operating_layer_app.command("visual-qa")
def operating_layer_visual_qa_command(
    json_output: bool = typer.Option(False, "--json", help="Print the visual QA plan as JSON."),
    base_url: str = typer.Option("http://127.0.0.1:8765", "--base-url", help="Operating-layer URL to test."),
    write_current: bool = typer.Option(False, "--write-current", help="Write current SVG image fallback artifacts."),
    update_baseline: bool = typer.Option(False, "--update-baseline", help="Update SVG image fallback baselines."),
) -> None:
    """Render the operating-layer visual-regression QA plan."""
    from devflow.legacy.control_room.operating_layer_visual_qa import (
        build_visual_qa_plan,
        render_visual_qa_plan,
        render_visual_qa_plan_json,
        write_visual_qa_image_fallbacks,
    )

    if write_current or update_baseline:
        plan = build_visual_qa_plan(Path.cwd(), base_url=base_url)
        plan["image_fallback"] = write_visual_qa_image_fallbacks(
            Path.cwd(),
            base_url=base_url,
            update_baseline=update_baseline,
        )
        if json_output:
            import json

            typer.echo(json.dumps(plan, indent=2, sort_keys=True) + "\n", nl=False)
            return
        typer.echo(render_visual_qa_plan(Path.cwd(), base_url=base_url), nl=False)
        typer.echo(f"Image fallback: {plan['image_fallback']['status']}")
        return

    if json_output:
        typer.echo(render_visual_qa_plan_json(Path.cwd(), base_url=base_url), nl=False)
        return

    typer.echo(render_visual_qa_plan(Path.cwd(), base_url=base_url), nl=False)
