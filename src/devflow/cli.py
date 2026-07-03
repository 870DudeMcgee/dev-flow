from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import typer

from devflow.control_room.task_command_policy import (
    experimental_command_hidden,
    experimental_refusal_lines,
)


def _enforce_experimental(cmd_name: str) -> None:
    lines = experimental_refusal_lines(cmd_name) if experimental_command_hidden() else []
    if lines:
        for line in lines:
            typer.echo(line, err=True)
        raise typer.Exit(code=1)


from devflow.control_room.dashboard import (
    run_dashboard,
    render_dashboard_json,
    render_multi_project_dashboard,
    render_multi_project_dashboard_json,
    render_next_action,
    render_task_history,
)
from devflow.control_room.service import (
    create_task,
    doctor,
    get_task,
    init_control_room,
    run_local_model_task,
    verify_task,
)
from devflow.control_room.task_apply_patch_command import (
    TaskApplyPatchCommandError,
    build_task_apply_patch_result,
    render_task_apply_patch_result,
)
from devflow.control_room.task_auto_run_command import run_task_auto_run_command
from devflow.control_room.task_patch_gate_command import (
    TaskPatchGateCommandError,
    build_task_patch_dry_run_result,
    build_task_patch_review_result,
    render_task_patch_dry_run_lines,
    render_task_patch_review_lines,
)
from devflow.control_room.task_closure import (
    TaskClosureError,
    cleanup_task as cleanup_closed_task,
    close_task,
)
from devflow.control_room.task_evidence_summary import (
    TaskEvidenceSummaryError,
    build_task_evidence_summary,
    render_task_evidence_summary,
)
from devflow.control_room.task_show_summary import (
    TaskShowSummaryError,
    build_task_show_summary,
    render_task_show_summary,
)
from devflow.control_room.task_artifact_open import (
    TaskArtifactOpenError,
    open_task_artifact,
    render_task_open_candidates,
    select_task_open_artifact,
)
from devflow.control_room.task_pruning import TaskPruneError, prune_closed_tasks
from devflow.control_room.reconciliation import build_reconciliation_report

from devflow.control_room.status_projection import list_task_status_projections
from devflow.control_room.models import TaskRecord
from devflow.control_room.supervisor import DEFAULT_WORKER_COMMAND, supervise_once, supervise_poll
from devflow.control_room.token_context import write_context_packet
from devflow.control_room.proposal_normalizer import normalize_proposal
from devflow.control_room.git_worktree import (
    GitWorktreeError,
    archive_devflow_branch,
    cleanup_task_git_resources,
    list_devflow_branches,
    list_devflow_worktrees,
    prune_orphan_worktrees,
)
from devflow.control_room.task_promotion_command import (
    TaskPromotionCommandError,
    build_task_promotion_preview_view,
    build_task_promotion_run_view,
    execute_task_promotion_run,
)
from devflow.control_room.task_routing_command import (
    TaskRoutingCommandError,
    build_task_routing_result,
    render_task_routing_json,
    render_task_routing_lines,
)
from devflow.control_room.task_run_command import (
    TaskRunCommandError,
    render_task_run_lines,
    run_task_command,
)
from devflow.control_room.task_scorecard_command import (
    TaskScorecardCommandError,
    build_task_scorecard_result,
    render_task_scorecard_json,
    render_task_scorecard_lines,
)
from devflow.control_room.architecture_command import architecture_app, architecture_audit_command  # noqa: F401
from devflow.control_room.builder_judge_command import builder_judge_app
from devflow.control_room.dogfood_command import dogfood_app
from devflow.control_room.freshness_command import (  # noqa: F401
    freshness_app, freshness_create_batch, freshness_loop, freshness_run,
    freshness_verify_batch, freshness_worker_batch,
)
from devflow.control_room.goal_command import goal_app
from devflow.control_room.idea_command import idea_app
from devflow.control_room.local_ai_command import local_ai_app
from devflow.control_room.local_model_command import local_model_app
from devflow.control_room.loop_command import loop_app
from devflow.control_room.agent_command import agent_app
from devflow.control_room.maintenance_command import maintenance_app
from devflow.control_room.operating_layer_command import operating_layer_app
from devflow.control_room.project_command import project_app
from devflow.control_room.training_command import training_app
from devflow.control_room.question_command import (  # noqa: F401
    question_answer, question_app, question_list, question_resolve, question_show,
)
from devflow.control_room.scheduler_command import scheduler_app, scheduler_retry, scheduler_status  # noqa: F401
from devflow.control_room.devmode_bridge import detect_devmode, render_devmode_status
from devflow.control_room.git_state import GitStateError, push_main, render_git_status, sync_main
from devflow.control_room.qwopus_evidence import write_qwopus_escalation_packet
from devflow.control_room.review_capsule import export_review_capsule_markdown, render_review_capsule
from devflow.control_room.review_readiness import (
    build_review_readiness_projection,
    render_review_readiness,
    summarize_review_readiness,
)
from devflow.control_room.supervisor_surface import (
    render_control_room_status,
    render_supervisor_command_classification,
    render_supervisor_packet,
    render_supervisor_policy,
    render_task_next_action,
    render_task_review,
)
from devflow.control_room.telegram_routing import render_telegram_route
from devflow.control_room.hermes_readiness import render_hermes_imessage_check
from devflow.control_room.hermes_profiles_command import hermes_profiles_app
from devflow.control_room.project_registry import (
    ProjectRootResolution,
    ProjectRegistryError,
    project_task_ref,
    resolve_project_root,
)
from devflow.control_room.paths import relative_path


app = typer.Typer(help="Dev-Flow local control room")
task_app = typer.Typer(help="Manage control-room tasks")
worktree_app = typer.Typer(help="Inspect and clean Dev-Flow Git worktrees")
branch_app = typer.Typer(help="Inspect and archive Dev-Flow Git branches")
git_app = typer.Typer(help="Inspect guarded Git state")
worker_app = typer.Typer(help="Validate worker outcome metadata")
knowledge_app = typer.Typer(help="Capture and curate reusable local knowledge")
release_app = typer.Typer(help="Inspect milestone release-readiness gates")
supervisor_app = typer.Typer(help="Inspect and operate Dev-Flow through supervisor-safe read-only surfaces")
hermes_app = typer.Typer(help="Inspect Hermes operator integration readiness")
map_app = typer.Typer(help="Project Code Map orientation layer (Milestone 11)")
app.add_typer(task_app, name="task")
app.add_typer(agent_app, name="agent")
app.add_typer(worktree_app, name="worktree")
app.add_typer(branch_app, name="branch")
app.add_typer(git_app, name="git")
app.add_typer(goal_app, name="goal")
app.add_typer(worker_app, name="worker")
app.add_typer(knowledge_app, name="knowledge")
app.add_typer(idea_app, name="idea")
app.add_typer(dogfood_app, name="dogfood")
app.add_typer(maintenance_app, name="maintenance")
app.add_typer(release_app, name="release")
app.add_typer(supervisor_app, name="supervisor")
app.add_typer(hermes_app, name="hermes")
hermes_app.add_typer(hermes_profiles_app, name="profiles")
app.add_typer(project_app, name="project")
app.add_typer(map_app, name="map")
app.add_typer(freshness_app, name="freshness")
app.add_typer(scheduler_app, name="scheduler")
app.add_typer(question_app, name="question")
app.add_typer(operating_layer_app, name="operating-layer")
app.add_typer(local_ai_app, name="local-ai")
app.add_typer(local_model_app, name="local-model")
app.add_typer(loop_app, name="loop")
app.add_typer(training_app, name="training")
app.add_typer(builder_judge_app, name="builder-judge")
app.add_typer(architecture_app, name="architecture")


TRUSTED_LOCAL_WARNING = "Security: shell execution is path-isolated, not sandboxed; run only trusted local commands."


def _resolve_task_project_root(project: str | None) -> ProjectRootResolution:
    try:
        return resolve_project_root(Path.cwd(), project)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("init")
def init_command() -> None:
    """Initialize the local control-room runtime."""
    root = Path.cwd()
    init_control_room(root)
    typer.echo("Initialized .devflow control room")
    typer.echo("config: .devflow/config.yaml")
    typer.echo("tasks: .devflow/tasks")
    typer.echo("workspaces: .devflow/workspaces")
    typer.echo(TRUSTED_LOCAL_WARNING)


@app.command("doctor")
def doctor_command(
    strict: bool = typer.Option(False, "--strict", help="Enforce strict production readiness checks."),
    repair: bool = typer.Option(
        False,
        "--repair",
        help="Auto-fix the macOS hidden flag on the venv before checking (non-destructive).",
    ),
    provision: bool = typer.Option(False, "--provision", help="Inspect local model readiness and onboarding commands."),
    json_output: bool = typer.Option(False, "--json", help="Print local model readiness payload as JSON with --provision."),
    apply_changes: bool = typer.Option(
        False,
        "--apply",
        help="Run supported local model onboarding commands from --provision and write command evidence.",
    ),
) -> None:
    """Check local control-room runtime readiness."""
    root = Path.cwd()
    if json_output and not provision:
        typer.echo("Error: doctor --json is only supported with --provision.", err=True)
        raise typer.Exit(code=1)
    if apply_changes and not provision:
        typer.echo("Error: doctor --apply requires --provision.", err=True)
        raise typer.Exit(code=1)
    if json_output and apply_changes:
        typer.echo("Error: doctor --provision --json is read-only and cannot be combined with --apply.", err=True)
        raise typer.Exit(code=1)
    if provision:
        from devflow.control_room.local_model_readiness import (
            LocalModelReadinessError,
            apply_local_model_readiness_plan,
            build_local_model_readiness_plan,
            render_local_model_readiness_apply_result,
            render_local_model_readiness_plan,
        )

        try:
            if apply_changes:
                result = apply_local_model_readiness_plan(root)
                for line in render_local_model_readiness_apply_result(result):
                    typer.echo(line)
                if result["status"] == "failed":
                    raise typer.Exit(code=1)
                return
            plan = build_local_model_readiness_plan(root)
        except LocalModelReadinessError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        if json_output:
            typer.echo(json.dumps(plan, indent=2, sort_keys=True))
            return
        for line in render_local_model_readiness_plan(plan):
            typer.echo(line)
        return
    if repair:
        from devflow.control_room.control_room_doctor import repair_macos_path_hygiene

        fixed = repair_macos_path_hygiene(root)
        if fixed:
            for path in fixed:
                typer.echo(f"repaired: cleared macOS hidden flag on {path}")
        else:
            typer.echo("repair: no macOS hidden flags found to clear")
    if strict:
        typer.echo(TRUSTED_LOCAL_WARNING)
    checks = doctor(root, strict=strict)
    failed = False
    for name, ok, detail in checks:
        marker = "ok" if ok else "FAIL"
        typer.echo(f"{marker}: {name} ({detail})")
        failed = failed or not ok
    if failed:
        raise typer.Exit(code=1)


