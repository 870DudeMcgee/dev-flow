from __future__ import annotations

from pathlib import Path
import json

import typer

from devflow.control_room.dashboard import run_dashboard
from devflow.control_room.service import (
    create_task,
    doctor,
    get_task,
    init_control_room,
    promotion_readiness_errors,
    run_shell_task,
    verify_task,
)
from devflow.control_room.status_projection import build_task_status_projection, list_task_status_projections
from devflow.control_room.supervisor import DEFAULT_WORKER_COMMAND, supervise_once
from devflow.control_room.token_context import write_context_packet
from devflow.control_room.worker_adapter import UnsupportedWorkerAdapter, get_worker_adapter


app = typer.Typer(help="Dev-Flow local control room")
task_app = typer.Typer(help="Manage control-room tasks")
app.add_typer(task_app, name="task")


@app.command("init")
def init_command() -> None:
    """Initialize the local control-room runtime."""
    root = Path.cwd()
    init_control_room(root)
    typer.echo("Initialized .devflow control room")
    typer.echo("config: .devflow/config.yaml")
    typer.echo("tasks: .devflow/tasks")
    typer.echo("workspaces: .devflow/workspaces")


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
def dashboard_command(refresh_seconds: int = typer.Option(0, "--refresh-seconds", min=0)) -> None:
    """Render the text-only terminal dashboard."""
    run_dashboard(refresh_seconds=refresh_seconds)


@app.command("supervise")
def supervise_command(
    once: bool = typer.Option(False, "--once"),
    task_id: str | None = typer.Option(None, "--task"),
    worker_command: str = typer.Option(DEFAULT_WORKER_COMMAND, "--worker-command"),
    timeout_seconds: int = typer.Option(60, "--timeout-seconds"),
) -> None:
    """Run one supervisor pass over runnable tasks."""
    if not once:
        typer.echo("supervise currently requires --once for this MVP slice.")
        raise typer.Exit(code=1)

    try:
        tasks = supervise_once(
            Path.cwd(),
            task_id=task_id,
            worker_command=worker_command,
            timeout_seconds=timeout_seconds,
        )
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    if not tasks:
        typer.echo("No runnable tasks.")
        return

    exit_code = 0
    for task in tasks:
        typer.echo(f"{task.id}: {task.status}")
        typer.echo(f"log_path: {task.log_path}")
        typer.echo(f"result_path: {task.result_path}")
        if task.latest_log_line:
            typer.echo(f"latest_log_line: {task.latest_log_line}")
        if task.status != "complete":
            exit_code = task.last_exit_code if task.last_exit_code is not None else 1
    if exit_code:
        raise typer.Exit(code=exit_code)


@app.command("context")
def context_command(
    task_description: str = typer.Argument(None, help="The task description to plan context for."),
    show: bool = typer.Option(False, "--show", help="Show the current token-context packet."),
) -> None:
    """Write or show a visible token-context packet for an IDE agent."""
    if show:
        packet_path = Path.cwd() / ".devflow" / "token-context" / "current.md"
        if not packet_path.exists():
            typer.echo(
                "No token-context packet found. Create one with:\n"
                '  devflow context "<task description>"'
            )
            return
        typer.echo(packet_path.read_text(encoding="utf-8"), nl=False)
        return

    if not task_description:
        typer.echo("Error: Missing argument 'TASK_DESCRIPTION' or option '--show'.", err=True)
        raise typer.Exit(code=1)

    plan = write_context_packet(Path.cwd(), task_description)
    typer.echo(f"Wrote {_relative(plan.repo_root, plan.packet_path)}")
    typer.echo(f"mode: {plan.context_mode}")
    typer.echo(f"recommended_tools: {', '.join(plan.recommended_tools)}")
    typer.echo(f"events: {_relative(plan.repo_root, plan.events_path)}")


@task_app.command("create")
def task_create(title: str) -> None:
    """Create a task and its artifact directory."""
    task = create_task(Path.cwd(), title)
    typer.echo(f"Created {task.id}: {task.title}")
    typer.echo(f"status: {task.status}")
    typer.echo(f"workspace: {task.workspace_path}")
    if task.workspace_dirty:
        typer.echo("Warning: Main worktree has uncommitted changes. Workspace contains dirty modifications.")


