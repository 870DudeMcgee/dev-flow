from __future__ import annotations

from pathlib import Path

import typer

from devflow.legacy.control_room import local_model_server
from devflow.legacy.control_room.local_ai_fleet import (
    LocalAICommandError,
    DEFAULT_SCOUT_CAPACITY_BASE_URL,
    DEFAULT_SCOUT_CAPACITY_CANDIDATES,
    DEFAULT_SCOUT_CAPACITY_MODEL,
    DEFAULT_SCOUT_CAPACITY_PASSES,
    DEFAULT_SCOUT_CAPACITY_TIMEOUT_SECONDS,
    DEFAULT_SCOUT_CAPACITY_WARMUP,
    DEFAULT_LOCAL_AI_PACKET_MAX_CHARS,
    build_local_ai_scout_capacity_result,
    build_local_ai_switch,
    build_local_ai_recommendation,
    build_local_ai_nightly_dry_run_plan,
    build_local_ai_snapshot,
    build_local_ai_scout_pack_result,
    build_local_ai_worker_wave_result,
    render_local_ai_scout_capacity_json,
    render_local_ai_nightly_dry_run_json,
    render_local_ai_scout_pack_json,
    render_local_ai_switch_json,
    render_local_ai_worker_wave_json,
    render_local_ai_recommendation_json,
    render_local_ai_recommendation_lines,
    render_local_ai_snapshot_json,
    render_local_ai_snapshot_lines,
    scout_openai_base_url,
)


local_ai_app = typer.Typer(help="Inspect the local AI fleet without mutating model state by default.")


@local_ai_app.command("snapshot")
def local_ai_snapshot_command(
    json_output: bool = typer.Option(False, "--json", help="Print the fleet snapshot as JSON."),
    include_ollama: bool = typer.Option(True, "--include-ollama/--no-include-ollama", help="Include Ollama processes."),
) -> None:
    """Show the current local AI fleet state and the next safe action."""
    payload = build_local_ai_snapshot(Path.cwd(), include_ollama=include_ollama)
    if json_output:
        typer.echo(render_local_ai_snapshot_json(payload))
        return
    for line in render_local_ai_snapshot_lines(payload):
        typer.echo(line)


@local_ai_app.command("recommend")
def local_ai_recommend_command(
    json_output: bool = typer.Option(False, "--json", help="Print the recommendation as JSON."),
    include_ollama: bool = typer.Option(True, "--include-ollama/--no-include-ollama", help="Include Ollama processes."),
) -> None:
    """Recommend the next safe local AI action from the current fleet snapshot."""
    payload = build_local_ai_recommendation(Path.cwd(), include_ollama=include_ollama)
    if json_output:
        typer.echo(render_local_ai_recommendation_json(payload))
        return
    for line in render_local_ai_recommendation_lines(payload):
        typer.echo(line)


@local_ai_app.command("stop-all")
def local_ai_stop_all_command(
    json_output: bool = typer.Option(False, "--json", help="Print the stop plan/result as JSON."),
    include_ollama: bool = typer.Option(False, "--include-ollama", help="Also include Ollama processes."),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Default to dry-run; use --apply to stop for real."),
    timeout_seconds: float = typer.Option(15.0, "--timeout", min=0.0, help="Seconds to wait after SIGTERM."),
    no_kill: bool = typer.Option(False, "--no-kill", help="Do not escalate to SIGKILL after the timeout."),
) -> None:
    """Preview or run a stop across the current local model fleet."""
    try:
        payload = local_model_server.stop_local_model_servers(
            Path.cwd(),
            include_ollama=include_ollama,
            dry_run=dry_run,
            timeout_seconds=timeout_seconds,
            force_after_timeout=not no_kill,
        )
    except local_model_server.LocalModelServerError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(render_local_ai_recommendation_json(payload))
        return
    for line in local_model_server.render_local_model_server_lines(payload):
        typer.echo(line)