@app.command("reconcile")
def reconcile_command(
    json_output: bool = typer.Option(False, "--json", help="Print the report as JSON."),
    task_id: str | None = typer.Option(None, "--task", help="Limit the report to one task id."),
) -> None:
    """Report crash/interruption evidence without changing task artifacts."""
    report = build_reconciliation_report(Path.cwd(), task_id=task_id)
    if json_output:
        typer.echo(json.dumps(report, sort_keys=True, indent=2))
    else:
        _echo_reconciliation_report(report)
    if report["status"] != "ok":
        raise typer.Exit(code=1)


@app.command("dashboard")
def dashboard_command(
    refresh_seconds: int = typer.Option(0, "--refresh-seconds", min=0),
    json_output: bool = typer.Option(False, "--json", help="Print dashboard state as JSON."),
    all_projects: bool = typer.Option(False, "--all-projects", help="Show all registered projects."),
) -> None:
    """Render the terminal Control Room Dashboard."""
    if all_projects:
        if refresh_seconds > 0:
            typer.echo("Error: --all-projects cannot be used with --refresh-seconds.", err=True)
            raise typer.Exit(code=1)
        if json_output:
            typer.echo(render_multi_project_dashboard_json(), nl=False)
        else:
            typer.echo(render_multi_project_dashboard(), nl=False)
        return
    if json_output:
        if refresh_seconds > 0:
            typer.echo("Error: --json cannot be used with --refresh-seconds.", err=True)
            raise typer.Exit(code=1)
        typer.echo(render_dashboard_json(Path.cwd()), nl=False)
    else:
        run_dashboard(refresh_seconds=refresh_seconds)


@app.command("status")
def status_command(
    json_output: bool = typer.Option(False, "--json", help="Print supervisor-safe control-room status as JSON."),
    all_projects: bool = typer.Option(False, "--all-projects", help="Show all registered projects."),
) -> None:
    """Render the terminal Control Room Dashboard alias."""
    if all_projects:
        if json_output:
            typer.echo(render_multi_project_dashboard_json(), nl=False)
        else:
            typer.echo(render_multi_project_dashboard(), nl=False)
        return
    if json_output:
        typer.echo(render_control_room_status(Path.cwd()), nl=False)
    else:
        from devflow.control_room.dashboard import render_dashboard
        typer.echo(render_dashboard(Path.cwd()), nl=False)


@supervisor_app.command("policy")
def supervisor_policy_command(
    json_output: bool = typer.Option(False, "--json", help="Print policy as JSON."),
) -> None:
    """Show the supervisor/Hermes operating policy."""
    typer.echo(render_supervisor_policy(json_output=json_output), nl=False)


@supervisor_app.command("packet")
def supervisor_packet_command(
    json_output: bool = typer.Option(False, "--json", help="Print supervisor packet as JSON."),
) -> None:
    """Show a compact supervisor packet derived from Dev-Flow artifacts."""
    typer.echo(render_supervisor_packet(Path.cwd(), json_output=json_output), nl=False)


@supervisor_app.command("route-message")
def supervisor_route_message_command(
    message: str = typer.Argument(..., help="Raw Telegram/Hermes message to route."),
    json_output: bool = typer.Option(False, "--json", help="Print routing decision as JSON."),
) -> None:
    """Route a Telegram/Hermes message through Dev-Flow policy without mutating state."""
    typer.echo(render_telegram_route(Path.cwd(), message, json_output=json_output), nl=False)


@supervisor_app.command("classify")
def supervisor_classify_command(
    command: str = typer.Argument(..., help="The exact command to classify."),
    json_output: bool = typer.Option(False, "--json", help="Print classification result as JSON."),
) -> None:
    """Classify a command against the supervisor policy for safety."""
    typer.echo(render_supervisor_command_classification(command, json_output=json_output), nl=False)


@hermes_app.command("imessage-check")
def hermes_imessage_check_command(
    json_output: bool = typer.Option(False, "--json", help="Print readiness check as JSON."),
) -> None:
    """Inspect read-only Hermes iMessage integration readiness."""
    typer.echo(render_hermes_imessage_check(Path.cwd(), json_output=json_output), nl=False)


@git_app.command("status")
def git_status_command() -> None:
    """Show read-only Git and DevMode guardrail state."""
    devmode = detect_devmode(Path.cwd())
    typer.echo(render_git_status(Path.cwd(), devmode_detected=devmode.detected), nl=False)
    typer.echo(render_devmode_status(Path.cwd()), nl=False)


@git_app.command("checkpoint")
def git_checkpoint_command(
    message: str = typer.Option(..., "--message", "-m", help="Commit message for the local checkpoint."),
    yes: bool = typer.Option(False, "--yes", help="Stage all unignored changes and create the checkpoint commit."),
) -> None:
    """Preview or create an explicit local checkpoint commit."""
    from devflow.control_room.git_checkpoint import checkpoint, render_checkpoint

    try:
        typer.echo(render_checkpoint(checkpoint(Path.cwd(), message=message, yes=yes)), nl=False)
    except GitStateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("sync-main")
def sync_main_command() -> None:
    """Fetch origin and fast-forward local main only when safe."""
    try:
        typer.echo(sync_main(Path.cwd()), nl=False)
    except GitStateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("push-main")
def push_main_command() -> None:
    """Push main only when local and origin state are safe."""
    try:
        typer.echo(push_main(Path.cwd()), nl=False)
    except GitStateError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@app.command("next")
def next_command() -> None:
    """Print exactly one recommended next safe action and its command."""
    typer.echo(render_next_action(Path.cwd()), nl=False)


@app.command(
    "supervise",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    hidden=experimental_command_hidden(),
)
def supervise_command(
    ctx: typer.Context,
    once: bool = typer.Option(False, "--once"),
    poll: bool = typer.Option(False, "--poll"),
    task_id: str | None = typer.Option(None, "--task"),
    worker_command: str | None = typer.Option(None, "--worker-command"),
    timeout_seconds: int = typer.Option(60, "--timeout-seconds"),
    interval_seconds: int = typer.Option(5, "--interval-seconds", min=0),
    max_iterations: int = typer.Option(12, "--max-iterations", min=1),
) -> None:
    """[EXPERIMENTAL-MANUAL] Run supervisor passes over runnable tasks."""
    _enforce_experimental("supervise")
    if once and poll:
        typer.echo("supervise accepts either --once or --poll, not both.")
        raise typer.Exit(code=1)
    if not once and not poll:
        typer.echo("supervise requires --once or --poll.")
        raise typer.Exit(code=1)

    try:
        command = _supervisor_command_or_args(worker_command, list(ctx.args))
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    try:
        if poll:
            supervised_batches = [
                (iteration.iteration, iteration.tasks)
                for iteration in supervise_poll(
                    Path.cwd(),
                    task_id=task_id,
                    worker_command=command,
                    timeout_seconds=timeout_seconds,
                    interval_seconds=interval_seconds,
                    max_iterations=max_iterations,
                )
            ]
        else:
            supervised_batches = [
                (
                    None,
                    supervise_once(
                        Path.cwd(),
                        task_id=task_id,
                        worker_command=command,
                        timeout_seconds=timeout_seconds,
                    ),
                )
            ]
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    exit_code = 0
    for iteration_number, tasks in supervised_batches:
        if iteration_number is not None:
            typer.echo(f"poll_iteration: {iteration_number}")
        if not tasks:
            typer.echo("No runnable tasks.")
            continue
        iteration_exit_code = _print_supervised_tasks(tasks)
        if iteration_exit_code:
            exit_code = iteration_exit_code
    if exit_code:
        raise typer.Exit(code=exit_code)


@app.command(
    "context",
    hidden=experimental_command_hidden(),
)
def context_command(
    task_description: str = typer.Argument(None, help="The task description to plan context for."),
    show: bool = typer.Option(False, "--show", help="Show the current token-context packet."),
) -> None:
    """[EXPERIMENTAL-READONLY] Write or show a visible token-context packet for an IDE agent."""
    _enforce_experimental("context")
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
    typer.echo(f"Wrote {relative_path(plan.repo_root, plan.packet_path)}")
    typer.echo(f"mode: {plan.context_mode}")
    typer.echo(f"recommended_tools: {', '.join(plan.recommended_tools)}")
    typer.echo(f"events: {relative_path(plan.repo_root, plan.events_path)}")