@task_app.command("list")
def task_list() -> None:
    """List tasks from the control-room task files."""
    projections = list_task_status_projections(Path.cwd())
    if not projections:
        typer.echo("No tasks found.")
        return
    typer.echo(f"{'Task':<10} {'Status':<20} {'Verify':<16} {'Updated':<25} Title")
    typer.echo("-" * 97)
    for projection in projections:
        task = projection.task
        typer.echo(
            f"{task.id:<10} {task.status:<20} {projection.verify_token:<16} "
            f"{task.updated_at.isoformat():<25} {task.title}"
        )


@task_app.command("show")
def task_show(task_id: str) -> None:
    """Show one task's status, logs, and artifacts."""
    try:
        task = get_task(Path.cwd(), task_id)
    except KeyError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    projection = build_task_status_projection(Path.cwd(), task_id, task=task)
    task_path = projection.task_path
    typer.echo(f"task: {task.id}")
    typer.echo(f"title: {task.title}")
    typer.echo(f"status: {task.status}")
    typer.echo(f"worker: {task.worker}")
    typer.echo(f"workspace: {task.workspace}")
    if task.branch_name:
        typer.echo(f"branch_name: {task.branch_name}")
    if task.workspace_commit:
        typer.echo(f"workspace_commit: {task.workspace_commit}")
    if task.workspace_dirty is not None:
        typer.echo(f"workspace_dirty: {str(task.workspace_dirty).lower()}")
    typer.echo(f"created_at: {task.created_at.isoformat()}")
    typer.echo(f"updated_at: {task.updated_at.isoformat()}")
    typer.echo(f"last_event: {task.last_event or ''}")
    typer.echo(f"latest_log_line: {task.latest_log_line or ''}")
    typer.echo(f"log_path: {task.log_path or ''}")
    typer.echo(f"result_path: {task.result_path or ''}")
    typer.echo(f"worker_command: {task.worker_command or ''}")

    typer.echo(f"verification_status: {projection.verification_status}")
    typer.echo(f"verification_command: {projection.verification_command or ''}")
    if projection.verification_exit_code is not None:
        typer.echo(f"verification_exit_code: {projection.verification_exit_code}")
    typer.echo(f"verification_log_path: {projection.verification_log_path or ''}")
    typer.echo(f"exit_code: {task.last_exit_code if task.last_exit_code is not None else ''}")
    typer.echo(f"suggested_next_action: {projection.suggested_next_action}")
    promoted_event = _get_latest_promoted_event(task_path)
    if promoted_event:
        typer.echo("promoted_changes:")
        added = promoted_event.get("added", [])
        modified = promoted_event.get("modified", [])
        deleted_applied = promoted_event.get("deleted_applied", [])
        if added:
            typer.echo(f"  added: {', '.join(added)}")
        if modified:
            typer.echo(f"  modified: {', '.join(modified)}")
        if deleted_applied:
            typer.echo(f"  deleted_applied: {', '.join(deleted_applied)}")
    packet_json = task_path / "packet.json"
    if packet_json.exists():
        rel_path = _relative(Path.cwd(), packet_json)
        typer.echo("packet_artifact: exists")
        typer.echo(f"packet_path: {rel_path}")
        typer.echo(f"packet_hint: run 'devflow task packet {task.id}' for the latest generated preview")
    else:
        typer.echo("packet_artifact: missing")
    if projection.merge_ready is not None:
        ready_str = "yes" if projection.merge_ready else "no"
        typer.echo(f"merge_ready: {ready_str}")
        if projection.readiness_reasons:
            typer.echo("readiness_reasons:")
            for reason in projection.readiness_reasons:
                typer.echo(f"  - {reason}")
    _echo_jsonl_tail("latest_events", task_path / "events.jsonl")
    _echo_jsonl_tail("open_questions", task_path / "questions.jsonl")
    _echo_result_summary(task_path / "result.md")


@task_app.command("packet")
def task_packet(task_id: str) -> None:
    """Build and print a task's TaskPacket as deterministic JSON."""
    try:
        from devflow.control_room.task_packet import build_task_packet
        packet = build_task_packet(task_id, root=Path.cwd())
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    packet_json = json.dumps(packet.model_dump(mode="json"), sort_keys=True, indent=2)
    typer.echo(packet_json)


