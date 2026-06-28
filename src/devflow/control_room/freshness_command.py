import json
from pathlib import Path

import typer


freshness_app = typer.Typer(help="Detect stale goal/task/document guidance")


@freshness_app.command("loop")
def freshness_loop(
    json_output: bool = typer.Option(False, "--json", help="Print the loop report as JSON."),
    all_projects: bool = typer.Option(False, "--all-projects", help="Run the loop across every registered project."),
) -> None:
    """Run one freshness-control loop iteration and update derived state."""
    if all_projects:
        from devflow.control_room import multi_project_freshness

        report = multi_project_freshness.run_multi_project_freshness_loop()
        if json_output:
            typer.echo(json.dumps(report.model_dump(), indent=2, sort_keys=True))
        else:
            typer.echo(multi_project_freshness.render_multi_project_freshness_report(report), nl=False)
        if report.status == "needs_human_decision":
            raise typer.Exit(code=2)
        return

    from devflow.control_room import freshness

    report = freshness.run_freshness_loop(Path.cwd())
    if json_output:
        typer.echo(json.dumps(report.model_dump(), indent=2, sort_keys=True))
    else:
        typer.echo(freshness.render_freshness_report(report), nl=False)
    if report.status == "needs_human_decision":
        raise typer.Exit(code=2)


@freshness_app.command("verify-batch")
def freshness_verify_batch(
    goal_id: str = typer.Argument(..., help="Goal ID containing the projected verification batch."),
    batch_id: str = typer.Argument(..., help="Projected verification batch ID, e.g. VB-0001."),
    max_parallel: int = typer.Option(4, "--max-parallel", min=1, help="Maximum task verification processes to run at once."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1, help="Timeout for each task verification process."),
    json_output: bool = typer.Option(False, "--json", help="Print the batch run report as JSON."),
) -> None:
    """Run one currently projected freshness verification batch."""
    from devflow.control_room import parallel_verification

    try:
        run = parallel_verification.run_projected_verification_batch(
            Path.cwd(), goal_id, batch_id, max_parallel=max_parallel, timeout_seconds=timeout_seconds
        )
    except parallel_verification.VerificationBatchSelectionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(run.model_dump(), indent=2, sort_keys=True))
    else:
        typer.echo(parallel_verification.render_parallel_verification_run(run), nl=False)
    if run.status == "failed":
        raise typer.Exit(code=1)


@freshness_app.command("worker-batch")
def freshness_worker_batch(
    goal_id: str = typer.Argument(..., help="Goal ID containing the projected worker batch."),
    batch_id: str = typer.Argument(..., help="Projected worker batch ID, e.g. WB-0001."),
    max_parallel: int = typer.Option(4, "--max-parallel", min=1, help="Maximum task worker processes to run at once."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1, help="Timeout for each task worker process."),
    json_output: bool = typer.Option(False, "--json", help="Print the worker run report as JSON."),
) -> None:
    """Run one currently projected shell-worker batch."""
    from devflow.control_room import parallel_worker

    try:
        run = parallel_worker.run_projected_worker_batch(
            Path.cwd(), goal_id, batch_id, max_parallel=max_parallel, timeout_seconds=timeout_seconds
        )
    except parallel_worker.WorkerBatchSelectionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(run.model_dump(), indent=2, sort_keys=True))
    else:
        typer.echo(parallel_worker.render_parallel_worker_run(run), nl=False)
    if run.status == "failed":
        raise typer.Exit(code=1)


@freshness_app.command("create-batch")
def freshness_create_batch(
    goal_id: str = typer.Argument(..., help="Goal ID containing the projected parallel task batch."),
    batch_id: str = typer.Argument(..., help="Projected parallel task batch ID, e.g. PB-0001."),
    json_output: bool = typer.Option(False, "--json", help="Print the task creation run report as JSON."),
) -> None:
    """Create tasks for one currently projected parallel-safe batch."""
    from devflow.control_room import parallel_task_creation

    try:
        run = parallel_task_creation.run_projected_task_creation_batch(Path.cwd(), goal_id, batch_id)
    except parallel_task_creation.ParallelTaskCreationSelectionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(run.model_dump(), indent=2, sort_keys=True))
    else:
        typer.echo(parallel_task_creation.render_parallel_task_creation_run(run), nl=False)


@freshness_app.command("run")
def freshness_run(
    max_iterations: int = typer.Option(3, "--max-iterations", min=1, help="Maximum bounded loop iterations."),
    all_projects: bool = typer.Option(False, "--all-projects", help="Run bounded read-mostly loop iterations across registered projects."),
    create_tasks: bool = typer.Option(
        False,
        "--create-tasks",
        help="Explicitly create tasks from the first projected parallel-safe batch in each safe iteration.",
    ),
    execute_verification: bool = typer.Option(
        False,
        "--execute-verification",
        help="Explicitly run the first projected verification batch in each safe iteration.",
    ),
    execute_workers: bool = typer.Option(
        False,
        "--execute-workers",
        help="Explicitly run the first projected shell-worker batch in each safe iteration.",
    ),
    max_parallel: int = typer.Option(4, "--max-parallel", min=1, help="Maximum task worker or verification processes to run at once."),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds", min=1, help="Timeout for each task worker or verification process."),
    json_output: bool = typer.Option(False, "--json", help="Print the control run report as JSON."),
) -> None:
    """Run bounded PLC-style freshness iterations."""
    from devflow.control_room import freshness_runner

    if all_projects:
        if create_tasks or execute_workers or execute_verification:
            typer.echo("Error: --all-projects currently supports read-mostly bounded runs only.", err=True)
            raise typer.Exit(code=1)
        run = freshness_runner.run_bounded_multi_project_freshness_control(max_iterations=max_iterations)
        if json_output:
            typer.echo(json.dumps(run.model_dump(), indent=2, sort_keys=True))
        else:
            typer.echo(freshness_runner.render_bounded_multi_project_freshness_run(run), nl=False)
        if run.status == "needs_human_decision":
            raise typer.Exit(code=2)
        return

    run = freshness_runner.run_bounded_freshness_control(
        Path.cwd(),
        max_iterations=max_iterations,
        create_tasks=create_tasks,
        execute_workers=execute_workers,
        execute_verification=execute_verification,
        max_parallel=max_parallel,
        timeout_seconds=timeout_seconds,
    )
    if json_output:
        typer.echo(json.dumps(run.model_dump(), indent=2, sort_keys=True))
    else:
        typer.echo(freshness_runner.render_bounded_freshness_run(run), nl=False)
    if run.status in {"needs_human_decision", "worker_failed", "verification_failed"}:
        raise typer.Exit(code=2)