@task_app.command("create")
def task_create(
    title: str,
    git_worktree: bool = typer.Option(False, "--git-worktree", help="Create a Git branch/worktree-backed worker lane."),
    definition_of_done: str | None = typer.Option(
        None,
        "--definition-of-done",
        help="Optional text describing the task's completion criteria.",
    ),
    project: str | None = typer.Option(None, "--project", help="Create the task in a registered project root."),
) -> None:
    """Create a task and its artifact directory."""
    scope = _resolve_task_project_root(project)
    try:
        task = create_task(
            scope.root,
            title,
            git_worktree=git_worktree,
            definition_of_done=definition_of_done,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Created {project_task_ref(task.id, scope.project_id)}: {task.title}")
    if scope.project_id:
        typer.echo(f"project_root: {scope.root}")
    typer.echo(f"status: {task.status}")
    typer.echo(f"workspace: {task.workspace_path}")
    if task.workspace_kind:
        typer.echo(f"workspace_kind: {task.workspace_kind}")
    if task.branch_name:
        typer.echo(f"worker_branch: {task.branch_name}")
    if task.workspace_dirty:
        typer.echo("Warning: Main worktree has uncommitted changes. Workspace contains dirty modifications.")


@task_app.command("cleanup")
def task_cleanup(
    task_id: str,
    preview: bool = typer.Option(False, "--preview", help="Preview closed-task cleanup without deleting anything."),
    apply: bool = typer.Option(False, "--apply", help="Apply conservative closed-task cleanup."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Compatibility preview for existing Git-native cleanup."),
    force: bool = typer.Option(False, "--force", help="Compatibility option for Git-native --dry-run cleanup."),
) -> None:
    """Preview or apply cleanup for one task."""
    if apply and (preview or dry_run):
        typer.echo("Choose either --preview/--dry-run or --apply, not both.", err=True)
        raise typer.Exit(code=1)
    if dry_run:
        try:
            actions = cleanup_task_git_resources(Path.cwd(), task_id, dry_run=True, force=force)
        except (KeyError, GitWorktreeError, ValueError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo("mode: dry-run")
        typer.echo(f"task: {task_id}")
        _echo_cleanup_actions(actions, dry_run=True)
        return
    if apply:
        try:
            task_for_compat = get_task(Path.cwd(), task_id)
            if task_for_compat.status != "closed":
                actions = cleanup_task_git_resources(Path.cwd(), task_id, dry_run=False, force=force)
                typer.echo("mode: apply")
                typer.echo(f"task: {task_id}")
                _echo_cleanup_actions(actions, dry_run=False)
                return
        except (KeyError, GitWorktreeError, ValueError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
    try:
        result = cleanup_closed_task(Path.cwd(), task_id, apply=apply)
    except (KeyError, TaskClosureError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"mode: {'apply' if apply else 'preview'}")
    typer.echo(f"task: {task_id}")
    _echo_task_cleanup_result(result)


@task_app.command("prune-closed")
def task_prune_closed(
    older_than: str = typer.Option(..., "--older-than", help="Prune closed-task evidence older than this duration, such as 30d or 12h."),
    preview: bool = typer.Option(False, "--preview", help="Preview closed-task evidence pruning without deleting anything."),
    apply: bool = typer.Option(False, "--apply", help="Apply closed-task evidence pruning."),
) -> None:
    """Preview or apply pruning for retained closed-task evidence."""
    if preview == apply:
        typer.echo("Choose exactly one of --preview or --apply.", err=True)
        raise typer.Exit(code=1)
    try:
        result = prune_closed_tasks(Path.cwd(), older_than=older_than, apply=apply)
    except TaskPruneError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"mode: {'apply' if apply else 'preview'}")
    typer.echo(f"older_than: {older_than}")
    if result.get("audit_path"):
        typer.echo(f"audit: {result['audit_path']}")
    _echo_task_prune_result(result)


@task_app.command("close")
def task_close(
    task_id: str,
    outcome: str = typer.Option(..., "--outcome", help="Close outcome."),
    reason: str = typer.Option(..., "--reason", help="Reason for closing the task."),
) -> None:
    """Close a task as inactive while preserving evidence."""
    try:
        closure = close_task(Path.cwd(), task_id, outcome=outcome, reason=reason)
    except (KeyError, TaskClosureError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"task: {task_id}")
    typer.echo("closed: yes")
    typer.echo(f"outcome: {closure['outcome']}")
    typer.echo(f"reason: {closure['reason']}")
    typer.echo(f"closed_at: {closure['closed_at']}")
    typer.echo(f"next_action: {closure['next_suggested_action']}")


@worktree_app.command("list")
def worktree_list() -> None:
    """List Dev-Flow-owned Git worktrees and orphan status."""
    try:
        worktrees = list_devflow_worktrees(Path.cwd())
    except GitWorktreeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if not worktrees:
        typer.echo("No Dev-Flow worktrees found.")
        return
    typer.echo(f"{'Path':<44} {'Branch':<32} {'Task':<12} {'Worker':<12} Status")
    typer.echo("-" * 116)
    for item in worktrees:
        typer.echo(
            f"{item['path']:<44} {item['branch']:<32} {item['task_id']:<12} {item['worker_id']:<12} {item['status']}"
        )


@worktree_app.command("prune")
def worktree_prune(
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview pruning by default; use --apply to mutate."),
    force: bool = typer.Option(False, "--force", help="Allow removal of dirty orphan worktrees after review."),
) -> None:
    """Remove orphaned Dev-Flow Git worktrees only when --apply is supplied."""
    try:
        actions = prune_orphan_worktrees(Path.cwd(), dry_run=dry_run, force=force)
    except GitWorktreeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"mode: {'dry-run' if dry_run else 'apply'}")
    _echo_cleanup_actions(actions, dry_run=dry_run)


@branch_app.command("list")
def branch_list() -> None:
    """List local Dev-Flow task branches and orphan status."""
    try:
        branches = list_devflow_branches(Path.cwd())
    except GitWorktreeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if not branches:
        typer.echo("No Dev-Flow branches found.")
        return
    typer.echo(f"{'Branch':<36} {'Task':<12} {'Worker':<12} {'Worktree':<44} Status")
    typer.echo("-" * 120)
    for item in branches:
        typer.echo(
            f"{item['branch']:<36} {item['task_id']:<12} {item['worker_id']:<12} {item['worktree_path']:<44} {item['status']}"
        )


@branch_app.command("archive")
def branch_archive(
    branch: str,
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview archive by default; use --apply to mutate."),
) -> None:
    """Rename a Dev-Flow task branch under devflow/archive/."""
    try:
        result = archive_devflow_branch(Path.cwd(), branch, dry_run=dry_run)
    except GitWorktreeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"mode: {'dry-run' if dry_run else 'apply'}")
    label = "would_archive_branch" if dry_run else "archived_branch"
    typer.echo(f"{label}: {result['branch']} -> {result['archive_branch']}")


@task_app.command("list")
def task_list(
    active: bool = typer.Option(False, "--active", help="Show only active tasks."),
    closed: bool = typer.Option(False, "--closed", help="Show only closed tasks."),
    project: str | None = typer.Option(None, "--project", help="List tasks from a registered project root."),
) -> None:
    """List tasks from the control-room task files."""
    if active and closed:
        typer.echo("Choose either --active or --closed, not both.", err=True)
        raise typer.Exit(code=1)
    scope = _resolve_task_project_root(project)
    projections = list_task_status_projections(scope.root)
    if active:
        projections = [projection for projection in projections if projection.is_active]
    if closed:
        projections = [projection for projection in projections if projection.task.status == "closed"]
    if not projections:
        typer.echo("No tasks found.")
        return
    rows = [(project_task_ref(projection.task.id, scope.project_id), projection) for projection in projections]
    task_width = max(10, *(len(ref) for ref, _ in rows))
    typer.echo(f"{'Task':<{task_width}} {'Status':<20} {'Verify':<16} {'Updated':<25} Title")
    typer.echo("-" * (task_width + 87))
    for task_ref, projection in rows:
        task = projection.task
        typer.echo(
            f"{task_ref:<{task_width}} {projection.display_status:<20} {projection.verify_token:<16} "
            f"{task.updated_at.isoformat():<25} {task.title}"
        )


@task_app.command("show")
def task_show(
    task_id: str,
    project: str | None = typer.Option(None, "--project", help="Show a task from a registered project root."),
) -> None:
    """Show one task's status, logs, and artifacts."""
    scope = _resolve_task_project_root(project)
    try:
        summary = build_task_show_summary(scope.root, task_id, project_id=scope.project_id)
    except TaskShowSummaryError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    for line in render_task_show_summary(summary):
        typer.echo(line)


@task_app.command("next-action")
def task_next_action_command(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print next action as JSON."),
    project: str | None = typer.Option(None, "--project", help="Inspect a task from a registered project root."),
) -> None:
    """Recommend one read-only next safe action for a task."""
    scope = _resolve_task_project_root(project)
    try:
        typer.echo(
            render_task_next_action(scope.root, task_id, json_output=json_output, project_id=scope.project_id),
            nl=False,
        )
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@task_app.command("review")
def task_review_command(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print review capsule as JSON."),
    project: str | None = typer.Option(None, "--project", help="Review a task from a registered project root."),
) -> None:
    """Render a compact supervisor-safe task review capsule."""
    scope = _resolve_task_project_root(project)
    try:
        typer.echo(
            render_task_review(scope.root, task_id, json_output=json_output, project_id=scope.project_id),
            nl=False,
        )
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@task_app.command("capsule")
def task_capsule(
    task_id: str,
    export_md: bool = typer.Option(False, "--export-md", help="Write one explicit markdown export under the task evidence folder."),
    project: str | None = typer.Option(None, "--project", help="Render a capsule from a registered project root."),
) -> None:
    """Render a read-only Review Capsule from existing task evidence."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        capsule = render_review_capsule(root, task_id)
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(capsule, nl=False)
    if export_md:
        export_path = export_review_capsule_markdown(root, task_id, capsule)
        typer.echo(f"export_path: {relative_path(root, export_path)}")


@task_app.command("review-ready")
def task_review_ready(
    task_id: str | None = typer.Argument(None, help="Task ID to inspect. Omit to inspect all active tasks."),
    json_output: bool = typer.Option(False, "--json", help="Print review readiness as JSON."),
    project: str | None = typer.Option(None, "--project", help="Inspect tasks from a registered project root."),
) -> None:
    """Inspect task readiness for human review."""
    scope = _resolve_task_project_root(project)
    try:
        if task_id is not None:
            projection = build_review_readiness_projection(scope.root, task_id, project_id=scope.project_id)
            if json_output:
                typer.echo(json.dumps(projection.model_dump(), indent=2, sort_keys=True))
            else:
                typer.echo(render_review_readiness(projection), nl=False)
            return

        summary = summarize_review_readiness(scope.root, project_id=scope.project_id)
        if json_output:
            typer.echo(json.dumps(summary.model_dump(), indent=2, sort_keys=True))
        else:
            typer.echo(render_review_readiness(summary), nl=False)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@task_app.command("orchestrate")
def task_orchestrate(
    task_id: str,
    plan_only: bool = typer.Option(False, "--plan-only", help="Write plan-only orchestration policy evidence."),
) -> None:
    """Create a plan-only parallel-worker orchestration policy artifact."""
    if not plan_only:
        typer.echo("Error: task orchestrate currently requires --plan-only.", err=True)
        raise typer.Exit(code=1)
    try:
        from devflow.control_room.orchestration_plan import (
            OrchestrationPlanError,
            create_orchestration_plan,
            render_orchestration_plan_summary,
        )

        plan = create_orchestration_plan(Path.cwd(), task_id, plan_only=True)
    except (KeyError, OrchestrationPlanError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(render_orchestration_plan_summary(Path.cwd(), plan), nl=False)


@task_app.command("fit")
def task_fit_command(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit stable JSON evidence."),
    project: str | None = typer.Option(None, "--project", help="Estimate task fit from a registered project root."),
) -> None:
    """Deterministic task-fit and context-size estimation."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        from devflow.control_room.estimator import estimate_task_fit, save_task_fit
        fit_data = estimate_task_fit(root, task_id)
        save_task_fit(root, task_id, fit_data)
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        payload = {
            "artifact_path": f".devflow/tasks/{task_id}/task-fit.yaml",
            "fit_data": fit_data,
            "task_id": task_id,
        }
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    # Render a beautiful terminal breakdown
    typer.echo(f"Estimated task-fit profile for task: {project_task_ref(task_id, scope.project_id)}")
    typer.echo("-" * 50)

    tf = fit_data["task_fit"]
    typer.echo(f"Task Type:                 {tf['task_type']}")
    typer.echo(f"Repository Scope:          {tf['repo_scope']}")
    typer.echo(f"Context Requirement:       {tf['context_requirement']}")
    typer.echo(f"Reasoning Requirement:     {tf['reasoning_requirement']}")
    typer.echo(f"Code Edit Risk:            {tf['code_edit_risk']}")
    typer.echo(f"Architectural Risk:        {tf['architectural_risk']}")
    typer.echo(f"Verification Complexity:   {tf['verification_complexity']}")
    typer.echo(f"Context Layer:             {tf['context_layer']}")
    typer.echo(f"Confidence Score:          {tf['confidence']}")

    typer.echo("")
    typer.echo("Recommended Agent Tiers:")
    typer.echo(f"  Planner:  {tf['recommended_planner_tier']}")
    typer.echo(f"  Worker:   {tf['recommended_worker_tier']}")
    typer.echo(f"  Reviewer: {tf['recommended_reviewer_tier']}")

    typer.echo("")
    typer.echo("Deterministic Context Metrics:")
    rs = fit_data["repo_scan"]
    typer.echo(f"  Changed Files Count:     {rs['changed_files_count']}")
    typer.echo(f"  Relevant Files Count:    {rs['relevant_files_count']}")
    typer.echo(f"  Relevant Lines Estimate: {rs['relevant_lines_estimate']}")
    typer.echo(f"  Relevant Tokens (char):  {rs['relevant_tokens_estimate']}")
    typer.echo(f"  Test Files Needed:       {rs['test_files_needed']}")
    typer.echo(f"  Docs Needed:             {rs['docs_needed']}")
    typer.echo(f"  Task History Tokens:     {rs['task_history_tokens']}")
    typer.echo(f"  Total Context Estimate:  {rs['total_context_estimate']}")

    typer.echo("-" * 50)
    typer.echo(f"Wrote task-fit.yaml under .devflow/tasks/{task_id}/")


@task_app.command(
    "pack",
    hidden=experimental_command_hidden(),
)
def task_pack_command(task_id: str, role: str) -> None:
    """[EXPERIMENTAL-READONLY] Build and save a role-based context pack for a task."""
    _enforce_experimental("task pack")
    root = Path.cwd()
    try:
        from devflow.control_room.context_pack import build_context_pack, save_context_pack
        pack_data = build_context_pack(root, task_id, role)
        save_context_pack(root, task_id, role, pack_data)
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    # Render beautiful breakdown
    typer.echo(f"Compiled context pack for task: {task_id}")
    typer.echo(f"Role:                          {role.upper()}")
    typer.echo("-" * 50)

    cp = pack_data["context_pack"]
    typer.echo(f"Context Layer:                 {cp['context_layer']}")
    typer.echo(f"Estimated Pack Tokens:         {cp['estimated_tokens']}")

    typer.echo("")
    typer.echo("Included Sources:")
    for inc in cp["includes"]:
        typer.echo(f"  - {inc}")

    typer.echo("")
    typer.echo("Excluded Sources:")
    for exc in cp["excludes"]:
        typer.echo(f"  - {exc}")

    typer.echo("-" * 50)
    typer.echo(f"Wrote context-pack-{role}.yaml under .devflow/tasks/{task_id}/")


@task_app.command("scout")
def task_scout_command(
    task_id: str,
    role: str = typer.Option("all", "--role", help="Scout role to run, or 'all'."),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
    project: str | None = typer.Option(None, "--project", help="Run scout evidence from a registered project root."),
) -> None:
    """Run local scout roles to gather routing evidence and analyze risks."""
    scope = _resolve_task_project_root(project)
    root = scope.root

    try:
        from devflow.control_room.scout import run_scout_reports, save_scout_report

        reports = run_scout_reports(root, task_id, role=role)
        artifact_paths = {
            scout_role: relative_path(root, save_scout_report(root, task_id, scout_role, data))
            for scout_role, data in reports.items()
        }
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        payload = {
            "artifact_paths": artifact_paths,
            "reports": reports,
            "task_id": task_id,
        }
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    # Render beautiful breakdown
    typer.echo(f"Executed scout evaluation for task: {project_task_ref(task_id, scope.project_id)}")
    for scout_role, data in reports.items():
        sr = data["scout_report"]
        typer.echo("-" * 50)
        typer.echo(f"Scout Role:                  {sr['role'].upper()}")
        for key in sorted(sr.keys()):
            if key == "role":
                continue
            val = sr[key]
            if isinstance(val, list):
                typer.echo(f"  {key}:")
                for item in val:
                    typer.echo(f"    - {item}")
            else:
                typer.echo(f"  {key}: {val}")

        typer.echo(f"Wrote {artifact_paths[scout_role]}")
    typer.echo("-" * 50)


@task_app.command("route")
def task_route_command(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit stable JSON evidence."),
    project: str | None = typer.Option(None, "--project", help="Run routing evidence from a registered project root."),
) -> None:
    """Run conservative evidence-only routing matching for a task."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        result = build_task_routing_result(root, task_id, project_id=scope.project_id)
    except TaskRoutingCommandError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(render_task_routing_json(result))
        return

    for line in render_task_routing_lines(result):
        typer.echo(line)


@task_app.command("scorecard")
def task_scorecard_command(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Print routing-quality scorecard as JSON."),
    project: str | None = typer.Option(None, "--project", help="Compile scorecard from a registered project root."),
) -> None:
    """Compile and display a task's post-run routing quality scorecard."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        result = build_task_scorecard_result(root, task_id, project_id=scope.project_id)
    except TaskScorecardCommandError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(render_task_scorecard_json(result))
        return

    for line in render_task_scorecard_lines(result):
        typer.echo(line)


@task_app.command("packet")
def task_packet(
    task_id: str,
    save: bool = typer.Option(False, "--save", help="Save the task packet under the task folder."),
    text: bool = typer.Option(False, "--text", help="Output human-readable text preview instead of JSON."),
    project: str | None = typer.Option(None, "--project", help="Build a packet from a registered project root."),
) -> None:
    """Build and print a task's TaskPacket as deterministic JSON."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        from devflow.control_room.task_packet import (
            build_task_packet,
            render_task_packet_text,
            save_task_packet,
        )
        packet = build_task_packet(task_id, root=root)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    text_md = render_task_packet_text(packet)

    if save:
        written = save_task_packet(root, task_id, packet, text_md=text_md)
        for p in written:
            rel_p = relative_path(root, p)
            typer.echo(f"Wrote {rel_p}")
    else:
        if text:
            typer.echo(text_md)
        else:
            packet_json = json.dumps(packet.model_dump(mode="json"), sort_keys=True, indent=2)
            typer.echo(packet_json)


@task_app.command("normalize-proposal")
def task_normalize_proposal(
    task_id: str,
    run_id: str | None = typer.Option(None, "--run-id", help="Normalize a specific local model run id."),
    response_path: str | None = typer.Option(None, "--response-path", help="Normalize a specific response.md path."),
) -> None:
    """Normalize local model response evidence into proposal artifacts."""
    root = Path.cwd()
    try:
        result = normalize_proposal(
            root,
            task_id,
            run_id=run_id,
            response_path=Path(response_path) if response_path else None,
        )
    except (KeyError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"classification: {result.classification}")
    typer.echo(f"proposal: {result.proposal_path}")
    typer.echo(f"proposal_json: {result.proposal_json_path}")
    if result.patch_candidate_path:
        typer.echo(f"proposal_patch: {result.patch_candidate_path}")
    if result.validation_path:
        typer.echo(f"validation: {result.validation_path}")
    if result.warnings:
        typer.echo("warnings:")
        for warning in result.warnings:
            typer.echo(f"  - {warning}")
    typer.echo(f"next: {result.next_action_command or 'None'}")


@task_app.command("review-patch")
def task_review_patch(
    task_id: str,
    run_id: str | None = typer.Option(None, "--run-id", help="Review a specific normalized local model run id."),
    agent: str | None = typer.Option(None, "--agent", help="Normalize and review proposal.patch from a task agent."),
    project: str | None = typer.Option(None, "--project", help="Review patch evidence from a registered project root."),
) -> None:
    """Review normalized proposal.patch evidence without applying it."""
    scope = _resolve_task_project_root(project)
    try:
        result = build_task_patch_review_result(
            scope.root,
            task_id,
            run_id=run_id,
            agent_id=agent,
            project_id=scope.project_id,
        )
    except TaskPatchGateCommandError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for line in render_task_patch_review_lines(result):
        typer.echo(line)


@task_app.command("patch-dry-run")
def task_patch_dry_run(
    task_id: str,
    run_id: str | None = typer.Option(None, "--run-id", help="Dry-run a specific reviewed local model run id."),
    agent: str | None = typer.Option(None, "--agent", help="Dry-run a reviewed proposal.patch from a task agent."),
    project: str | None = typer.Option(None, "--project", help="Dry-run patch evidence from a registered project root."),
) -> None:
    """Preview whether reviewed proposal.patch evidence would apply without mutating files."""
    scope = _resolve_task_project_root(project)
    try:
        result = build_task_patch_dry_run_result(
            scope.root,
            task_id,
            run_id=run_id,
            agent_id=agent,
            project_id=scope.project_id,
        )
    except TaskPatchGateCommandError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for line in render_task_patch_dry_run_lines(result):
        typer.echo(line)


@task_app.command("log")
def task_log(
    task_id: str,
    verify: bool = typer.Option(False, "--verify", help="Print the verification log instead."),
    tail: int | None = typer.Option(None, "--tail", min=1, help="Number of lines to tail."),
    project: str | None = typer.Option(None, "--project", help="Print logs from a registered project root."),
) -> None:
    """Print the logs for a task."""
    scope = _resolve_task_project_root(project)
    root = scope.root
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


@task_app.command("history")
def task_history(
    task_id: str,
    limit: int = typer.Option(20, "--limit", min=1, help="Limit chronological history timeline events count.")
) -> None:
    """Render a compact timeline of chronological task events."""
    typer.echo(render_task_history(Path.cwd(), task_id, limit=limit), nl=False)


@task_app.command("local")
def task_local(
    task_id: str,
    worker: str | None = typer.Option(None, "--worker", help="Local Ollama worker name."),
    agent: str | None = typer.Option(None, "--agent", help="Local Ollama agent name (alias for --worker)."),
    input_worker: str | None = typer.Option(None, "--input-worker", help="Prior local worker output to review."),
    timeout_seconds: int | None = typer.Option(None, "--timeout-seconds", min=1),
) -> None:
    """Run a legacy advisory local Ollama worker for a task."""
    resolved_worker = agent or worker
    if not resolved_worker:
        typer.echo("Error: Please provide either --worker or --agent option.", err=True)
        raise typer.Exit(code=1)

    try:
        result = run_local_model_task(
            Path.cwd(),
            task_id,
            resolved_worker,
            input_worker=input_worker,
            timeout_seconds=timeout_seconds,
        )
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    # Human-facing advisory ladder output
    typer.echo("-" * 50)
    typer.echo("Legacy Local Ollama Advisory Evidence Captured!")
    typer.echo("  Mode:              legacy advisory evidence")
    typer.echo("  Canonical worker:  devflow task run <task-id> --worker qwopus-implementer")
    typer.echo("  Boundary:          task local shells out to ollama run; it does not write proposal.patch, apply patches, verify, or promote.")
    typer.echo(f"  Agent:             {resolved_worker}")
    typer.echo(f"  Model:             {result.model}")
    typer.echo(f"  Status:            {result.status}")
    typer.echo(f"  Run ID:            {result.run_id}")
    typer.echo(f"  Evidence Dir:      {relative_path(Path.cwd(), result.artifact_dir)}")
    typer.echo(f"  Prompt evidence:   {relative_path(Path.cwd(), result.prompt_path)}")
    typer.echo(f"  Response evidence: {relative_path(Path.cwd(), result.response_path)}")
    typer.echo(f"  Run Metadata:      {relative_path(Path.cwd(), result.run_json_path)}")
    typer.echo("-" * 50)

    # Standard compatibility outputs
    typer.echo(f"{task_id}: {result.status}")
    typer.echo(f"local_worker: {resolved_worker}")
    typer.echo(f"model: {result.model}")
    typer.echo("local_worker_mode: legacy_advisory")
    typer.echo("canonical_implementation_command: devflow task run <task-id> --worker qwopus-implementer")
    typer.echo(f"run_id: {result.run_id}")
    typer.echo(f"evidence_dir: {relative_path(Path.cwd(), result.artifact_dir)}")
    typer.echo(f"prompt_path: {relative_path(Path.cwd(), result.prompt_path)}")
    typer.echo(f"raw_response_path: {relative_path(Path.cwd(), result.raw_response_path)}")
    typer.echo(f"response_path: {relative_path(Path.cwd(), result.response_path)}")
    typer.echo(f"stderr_path: {relative_path(Path.cwd(), result.stderr_path)}")
    typer.echo(f"local_worker_run: {relative_path(Path.cwd(), result.run_json_path)}")

    if result.error_message:
        typer.echo(result.error_message)

    if result.status == "success":
        typer.echo("")
        typer.echo("Local advisory ladder (optional scouting/review evidence):")
        typer.echo("  1. Planner advisory:     devflow task local <task-id> --agent qwen-planner")
        typer.echo("  2. Implementation patch: devflow task run <task-id> --worker qwopus-implementer  [canonical]")
        typer.echo("  3. Review advisory:      devflow task local <task-id> --agent gemma-reviewer")
        typer.echo("  4. Review patch:         devflow task review-patch <task-id> --agent qwopus-implementer")
        typer.echo("  5. Dry-run patch:        devflow task patch-dry-run <task-id> --agent qwopus-implementer")
        typer.echo("  6. Apply patch:          devflow task apply-patch <task-id> --agent qwopus-implementer")
        typer.echo("  7. Verification:         devflow task verify <task-id> --shell \"<command>\"")
        typer.echo("  8. Promotion:            human-controlled promote-preview/promote only after verification.")

        if resolved_worker == "qwen-planner":
            typer.echo("")
            typer.echo("Suggested Next Action:")
            typer.echo("  Draft implementation patch using registry-backed qwopus-implementer:")
            typer.echo(f"    devflow task run {task_id} --worker qwopus-implementer")
        elif resolved_worker == "qwopus-implementer":
            typer.echo("")
            typer.echo("Suggested Next Action:")
            typer.echo("  This was advisory-only qwopus output. For canonical patch evidence, run:")
            typer.echo(f"    devflow task run {task_id} --worker qwopus-implementer")
        elif resolved_worker == "qwen-implementer":
            typer.echo("")
            typer.echo("Suggested Next Action:")
            typer.echo("  Review implementation diff using gemma-reviewer:")
            typer.echo(f"    devflow task local {task_id} --agent gemma-reviewer")
        elif resolved_worker == "gemma-reviewer":
            typer.echo("")
            typer.echo("Suggested Next Action:")
            typer.echo("  Inspect evidence review, apply the patch, and run verification:")
            typer.echo(f"    devflow task verify {task_id} --shell \"<test-command>\"")
        typer.echo("-" * 50)

    if result.status != "success":
        raise typer.Exit(code=result.exit_code if result.exit_code is not None else 1)


@task_app.command("local-review")
def task_local_review(
    task_id: str,
    base_url: str | None = typer.Option(None, "--base-url", help="Local OpenAI-compatible base URL."),
    model: str | None = typer.Option(None, "--model", help="Local OpenAI-compatible model ID."),
    timeout_seconds: int | None = typer.Option(None, "--timeout-seconds", min=1, help="Timeout in seconds."),
    temperature: float | None = typer.Option(None, "--temperature", min=0.0, max=2.0, help="Temperature for local model."),
    save_prompt: bool = typer.Option(True, "--save-prompt", help="Save prompt.md under the run folder."),
    max_packet_chars: int = typer.Option(200_000, "--max-packet-chars", help="Capping size of rendered task packet text."),
) -> None:
    """Run an advisory local model packet review for a task."""
    from devflow.control_room.local_packet_worker import run_local_packet_review

    try:
        result = run_local_packet_review(
            task_id=task_id,
            base_url=base_url,
            model=model,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            save_prompt=save_prompt,
            max_packet_chars=max_packet_chars,
            root=Path.cwd(),
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    rel_evidence_dir = relative_path(Path.cwd(), result["evidence_dir"])
    rel_response_path = relative_path(Path.cwd(), result["response_path"])

    if result["truncation_warning"]:
        typer.echo(result["truncation_warning"])

    typer.echo("-" * 50)
    typer.echo("Local Model Bounded Packet Review Evidence Captured!")
    typer.echo("  Mode:              local packet review (advisory)")
    typer.echo(f"  Run ID:            {result['run_id']}")
    typer.echo(f"  Evidence Dir:      {rel_evidence_dir}")
    typer.echo(f"  Response evidence: {rel_response_path}")
    typer.echo("-" * 50)
    typer.echo("")
    typer.echo("Recommended Next DevFlow Step:")
    typer.echo("  1. Review the generated proposal evidence at:")
    typer.echo(f"     {rel_response_path}")
    typer.echo("  2. Explicitly choose to run implementer, apply patch, or verify task:")
    typer.echo(f"     devflow task show {task_id}")
    typer.echo("-" * 50)


@task_app.command("run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def task_run(
    ctx: typer.Context,
    task_id: str,
    worker: str = typer.Option("shell", "--worker"),
    shell_command: str | None = typer.Option(None, "--shell"),
    timeout_seconds: int = typer.Option(60, "--timeout-seconds"),
    project: str | None = typer.Option(None, "--project", help="Run a task from a registered project root."),
) -> None:
    """Run a task with a worker command after '--'."""
    scope = _resolve_task_project_root(project)
    root = scope.root

    try:
        command = _shell_command_or_args(shell_command, list(ctx.args), "Shell worker")
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    try:
        result = run_task_command(
            root,
            task_id,
            command,
            worker_adapter=worker,
            timeout_seconds=timeout_seconds,
            project_id=scope.project_id,
        )
    except TaskRunCommandError as exc:
        for line in exc.lines:
            typer.echo(line)
        raise typer.Exit(code=exc.exit_code) from exc

    for line in render_task_run_lines(result):
        typer.echo(line)
    _echo_review_capsule(root, result.task.id)
    if result.task.status != "complete":
        raise typer.Exit(code=result.exit_code)


@task_app.command("auto-run", hidden=experimental_command_hidden())
def task_auto_run(
    task_id: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the routing decision without executing."),
    project: str | None = typer.Option(None, "--project", help="Auto-run a task from a registered project root."),
) -> None:
    """Classify, route, and run a task using the best available worker.

    This is the orchestrator's one-shot command:
    1. Classify the task (archetype, context estimate, required capabilities)
    2. Route to the best eligible worker (scored by capability match)
    3. Execute the worker

    Use --dry-run to inspect the routing decision without running.
    """
    _enforce_experimental("task auto-run")
    scope = _resolve_task_project_root(project)
    project_option = f" --project {project}" if project else ""
    result = run_task_auto_run_command(
        scope.root,
        task_id,
        dry_run=dry_run,
        project_id=project,
        project_option=project_option,
    )
    for line in result.lines:
        typer.echo(line)
    if result.exit_code:
        raise typer.Exit(code=result.exit_code)


@task_app.command("escalation-packet")
def task_escalation_packet(
    task_id: str,
    agent: str = typer.Option("qwopus-implementer", "--agent", help="The local agent evidence to escalate."),
) -> None:
    """Write a compact frontier-review packet from local worker evidence without calling providers."""
    root = Path.cwd()
    try:
        task = get_task(root, task_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    packet_path = write_qwopus_escalation_packet(root, task, agent)
    typer.echo(f"escalation_packet_path: {relative_path(root, packet_path)}")
    typer.echo("provider_calls: none")


@task_app.command("finalize")
def task_finalize(
    task_id: str,
    commit: bool = typer.Option(False, "--commit", help="Perform the actual commit instead of a dry-run preview."),
) -> None:
    """Preview or commit safe task-owned changes in its isolated Git worktree."""
    root = Path.cwd()
    from devflow.control_room.finalizer import finalize_task, FinalizationError
    try:
        evidence = finalize_task(root, task_id, commit=commit)
    except FinalizationError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Finalization summary for task: {task_id}")
    typer.echo("-" * 50)
    typer.echo("staged:")
    for f in evidence.get("staged_files") or []:
        typer.echo(f"  - {f}")
    if not evidence.get("staged_files"):
        typer.echo("  (none)")

    typer.echo("ignored:")
    for f in evidence.get("ignored_evidence_files") or []:
        typer.echo(f"  - {f}")
    if not evidence.get("ignored_evidence_files"):
        typer.echo("  (none)")

    typer.echo(f"verification_status: {evidence['verification_status']}")

    commit_hash = evidence.get("commit_hash")
    if commit_hash:
        typer.echo(f"commit_hash: {commit_hash}")
        typer.echo(f"commit_location: {evidence.get('commit_location', 'task worker branch')}")
        if evidence.get("worker_branch"):
            typer.echo(f"worker_branch: {evidence['worker_branch']}")
        typer.echo("main_changed: no")
    else:
        typer.echo("commit_hash: dry-run")

    typer.echo(f"next_action: {evidence['next_suggested_action']}")
    _echo_review_capsule(root, task_id)


@task_app.command("verify", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def task_verify(
    ctx: typer.Context,
    task_id: str,
    shell_command: str | None = typer.Option(None, "--shell"),
    timeout_seconds: int = typer.Option(120, "--timeout-seconds"),
    project: str | None = typer.Option(None, "--project", help="Verify a task from a registered project root."),
) -> None:
    """Run a verification command inside the task workspace."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        command = _shell_command_or_args(shell_command, list(ctx.args), "Verification")
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    try:
        task = verify_task(root, task_id, command, timeout_seconds=timeout_seconds)
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"{project_task_ref(task.id, scope.project_id)}: verification {task.verification_status}")
    if scope.project_id:
        typer.echo(f"project_root: {root}")
    typer.echo(f"verification_log_path: {task.verification_log_path}")
    if task.latest_log_line:
        typer.echo(f"latest_log_line: {task.latest_log_line}")
    _echo_review_capsule(root, task.id)
    if task.verification_status != "passed":
        exit_code = task.verification_exit_code if task.verification_exit_code is not None else 1
        raise typer.Exit(code=exit_code)