@task_app.command("log")
def task_log(
    task_id: str,
    verify: bool = typer.Option(False, "--verify", help="Print the verification log instead."),
    tail: int | None = typer.Option(None, "--tail", min=1, help="Number of lines to tail."),
) -> None:
    """Print the logs for a task."""
    root = Path.cwd()
    try:
        task = get_task(root, task_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    log_name = "verify.log" if verify else "worker.log"
    log_file = root / ".devflow" / "tasks" / task.id / "logs" / log_name

    if not log_file.exists():
        typer.echo(f"Log file not found: {log_file}", err=True)
        raise typer.Exit(code=1)

    try:
        content = log_file.read_text(encoding="utf-8")
    except Exception as exc:
        typer.echo(f"Error reading log file: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    lines = content.splitlines()
    if tail is not None:
        lines = lines[-tail:]

    for line in lines:
        typer.echo(line)


@task_app.command("run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def task_run(
    ctx: typer.Context,
    task_id: str,
    worker: str = typer.Option("shell", "--worker"),
    shell_command: str | None = typer.Option(None, "--shell"),
    timeout_seconds: int = typer.Option(60, "--timeout-seconds"),
) -> None:
    """Run a task with a worker command after '--'."""
    try:
        get_worker_adapter(worker)
    except UnsupportedWorkerAdapter as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1)

    try:
        command = _shell_command_or_args(shell_command, list(ctx.args), "Shell worker")
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    try:
        task = run_shell_task(Path.cwd(), task_id, command, timeout_seconds=timeout_seconds, worker_adapter=worker)
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"{task.id}: {task.status}")
    typer.echo(f"log_path: {task.log_path}")
    typer.echo(f"result_path: {task.result_path}")
    if task.latest_log_line:
        typer.echo(f"latest_log_line: {task.latest_log_line}")
    if task.status != "complete":
        exit_code = task.last_exit_code if task.last_exit_code is not None else 1
        raise typer.Exit(code=exit_code)


@task_app.command("verify", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def task_verify(
    ctx: typer.Context,
    task_id: str,
    shell_command: str | None = typer.Option(None, "--shell"),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds"),
) -> None:
    """Run a verification command inside the task workspace."""
    try:
        command = _shell_command_or_args(shell_command, list(ctx.args), "Verification")
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    try:
        task = verify_task(Path.cwd(), task_id, command, timeout_seconds=timeout_seconds)
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"{task.id}: verification {task.verification_status}")
    typer.echo(f"verification_log_path: {task.verification_log_path}")
    if task.latest_log_line:
        typer.echo(f"latest_log_line: {task.latest_log_line}")
    if task.verification_status != "passed":
        exit_code = task.verification_exit_code if task.verification_exit_code is not None else 1
        raise typer.Exit(code=exit_code)