@local_ai_app.command("nightly-dry-run")
def local_ai_nightly_dry_run_command(
    json_output: bool = typer.Option(False, "--json", help="Print the nightly dry-run plan as JSON."),
) -> None:
    """Build only a three-phase nightly dry-run local AI orchestration plan."""
    payload = build_local_ai_nightly_dry_run_plan(Path.cwd())
    if json_output:
        typer.echo(render_local_ai_nightly_dry_run_json(payload))
        return

    typer.echo(f"plan: {payload['plan_name']}")
    typer.echo(f"dry_run: {str(payload['dry_run']).lower()}")
    for phase in payload["phases"]:
        typer.echo(f"{phase['phase_id']}: {phase['title']}")
        for step in phase["steps"]:
            typer.echo(f"  - {step['summary']}: {step['command']}")


@local_ai_app.command("switch")
def local_ai_switch_command(
    role: str = typer.Argument(..., help="Role to switch to: supervisor or scout."),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Default to dry-run; use --apply to execute switch."),
    json_output: bool = typer.Option(False, "--json", help="Print the switch payload as JSON."),
) -> None:
    """Switch the active local AI role between supervisor and scout."""
    try:
        payload = build_local_ai_switch(Path.cwd(), role, dry_run=dry_run)
    except (LocalAICommandError, local_model_server.LocalModelServerError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(render_local_ai_switch_json(payload))
        return
    for line in (
        f"status: {payload.get('status')}",
        f"role: {payload.get('role')}",
        f"apply: {payload.get('apply')}",
    ):
        typer.echo(line)


@local_ai_app.command("run-scout-pack")
def local_ai_run_scout_pack_command(
    packet: str = typer.Argument(..., help="Path to a task packet JSON/YAML file."),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Default to dry-run; use --apply to run the local scout packet review."),
    max_packet_chars: int = typer.Option(200_000, "--max-packet-chars", help="Cap the rendered packet text before passing to local_packet_worker."),
    json_output: bool = typer.Option(False, "--json", help="Print dry-run/apply result as JSON."),
) -> None:
    """Run or preview a local scout packet read-only review."""
    try:
        payload = build_local_ai_scout_pack_result(
            Path.cwd(),
            Path(packet),
            dry_run=dry_run,
            max_packet_chars=max_packet_chars,
        )
    except LocalAICommandError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(render_local_ai_scout_pack_json(payload))
        return

    lines = [
        f"mode: {payload['mode']}",
        f"dry_run: {payload['dry_run']}",
        f"task_id: {payload['task_id']}",
        f"packet_path: {payload['packet_path']}",
        f"status: {payload['status']}",
        f"worker_profile: {payload['worker_profile']}",
    ]
    for key in ("evidence_dir", "response_path", "run_id", "error", "warning"):
        if payload.get(key):
            lines.append(f"{key}: {payload[key]}")
    typer.echo("\n".join(lines))

    if payload["status"] in {"failed"}:
        raise typer.Exit(code=1)


@local_ai_app.command("run-worker-wave")
def local_ai_run_worker_wave_command(
    wave_file: str = typer.Argument(..., help="Path to a packet wave file (JSON/YAML)."),
    concurrency: str = typer.Option(
        "auto",
        "--concurrency",
        help="Wave execution concurrency for packet review. Use 'auto' to use the latest passing scout-capacity result.",
    ),
    model: str = typer.Option(DEFAULT_SCOUT_CAPACITY_MODEL, "--model", help="Model for scout packets."),
    base_url: str = typer.Option(
        DEFAULT_SCOUT_CAPACITY_BASE_URL,
        "--base-url",
        help="Base URL for scout model calls.",
    ),
    timeout_seconds: float = typer.Option(
        DEFAULT_SCOUT_CAPACITY_TIMEOUT_SECONDS,
        "--timeout",
        min=0.0,
        help="Timeout for local scout packet review calls.",
    ),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Default to dry-run; use --apply to run all worker wave packets."),
    max_packet_chars: int = typer.Option(200_000, "--max-packet-chars", help="Cap rendered packet text for each packet."),
    json_output: bool = typer.Option(False, "--json", help="Print the wave result as JSON."),
) -> None:
    """Run or preview a full worker wave of packet-based scout tasks."""
    try:
        payload = build_local_ai_worker_wave_result(
            Path.cwd(),
            Path(wave_file),
            concurrency=concurrency,
            dry_run=dry_run,
            max_packet_chars=max_packet_chars,
            model=model,
            base_url=scout_openai_base_url(base_url),
            timeout_seconds=timeout_seconds,
        )
    except LocalAICommandError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(render_local_ai_worker_wave_json(payload))
        return

    typer.echo(f"mode: {payload['mode']}")
    typer.echo(f"dry_run: {payload['dry_run']}")
    typer.echo(f"status: {payload['status']}")
    typer.echo(f"wave_path: {payload['wave_path']}")
    typer.echo(f"concurrency: {payload['concurrency']}")
    typer.echo(f"results: {len(payload['results'])}")

    for result in payload["results"]:
        line = (
            f"  - {result.get('wave_index', '?')}: "
            f"{result.get('task_id', result.get('packet_path', 'unknown'))}"
            f" -> {result.get('status')}"
        )
        typer.echo(line)

    if payload["status"] != "success":
        raise typer.Exit(code=1)


@local_ai_app.command("scout-capacity")
def local_ai_scout_capacity_command(
    wave_file: str = typer.Argument(..., help="Path to a packet wave file (JSON/YAML)."),
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Default to dry-run; use --apply to measure and persist capacity."),
    model: str = typer.Option(DEFAULT_SCOUT_CAPACITY_MODEL, "--model", help="Model for all scout packets."),
    base_url: str = typer.Option(
        DEFAULT_SCOUT_CAPACITY_BASE_URL,
        "--base-url",
        help="Base URL for scout model calls.",
    ),
    candidates: list[int] = typer.Option(
        DEFAULT_SCOUT_CAPACITY_CANDIDATES,
        "--candidate",
        help="Candidate concurrency values to evaluate, repeated as needed.",
    ),
    passes: int = typer.Option(DEFAULT_SCOUT_CAPACITY_PASSES, "--passes", min=1, help="Number of measured attempts per candidate."),
    warmup: int = typer.Option(DEFAULT_SCOUT_CAPACITY_WARMUP, "--warmup", min=0, help="Number of warmup attempts before pass counting."),
    timeout_seconds: float = typer.Option(
        DEFAULT_SCOUT_CAPACITY_TIMEOUT_SECONDS,
        "--timeout",
        min=0.0,
        help="Timeout for local scout packet review calls.",
    ),
    max_packet_chars: int = typer.Option(
        DEFAULT_LOCAL_AI_PACKET_MAX_CHARS,
        "--max-packet-chars",
        help="Cap rendered packet text before calling local packet review.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the capacity payload as JSON."),
) -> None:
    """Measure or preview Gemma scout concurrency capacity for a wave."""
    try:
        payload = build_local_ai_scout_capacity_result(
            Path.cwd(),
            Path(wave_file),
            candidates=tuple(candidates),
            passes=passes,
            warmup=warmup,
            dry_run=dry_run,
            timeout_seconds=timeout_seconds,
            max_packet_chars=max_packet_chars,
            model=model,
            base_url=base_url,
        )
    except LocalAICommandError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(render_local_ai_scout_capacity_json(payload))
        return

    lines = (
        f"mode: {payload['mode']}",
        f"dry_run: {payload['dry_run']}",
        f"wave_path: {payload['wave_path']}",
        f"max_safe_concurrency: {payload['max_safe_concurrency']}",
    )
    for key in ("status", "error"):
        if payload.get(key) and key in payload:
            lines += (f"{key}: {payload[key]}",)
    typer.echo("\n".join(lines))
    if payload["status"] not in {"ready", "success"}:
        raise typer.Exit(code=1)