@task_app.command("apply-patch")
def task_apply_patch(
    task_id: str,
    agent: str | None = typer.Option(None, "--agent", help="The specific agent's patch to apply."),
    run_id: str | None = typer.Option(None, "--run-id", help="Apply a specific reviewed local model run proposal.patch."),
    project: str | None = typer.Option(None, "--project", help="Apply patch evidence from a registered project root."),
) -> None:
    """Apply a proposed patch from a worker agent to the isolated task workspace."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        result = build_task_apply_patch_result(
            root,
            task_id,
            agent_id=agent,
            run_id=run_id,
            project_id=scope.project_id,
        )
    except TaskApplyPatchCommandError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for line in render_task_apply_patch_result(result):
        typer.echo(line)


@task_app.command("promote-preview")
def task_promote_preview(
    task_id: str,
    project: str | None = typer.Option(None, "--project", help="Preview promotion from a registered project root."),
) -> None:
    """Preview changes that would be promoted from the isolated task workspace."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        view = build_task_promotion_preview_view(root, task_id, project_id=scope.project_id)
    except TaskPromotionCommandError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    for line in view.lines:
        typer.echo(line)
    _echo_review_capsule(root, task_id, promotion_preview=view.promotion_preview)


@task_app.command("promote")
def task_promote(
    task_id: str,
    force: bool = typer.Option(False, "--force", help="Bypass dirty repository check."),
    force_stale_baseline: bool = typer.Option(
        False,
        "--force-stale-baseline",
        help="Bypass the stale task-baseline guard after manual conflict review.",
    ),
    apply_deletions: bool = typer.Option(False, "--apply-deletions", help="Apply file deletions to the main checkout."),
    project: str | None = typer.Option(None, "--project", help="Promote a task from a registered project root."),
) -> None:
    """Promote verified changes from the isolated workspace to the main checkout."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        view = build_task_promotion_run_view(
            root,
            task_id,
            force=force,
            force_stale_baseline=force_stale_baseline,
            apply_deletions=apply_deletions,
            project_id=scope.project_id,
        )
    except TaskPromotionCommandError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    for line in view.lines:
        typer.echo(line)

    if view.no_changes:
        return

    if view.requires_confirmation:
        confirmed = typer.confirm("Promote these changes to the main checkout?", default=False)
        if not confirmed:
            typer.echo("Promotion aborted.")
            return

    try:
        result = execute_task_promotion_run(
            root,
            task_id,
            force=force,
            force_stale_baseline=force_stale_baseline,
            apply_deletions=apply_deletions,
        )
    except TaskPromotionCommandError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    for line in result.lines:
        typer.echo(line)


@task_app.command("open")
def task_open(
    task_id: str = typer.Argument(..., help="The task ID (e.g. task-0002)."),
    worker: str | None = typer.Option(None, "--worker", help="Prefer output files for this local worker."),
    raw: bool = typer.Option(False, "--raw", help="Prefer raw response/output files."),
    list_candidates: bool = typer.Option(False, "--list", help="Print candidate output files in priority order and exit."),
) -> None:
    """Open the most relevant task output artifact."""
    root = Path.cwd()
    try:
        selection = select_task_open_artifact(root, task_id, worker=worker, raw=raw)
    except TaskArtifactOpenError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if list_candidates:
        for line in render_task_open_candidates(selection):
            typer.echo(line)
        return

    if selection.selected is None:
        typer.echo("Error: No candidate output files found in task workspace.", err=True)
        raise typer.Exit(code=1)

    top_candidate = selection.selected.path
    opened = open_task_artifact(top_candidate)

    if opened:
        typer.echo(f"Opened: {top_candidate.relative_to(root)}")
    else:
        typer.echo(f"Failed to open automatically. Exact path:\n{top_candidate.resolve()}")


@task_app.command("evidence")
def task_evidence(
    task_id: str = typer.Argument(..., help="The task ID (e.g. task-0002)."),
    local: bool = typer.Option(False, "--local", help="Show the latest local AI worker evidence summary."),
) -> None:
    """Show a concise terminal summary of the task's evidence."""
    try:
        summary = build_task_evidence_summary(Path.cwd(), task_id, local=local)
    except TaskEvidenceSummaryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for line in render_task_evidence_summary(summary):
        typer.echo(line)