@task_app.command("promote-preview")
def task_promote_preview(task_id: str) -> None:
    """Preview changes that would be promoted from the isolated task workspace."""
    try:
        from devflow.control_room.service import preview_task_promotion
        res = preview_task_promotion(Path.cwd(), task_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    added = res["added"]
    modified = res["modified"]
    deleted = res["deleted"]
    diffs = res["diffs"]

    if not added and not modified and not deleted:
        typer.echo("No changes to promote")
        return

    if added:
        typer.echo("Added files:")
        for name in added:
            typer.echo(f"  - {name}")
        typer.echo()

    if modified:
        typer.echo("Modified files:")
        for name in modified:
            typer.echo(f"  - {name}")
        typer.echo()

    if deleted:
        typer.echo("Deleted files:")
        for name in deleted:
            typer.echo(f"  - {name}")
        typer.echo()

    typer.echo("--- Diffs ---")
    for name in sorted(diffs.keys()):
        diff_text = diffs[name]
        if diff_text:
            typer.echo(diff_text, nl=False)


@task_app.command("promote")
def task_promote(
    task_id: str,
    force: bool = typer.Option(False, "--force", help="Bypass dirty repository check."),
    apply_deletions: bool = typer.Option(False, "--apply-deletions", help="Apply file deletions to the main checkout."),
) -> None:
    """Promote verified changes from the isolated workspace to the main checkout."""
    try:
        from devflow.control_room.service import (
            format_promotion_refusal,
            get_task,
            main_checkout_has_uncommitted_changes,
            preview_task_promotion,
            promote_task,
            promotion_readiness_errors,
        )
        # 1. Safety check for dirty main checkout
        dirty = main_checkout_has_uncommitted_changes(Path.cwd())
        if dirty:
            if not force:
                typer.echo(
                    "Error: Main checkout has uncommitted changes. Please commit or stash them first, or use --force to bypass.",
                    err=True,
                )
                raise typer.Exit(code=1)
            else:
                typer.echo("Warning: Bypassing safety check for uncommitted changes in main checkout.")

        task = get_task(Path.cwd(), task_id)
        task_path = Path.cwd() / ".devflow" / "tasks" / task.id
        if promotion_readiness_errors(task, task_path):
            typer.echo(format_promotion_refusal(task, task_path), err=True)
            raise typer.Exit(code=1)

        res = preview_task_promotion(Path.cwd(), task_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    added = res["added"]
    modified = res["modified"]
    deleted = res["deleted"]
    diffs = res["diffs"]

    if not added and not modified and not deleted:
        typer.echo("No changes to promote")
        return

    if added:
        typer.echo("Added files:")
        for name in added:
            typer.echo(f"  - {name}")
        typer.echo()

    if modified:
        typer.echo("Modified files:")
        for name in modified:
            typer.echo(f"  - {name}")
        typer.echo()

    if deleted:
        typer.echo("Deleted files:")
        for name in deleted:
            typer.echo(f"  - {name}")
        typer.echo()

    typer.echo("--- Diffs ---")
    for name in sorted(diffs.keys()):
        diff_text = diffs[name]
        if diff_text:
            typer.echo(diff_text, nl=False)

    confirmed = typer.confirm("Promote these changes to the main checkout?", default=False)
    if not confirmed:
        typer.echo("Promotion aborted.")
        return

    try:
        promote_task(Path.cwd(), task_id, force=force, apply_deletions=apply_deletions)
    except Exception as exc:
        typer.echo(f"Error executing promotion: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Promotion complete.")
    if deleted:
        if apply_deletions:
            typer.echo(f"Applied deletions: {len(deleted)} file(s) removed.")
        else:
            typer.echo("Warning: Deletions are preview-only and were not applied (deletions are deferred). Use --apply-deletions to apply them.")


# Backward-compatible names for importers while the old CLI is retired.
def init_workspace() -> None:
    init_control_room(Path.cwd())


def status_workspace() -> None:
    task_list()


def main() -> None:
    app()


def _echo_jsonl_tail(label: str, path: Path, limit: int = 5) -> None:
    typer.echo(f"{label}:")
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        typer.echo("  none")
        return
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            typer.echo(f"  {line}")
            continue
        typer.echo(f"  {event.get('timestamp', '')} {event.get('event', '')}")


def _shell_command_or_args(shell_command: str | None, args: list[str], label: str) -> list[str]:
    if args and args[0] == "--":
        args = args[1:]
    if shell_command is not None and args:
        raise ValueError(f"{label} accepts either --shell or a command after '--', not both.")
    if shell_command is not None:
        if not shell_command.strip():
            raise ValueError(f"{label} --shell command cannot be empty.")
        return ["/bin/sh", "-c", shell_command]
    return args


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _echo_result_summary(path: Path) -> None:
    typer.echo("result_summary:")
    if not path.exists():
        typer.echo("  none")
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped not in {"## Summary", "## Status"}:
            typer.echo(f"  {stripped}")
            return
    typer.echo("  none")


def _get_latest_promoted_event(task_path: Path) -> dict[str, Any] | None:
    events_file = task_path / "events.jsonl"
    if not events_file.exists():
        return None
    latest_event = None
    try:
        with events_file.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if event.get("event") == "task_promoted":
                        latest_event = event
                except Exception:
                    pass
    except Exception:
        pass
    return latest_event


if __name__ == "__main__":
    main()
