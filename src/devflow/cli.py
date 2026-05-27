from __future__ import annotations

from pathlib import Path

import typer

from devflow.control_room.dashboard import run_dashboard
from devflow.control_room.service import create_task, doctor, get_task, init_control_room, list_tasks, run_shell_task, verify_task


app = typer.Typer(help="Dev-Flow local control room")
task_app = typer.Typer(help="Manage control-room tasks")
app.add_typer(task_app, name="task")


@app.command("init")
def init_command() -> None:
    """Initialize the local control-room runtime."""
    root = Path.cwd()
    init_control_room(root)
    typer.echo("Initialized .devflow control room")
    typer.echo("database: .devflow/devflow.db")
    typer.echo("config: .devflow/config.yaml")


@app.command("doctor")
def doctor_command() -> None:
    """Check local control-room runtime readiness."""
    root = Path.cwd()
    checks = doctor(root)
    failed = False
    for name, ok, detail in checks:
        marker = "ok" if ok else "missing"
        typer.echo(f"{marker}: {name} ({detail})")
        failed = failed or not ok
    if failed:
        raise typer.Exit(code=1)


@app.command("dashboard")
def dashboard_command(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the local browser dashboard."""
    run_dashboard(host=host, port=port)


@task_app.command("create")
def task_create(title: str) -> None:
    """Create a task and its artifact directory."""
    task = create_task(Path.cwd(), title)
    typer.echo(f"Created {task.id}: {task.title}")
    typer.echo(f"status: {task.status}")
    typer.echo(f"workspace: {task.workspace_path}")


@task_app.command("list")
def task_list() -> None:
    """List tasks from the control-room database."""
    tasks = list_tasks(Path.cwd())
    if not tasks:
        typer.echo("No tasks found.")
        return
    typer.echo(f"{'Task':<10} {'Status':<14} {'Verify':<10} {'Ready':<5} {'Worker':<8} Title")
    typer.echo("-" * 84)
    for task in tasks:
        ready = "yes" if task.merge_ready else "no"
        typer.echo(
            f"{task.id:<10} {task.status:<14} {(task.verification_status or ''):<10} "
            f"{ready:<5} {(task.worker_adapter or ''):<8} {task.title}"
        )


@task_app.command("show")
def task_show(task_id: str) -> None:
    """Show one task's status, logs, and artifacts."""
    try:
        task = get_task(Path.cwd(), task_id)
    except KeyError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"task: {task.id}")
    typer.echo(f"title: {task.title}")
    typer.echo(f"status: {task.status}")
    typer.echo(f"worker: {task.worker_adapter or ''}")
    typer.echo(f"workspace: {task.workspace_path or ''}")
    typer.echo(f"workspace_kind: {task.workspace_kind or ''}")
    typer.echo(f"branch_name: {task.branch_name or ''}")
    typer.echo(f"latest_log_line: {task.latest_log_line or ''}")
    typer.echo(f"log_path: {task.log_path or ''}")
    typer.echo(f"result_path: {task.result_path or ''}")
    typer.echo(f"verification_status: {task.verification_status or ''}")
    typer.echo(f"verification_command: {task.verification_command or ''}")
    typer.echo(f"verification_log_path: {task.verification_log_path or ''}")
    typer.echo(f"merge_ready: {'yes' if task.merge_ready else 'no'}")
    typer.echo(f"exit_code: {task.exit_code if task.exit_code is not None else ''}")


@task_app.command("run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def task_run(
    ctx: typer.Context,
    task_id: str,
    worker: str = typer.Option("shell", "--worker"),
    timeout_seconds: int = typer.Option(60, "--timeout-seconds"),
) -> None:
    """Run a task with a worker command after '--'."""
    if worker != "shell":
        typer.echo("Only the shell worker is available in the MVP.")
        raise typer.Exit(code=1)

    command = list(ctx.args)
    if command and command[0] == "--":
        command = command[1:]
    try:
        task = run_shell_task(Path.cwd(), task_id, command, timeout_seconds=timeout_seconds)
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"{task.id}: {task.status}")
    typer.echo(f"log_path: {task.log_path}")
    typer.echo(f"result_path: {task.result_path}")
    if task.latest_log_line:
        typer.echo(f"latest_log_line: {task.latest_log_line}")
    if task.status != "complete":
        raise typer.Exit(code=1)


@task_app.command("verify", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def task_verify(
    ctx: typer.Context,
    task_id: str,
    timeout_seconds: int = typer.Option(120, "--timeout-seconds"),
) -> None:
    """Run a verification command inside the task workspace."""
    command = list(ctx.args)
    if command and command[0] == "--":
        command = command[1:]
    try:
        task = verify_task(Path.cwd(), task_id, command, timeout_seconds=timeout_seconds)
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"{task.id}: verification {task.verification_status}")
    typer.echo(f"verification_log_path: {task.verification_log_path}")
    typer.echo(f"merge_ready: {'yes' if task.merge_ready else 'no'}")
    if task.latest_log_line:
        typer.echo(f"latest_log_line: {task.latest_log_line}")
    if task.verification_status != "passed":
        raise typer.Exit(code=1)


# Backward-compatible names for importers while the old CLI is retired.
def init_workspace() -> None:
    init_control_room(Path.cwd())


def status_workspace() -> None:
    task_list()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