# Backward-compatible names for importers while the old CLI is retired.
def init_workspace() -> None:
    init_control_room(Path.cwd())


def status_workspace() -> None:
    task_list()


def main() -> None:
    app()


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


def _supervisor_command_or_args(worker_command: str | None, args: list[str]) -> list[str]:
    if args and args[0] == "--":
        args = args[1:]
    if worker_command is not None and args:
        raise ValueError(
            "Supervisor worker command accepts either --worker-command or a command after '--', not both."
        )
    if worker_command is not None:
        if not worker_command.strip():
            raise ValueError("Supervisor --worker-command cannot be empty.")
        return [worker_command]
    if args:
        return args
    return [DEFAULT_WORKER_COMMAND]


def _print_supervised_tasks(tasks: list[TaskRecord]) -> int:
    exit_code = 0
    for task in tasks:
        typer.echo(f"{task.id}: {task.status}")
        typer.echo(f"log_path: {task.log_path}")
        typer.echo(f"result_path: {task.result_path}")
        if task.latest_log_line:
            typer.echo(f"latest_log_line: {task.latest_log_line}")
        if task.status != "complete":
            exit_code = task.last_exit_code if task.last_exit_code is not None else 1
    return exit_code


def _echo_review_capsule(
    root: Path,
    task_id: str,
    *,
    promotion_preview: dict[str, Any] | None = None,
) -> None:
    try:
        typer.echo()
        typer.echo(render_review_capsule(root, task_id, promotion_preview=promotion_preview), nl=False)
    except Exception as exc:
        typer.echo(f"review_capsule: unavailable ({exc})", err=True)


