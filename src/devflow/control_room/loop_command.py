from __future__ import annotations

import json
from pathlib import Path

import typer


loop_app = typer.Typer(help="Run durable DevFlow automation loops")


@loop_app.command("init")
def loop_init(
    loop_id: str = typer.Argument(..., help="Loop ID to create under .devflow/loops/."),
    template: str = typer.Option("goal-autopilot", "--template", help="Built-in loop template."),
) -> None:
    """Create a durable loop definition."""
    from devflow.control_room.loop_engine import LoopConfigError, init_loop_definition, loop_config_path

    try:
        definition = init_loop_definition(Path.cwd(), loop_id, template=template)
    except LoopConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Initialized loop {definition.loop_id}")
    typer.echo(f"template: {definition.template}")
    typer.echo(f"path: {loop_config_path(Path.cwd(), loop_id).as_posix()}")


@loop_app.command("show")
def loop_show(
    loop_id: str = typer.Argument(..., help="Loop ID to inspect."),
    json_output: bool = typer.Option(False, "--json", help="Print loop definition as JSON."),
) -> None:
    """Show one loop definition."""
    from devflow.control_room.loop_engine import LoopConfigError, load_loop_definition, render_loop_definition

    try:
        definition = load_loop_definition(Path.cwd(), loop_id)
    except LoopConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(definition.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        typer.echo(render_loop_definition(definition), nl=False)


@loop_app.command("list")
def loop_list(
    json_output: bool = typer.Option(False, "--json", help="Print loop IDs as JSON."),
) -> None:
    """List durable loop definitions."""
    from devflow.control_room.loop_engine import list_loop_ids

    loops = list_loop_ids(Path.cwd())
    if json_output:
        typer.echo(json.dumps({"loops": loops}, indent=2, sort_keys=True))
        return
    if not loops:
        typer.echo("No loops configured.")
        return
    for loop_id in loops:
        typer.echo(loop_id)


@loop_app.command("spine-fixture")
def loop_spine_fixture(
    target_file: str = typer.Option(
        "src/devflow/loop/models.py",
        "--target-file",
        help="Existing repo file used to ground the deterministic fixture.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Print harness report as JSON."),
) -> None:
    """Run the deterministic V2 loop-spine fixture harness."""
    from devflow.loop.e2e_harness import run_e2e_loop_harness

    try:
        report = run_e2e_loop_harness(Path.cwd(), target_file=target_file)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
        return

    typer.echo(f"run_id: {report.run_id}")
    typer.echo(f"final_stage: {report.final_stage.value}")
    typer.echo("stage_chain: " + " -> ".join(stage.value for stage in report.observed_stage_chain))


@loop_app.command("run")
def loop_run(
    loop_id: str = typer.Argument(..., help="Loop ID to run."),
    max_iterations: int | None = typer.Option(None, "--max-iterations", min=1, help="Override loop max iterations."),
    max_parallel: int | None = typer.Option(None, "--max-parallel", min=1, help="Override loop max parallel workers."),
    worker_timeout_seconds: int | None = typer.Option(
        None,
        "--worker-timeout-seconds",
        min=1,
        help="Override per-worker/per-verification timeout.",
    ),
    allow_workers: bool = typer.Option(False, "--allow-workers", help="Allow projected shell-worker batches."),
    allow_verify: bool = typer.Option(False, "--allow-verify", help="Allow projected verification batches."),
    allow_promote: bool = typer.Option(False, "--allow-promote", help="Allow gated promotion preview and promotion."),
    json_output: bool = typer.Option(False, "--json", help="Print loop run evidence summary as JSON."),
) -> None:
    """Run a durable DevFlow automation loop with explicit automation grants."""
    from devflow.control_room.loop_engine import LoopConfigError, LoopRunError, render_loop_run, run_loop

    try:
        run = run_loop(
            Path.cwd(),
            loop_id,
            max_iterations=max_iterations,
            max_parallel=max_parallel,
            worker_timeout_seconds=worker_timeout_seconds,
            allow_workers=allow_workers,
            allow_verify=allow_verify,
            allow_promote=allow_promote,
        )
    except (LoopConfigError, LoopRunError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(run.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        typer.echo(render_loop_run(run), nl=False)
    if run.status != "completed":
        raise typer.Exit(code=2)