def _echo_reconciliation_report(report: dict[str, Any]) -> None:
    typer.echo(f"status: {report['status']}")
    typer.echo(f"tasks_checked: {report['tasks_checked']}")
    findings = report["findings"]
    typer.echo("findings:")
    if not findings:
        typer.echo("  none")
        return
    for finding in findings:
        task = f" {finding['task_id']}" if finding.get("task_id") else ""
        typer.echo(f"  - [{finding['severity']}] {finding['code']}{task}: {finding['detail']}")
        typer.echo(f"    path: {finding['path']}")
        typer.echo(f"    next_safe_action: {finding['next_action']}")


def _echo_cleanup_actions(actions: list[dict[str, Any]], dry_run: bool) -> None:
    if not actions:
        typer.echo("No Git-native cleanup actions found.")
        return
    for action in actions:
        if action["action"] == "remove_worktree":
            label = "would_remove_worktree" if dry_run else "removed_worktree"
            typer.echo(f"{label}: {action['path']}")
        elif action["action"] == "archive_branch":
            label = "would_archive_branch" if dry_run else "archived_branch"
            typer.echo(f"{label}: {action['branch']} -> {action['archive_branch']}")


def _echo_task_cleanup_result(result: dict[str, Any]) -> None:
    would_remove = result.get("would_remove") or []
    removed = result.get("removed") or []
    for path in would_remove:
        typer.echo(f"would_remove: {path}")
    for path in removed:
        typer.echo(f"removed: {path}")
    if not would_remove and not removed:
        typer.echo("cleanup_candidates: none")
    for path in result.get("retained") or []:
        typer.echo(f"retained: {path}")


def _echo_task_prune_result(result: dict[str, Any]) -> None:
    would_prune = result.get("would_prune") or []
    pruned = result.get("pruned") or []
    for path in would_prune:
        typer.echo(f"would_prune: {path}")
    for path in pruned:
        typer.echo(f"pruned: {path}")
    if not would_prune and not pruned:
        typer.echo("prune_candidates: none")
    for item in result.get("skipped") or []:
        typer.echo(f"skipped: {item['task_id']} {item['reason']}")
    for item in result.get("refused") or []:
        typer.echo(f"refused: {item['task_id']} {item['reason']}")


@worker_app.command("validate-outcome")
def worker_validate_outcome(outcome_json: str) -> None:
    """Validate worker outcome metadata without running agents or mutating task state."""
    try:
        from devflow.control_room.worker_outcome import (
            render_worker_outcome_validation,
            validate_worker_outcome_file,
        )

        result = validate_worker_outcome_file(Path.cwd(), Path(outcome_json))
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(render_worker_outcome_validation(result), nl=False)
    if result["status"] != "passed":
        raise typer.Exit(code=1)


@release_app.command("readiness")
def release_readiness_command(
    pytest_evidence: Path | None = typer.Option(
        None,
        "--pytest-evidence",
        help="Path to captured full-suite pytest output.",
    ),
    stale_context_evidence: Path | None = typer.Option(
        None,
        "--stale-context-evidence",
        help="Path to captured stale-context scan output.",
    ),
    dogfood_run: str = typer.Option("latest", "--dogfood-run", help="Dogfood run id to use, or latest."),
    json_output: bool = typer.Option(False, "--json", help="Print release-readiness report as JSON."),
) -> None:
    """Check explicit release-readiness gates without running heavy suites."""
    from devflow.control_room.release_readiness import (
        build_release_readiness_report,
        render_release_readiness_report,
    )

    report = build_release_readiness_report(
        Path.cwd(),
        pytest_evidence=pytest_evidence,
        stale_context_evidence=stale_context_evidence,
        dogfood_run_id=dogfood_run,
    )
    if json_output:
        typer.echo(json.dumps(report, indent=2, sort_keys=True))
    else:
        typer.echo(render_release_readiness_report(report), nl=False)
    if report["status"] != "passed":
        raise typer.Exit(code=1)


@knowledge_app.command("capture")
def knowledge_capture(
    from_task: str | None = typer.Option(None, "--from-task", help="Capture a proposed knowledge item from an existing task."),
    from_validation: str | None = typer.Option(
        None,
        "--from-validation",
        help="Capture a proposed knowledge item from worker outcome validation evidence.",
    ),
) -> None:
    """Capture proposed, human-reviewed reusable knowledge from existing evidence."""
    if bool(from_task) == bool(from_validation):
        typer.echo("Error: choose exactly one of --from-task or --from-validation.", err=True)
        raise typer.Exit(code=1)
    try:
        from devflow.control_room.knowledge_foundry import (
            KnowledgeFoundryError,
            capture_from_task,
            capture_from_validation,
        )

        item = (
            capture_from_task(Path.cwd(), from_task)
            if from_task
            else capture_from_validation(Path.cwd(), Path(str(from_validation)))
        )
    except (KeyError, KnowledgeFoundryError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"knowledge_id: {item['id']}")
    typer.echo("status: proposed")
    typer.echo(f"type: {item['type']}")
    typer.echo(f"path: .devflow/knowledge/{item['id']}/knowledge.json")
    typer.echo("task_modified: no")
    typer.echo("promotion_run: no")


@knowledge_app.command("list")
def knowledge_list() -> None:
    """List local Knowledge Foundry items."""
    from devflow.control_room.knowledge_foundry import list_knowledge, render_knowledge_list

    typer.echo(render_knowledge_list(list_knowledge(Path.cwd())), nl=False)


@knowledge_app.command("show")
def knowledge_show(knowledge_id: str) -> None:
    """Show one Knowledge Foundry item and its note."""
    try:
        from devflow.control_room.knowledge_foundry import KnowledgeFoundryError, render_knowledge_show, show_knowledge

        metadata, note = show_knowledge(Path.cwd(), knowledge_id)
    except (KnowledgeFoundryError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(render_knowledge_show(metadata, note), nl=False)


@knowledge_app.command("promote")
def knowledge_promote(knowledge_id: str) -> None:
    """Promote a reviewed knowledge item without promoting task code."""
    try:
        from devflow.control_room.knowledge_foundry import KnowledgeFoundryError, promote_knowledge

        item = promote_knowledge(Path.cwd(), knowledge_id)
    except (KnowledgeFoundryError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"knowledge_id: {item['id']}")
    typer.echo("status: promoted")
    typer.echo("task_promotion_run: no")


@knowledge_app.command("reject")
def knowledge_reject(knowledge_id: str) -> None:
    """Reject a knowledge item while preserving its source references."""
    try:
        from devflow.control_room.knowledge_foundry import KnowledgeFoundryError, reject_knowledge

        item = reject_knowledge(Path.cwd(), knowledge_id)
    except (KnowledgeFoundryError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"knowledge_id: {item['id']}")
    typer.echo("status: rejected")
    typer.echo("task_modified: no")


@knowledge_app.command("search")
def knowledge_search(query: str) -> None:
    """Search local knowledge title, tags, and note text."""
    from devflow.control_room.knowledge_foundry import render_knowledge_list, search_knowledge

    typer.echo(render_knowledge_list(search_knowledge(Path.cwd(), query)), nl=False)


df_app = typer.Typer(help="Dev-Flow short-command terminal interface")


@df_app.command("quick")
def df_quick() -> None:
    """Print a concise reminder of Dev-Flow local agent commands."""
    reminder = (
        "Dev-Flow local agent commands\n\n"
        "Talk to Qwopus:\n"
        "  qwopus \"your prompt\"\n"
        "  qwopus chat\n"
        "  qwopus --project \"what is this project?\"\n"
        "  qwopus --file path/to/file \"explain this\"\n"
        "  qwopus --show-paths \"your prompt\"\n"
        "  qwopus --no-save \"your prompt\"\n\n"
        "Default Dev-Flow agent:\n"
        "  df ask \"your prompt\"\n"
        "  df ask --project \"what is this project?\"\n"
        "  df chat\n"
        "  df run --prompt \"your prompt\"\n"
        "  df run --project --prompt \"summarize this project\"\n"
        "  df run --prompt-file prompt.md\n"
        "  cat prompt.md | df run --stdin\n\n"
        "Code-change task mode:\n"
        "  devflow task create \"task title\"\n"
        "  devflow task run <task-id> --worker qwopus-implementer\n"
        "  devflow task review-patch <task-id> --agent qwopus-implementer\n"
        "  devflow task patch-dry-run <task-id> --agent qwopus-implementer\n"
        "  devflow task apply-patch <task-id> --agent qwopus-implementer\n"
        "  devflow task verify <task-id> --shell '<command>'\n"
        "  devflow task promote-preview <task-id>\n\n"
        "Tip:\n"
        "  Quotes are optional for simple prompts. Use quotes for shell-sensitive characters, or use qwopus chat."
    )
    typer.echo(reminder)


@df_app.command("help-local")
def df_help_local() -> None:
    """Print a concise reminder of Dev-Flow local agent commands."""
    df_quick()


@df_app.command("ask")
def df_ask(
    prompt: list[str] = typer.Argument(None, help="The prompt to send to the agent."),
    agent: str = typer.Option("qwopus-implementer", "--agent", help="The local agent name."),
    project: bool = typer.Option(False, "--project", help="Include compact project context."),
    file: str | None = typer.Option(None, "--file", help="An optional file to include in the context."),
    show_paths: bool = typer.Option(False, "--show-paths", help="Print saved paths of evidence files."),
    no_save: bool = typer.Option(False, "--no-save", help="Disable saving evidence to disk."),
    allow_disabled: bool = typer.Option(False, "--allow-disabled", help="Allow using disabled agents."),
) -> None:
    """Ask a local agent a prompt directly."""
    if not prompt:
        typer.echo(
            "Error: prompt is required.\n\n"
            "Try:\n"
            "  df ask \"your prompt\"\n"
            "  qwopus \"your prompt\"\n"
            "  qwopus chat\n"
            "  df quick",
            err=True,
        )
        raise typer.Exit(code=1)
    prompt_text = " ".join(prompt)
    from devflow.control_room.agent_terminal import AgentTerminalRunner
    runner = AgentTerminalRunner(repo_root=Path.cwd(), agent_name=agent, allow_disabled=allow_disabled)
    runner.run_one_shot(
        command="ask",
        prompt=prompt_text,
        file_to_include=file,
        no_save=no_save,
        show_paths=show_paths,
        include_project=project,
    )


@df_app.command("run")
def df_run(
    prompt: str | None = typer.Option(None, "--prompt", help="The prompt to send to the agent."),
    prompt_file: str | None = typer.Option(None, "--prompt-file", help="Read prompt from a file."),
    stdin: bool = typer.Option(False, "--stdin", help="Read prompt from stdin."),
    agent: str = typer.Option("qwopus-implementer", "--agent", help="The local agent name."),
    project: bool = typer.Option(False, "--project", help="Include compact project context."),
    file: str | None = typer.Option(None, "--file", help="An optional file to include in the context."),
    show_paths: bool = typer.Option(False, "--show-paths", help="Print saved paths of evidence files."),
    no_save: bool = typer.Option(False, "--no-save", help="Disable saving evidence to disk."),
    allow_disabled: bool = typer.Option(False, "--allow-disabled", help="Allow using disabled agents."),
) -> None:
    """Run a task-less one-shot prompt with a local agent."""
    import sys
    prompt_text = ""
    if stdin:
        prompt_text = sys.stdin.read()
    elif prompt_file:
        try:
            prompt_text = Path(prompt_file).read_text(encoding="utf-8")
        except Exception as exc:
            typer.echo(f"Error: Failed to read prompt-file: {exc}", err=True)
            raise typer.Exit(code=1)
    elif prompt:
        prompt_text = prompt
    else:
        typer.echo("Error: One of --prompt, --prompt-file, or --stdin is required.", err=True)
        raise typer.Exit(code=1)

    from devflow.control_room.agent_terminal import AgentTerminalRunner
    runner = AgentTerminalRunner(repo_root=Path.cwd(), agent_name=agent, allow_disabled=allow_disabled)
    runner.run_one_shot(
        command="run",
        prompt=prompt_text,
        file_to_include=file,
        no_save=no_save,
        show_paths=show_paths,
        include_project=project,
    )


@df_app.command("chat")
def df_chat(
    agent: str = typer.Option("qwopus-implementer", "--agent", help="The local agent name."),
    no_save: bool = typer.Option(False, "--no-save", help="Disable saving transcript to disk."),
    allow_disabled: bool = typer.Option(False, "--allow-disabled", help="Allow using disabled agents."),
) -> None:
    """Start an interactive chat session with a local agent."""
    from devflow.control_room.agent_terminal import AgentTerminalRunner
    runner = AgentTerminalRunner(repo_root=Path.cwd(), agent_name=agent, allow_disabled=allow_disabled)
    runner.run_chat(no_save=no_save)


def df_main() -> None:
    df_app()


def qwopus_main() -> None:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description="Direct qwopus shortcut mapping to qwopus-implementer.")
    parser.add_argument("prompt_or_cmd", nargs="*", default=None, help="The prompt or 'chat' command.")
    parser.add_argument("--project", action="store_true", help="Include compact project context.")
    parser.add_argument("--file", help="An optional file to include.")
    parser.add_argument("--show-paths", action="store_true", help="Show saved evidence file paths.")
    parser.add_argument("--no-save", action="store_true", help="Disable saving evidence or transcript.")
    parser.add_argument("--allow-disabled", action="store_true", help="Allow using disabled agent.")

    args = parser.parse_args()

    if not args.prompt_or_cmd:
        # Check if stdin is not a tty. In this case, we read from stdin as the prompt!
        if not sys.stdin.isatty():
            prompt_text = sys.stdin.read().strip()
            if prompt_text:
                from devflow.control_room.agent_terminal import AgentTerminalRunner
                runner = AgentTerminalRunner(
                    repo_root=Path.cwd(),
                    agent_name="qwopus-implementer",
                    allow_disabled=args.allow_disabled,
                )
                runner.run_one_shot(
                    command="ask",
                    prompt=prompt_text,
                    file_to_include=args.file,
                    no_save=args.no_save,
                    show_paths=args.show_paths,
                    include_project=args.project,
                )
                return
        print(
            "Error: prompt is required.\n\n"
            "Try:\n"
            "  df ask \"your prompt\"\n"
            "  qwopus \"your prompt\"\n"
            "  qwopus chat\n"
            "  df quick",
            file=sys.stderr,
        )
        sys.exit(1)

    from devflow.control_room.agent_terminal import AgentTerminalRunner
    runner = AgentTerminalRunner(
        repo_root=Path.cwd(),
        agent_name="qwopus-implementer",
        allow_disabled=args.allow_disabled,
    )

    if len(args.prompt_or_cmd) == 1 and args.prompt_or_cmd[0] == "chat" and not args.project:
        runner.run_chat(no_save=args.no_save)
    else:
        prompt_text = " ".join(args.prompt_or_cmd)
        runner.run_one_shot(
            command="ask",
            prompt=prompt_text,
            file_to_include=args.file,
            no_save=args.no_save,
            show_paths=args.show_paths,
            include_project=args.project,
        )


@map_app.command("init")
def map_init_command(
    force: bool = typer.Option(False, "--force", help="Overwrite an existing CODE_MAP.md."),
) -> None:
    """Scaffold a blank CODE_MAP.md project orientation file at the repo root."""
    from devflow.control_room.code_map import CodeMapError, map_init

    try:
        target = map_init(Path.cwd(), force=force)
    except CodeMapError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Created {target.name}")
    typer.echo(f"path: {target}")
    typer.echo("Edit CODE_MAP.md to describe your repo layout, entry points, and what workers should read first.")


@map_app.command("show")
def map_show_command() -> None:
    """Print the contents of CODE_MAP.md to stdout."""
    from devflow.control_room.code_map import CodeMapError, map_show

    try:
        content = map_show(Path.cwd())
    except CodeMapError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(content, nl=False)


@map_app.command("check")
def map_check_command() -> None:
    """Validate CODE_MAP.md required sections and entry-point paths."""
    from devflow.control_room.code_map import CodeMapError, map_check

    try:
        result = map_check(Path.cwd())
    except CodeMapError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.ok:
        typer.echo("CODE_MAP.md check passed")
        if result.checked_paths:
            typer.echo("checked entry points:")
            for path in result.checked_paths:
                typer.echo(f"  - {path}")
        return

    typer.echo("CODE_MAP.md check failed", err=True)
    if result.missing_sections:
        typer.echo("missing sections:", err=True)
        for section in result.missing_sections:
            typer.echo(f"  - {section}", err=True)
    if result.unfilled_sections:
        typer.echo("unfilled sections:", err=True)
        for section in result.unfilled_sections:
            typer.echo(f"  - {section}", err=True)
    if result.broken_paths:
        typer.echo("broken entry-point paths:", err=True)
        for path in result.broken_paths:
            typer.echo(f"  - {path}", err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":
    main()
