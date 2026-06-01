from __future__ import annotations

from pathlib import Path
import json
import os

def _enforce_experimental(cmd_name: str) -> None:
    if os.getenv("DEVFLOW_EXPERIMENTAL") != "1":
        typer.echo(f"Error: Command '{cmd_name}' is experimental and restricted to transition planning aids.", err=True)
        typer.echo("To run this command, please set the environment variable DEVFLOW_EXPERIMENTAL=1.", err=True)
        raise typer.Exit(code=1)


import typer

from devflow.control_room.dashboard import run_dashboard
from devflow.control_room.service import (
    create_task,
    doctor,
    get_task,
    init_control_room,
    promotion_readiness_errors,
    run_local_model_task,
    run_shell_task,
    verify_task,
    apply_task_patch,
)
from devflow.control_room.patch_applier import (
    PatchError,
    PatchSelectionError,
    PatchParseError,
    PatchApplicationError,
)
from devflow.control_room.reconciliation import build_reconciliation_report

from devflow.control_room.status_projection import build_task_status_projection, list_task_status_projections
from devflow.control_room.models import TaskRecord
from devflow.control_room.supervisor import DEFAULT_WORKER_COMMAND, supervise_once, supervise_poll
from devflow.control_room.token_context import write_context_packet
from devflow.control_room.worker_adapter import UnsupportedWorkerAdapter, get_worker_adapter
from devflow.control_room.agent_registry import load_agent_registry, AgentRegistryError
from devflow.control_room.task_packet import build_agent_packet
from devflow.control_room.git_worktree import (
    GitWorktreeError,
    archive_devflow_branch,
    cleanup_task_git_resources,
    list_devflow_branches,
    list_devflow_worktrees,
    prune_orphan_worktrees,
)


app = typer.Typer(help="Dev-Flow local control room")
task_app = typer.Typer(help="Manage control-room tasks")
agent_app = typer.Typer(help="Manage and inspect agents")
worktree_app = typer.Typer(help="Inspect and clean Dev-Flow Git worktrees")
branch_app = typer.Typer(help="Inspect and archive Dev-Flow Git branches")
app.add_typer(task_app, name="task")
app.add_typer(agent_app, name="agent")
app.add_typer(worktree_app, name="worktree")
app.add_typer(branch_app, name="branch")

TRUSTED_LOCAL_WARNING = "Security: shell execution is path-isolated, not sandboxed; run only trusted local commands."


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
    strict: bool = typer.Option(False, "--strict", help="Enforce strict production readiness checks.")
) -> None:
    """Check local control-room runtime readiness."""
    root = Path.cwd()
    if strict:
        typer.echo(TRUSTED_LOCAL_WARNING)
    checks = doctor(root, strict=strict)
    failed = False
    for name, ok, detail in checks:
        marker = "ok" if ok else "missing"
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
def dashboard_command(refresh_seconds: int = typer.Option(0, "--refresh-seconds", min=0)) -> None:
    """Render the text-only terminal dashboard."""
    run_dashboard(refresh_seconds=refresh_seconds)


@app.command(
    "supervise",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    hidden=os.getenv("DEVFLOW_EXPERIMENTAL") != "1",
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
    hidden=os.getenv("DEVFLOW_EXPERIMENTAL") != "1",
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
    typer.echo(f"Wrote {_relative(plan.repo_root, plan.packet_path)}")
    typer.echo(f"mode: {plan.context_mode}")
    typer.echo(f"recommended_tools: {', '.join(plan.recommended_tools)}")
    typer.echo(f"events: {_relative(plan.repo_root, plan.events_path)}")


@task_app.command("create")
def task_create(
    title: str,
    git_worktree: bool = typer.Option(False, "--git-worktree", help="Create a Git branch/worktree-backed worker lane."),
) -> None:
    """Create a task and its artifact directory."""
    try:
        task = create_task(Path.cwd(), title, git_worktree=git_worktree)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Created {task.id}: {task.title}")
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
    dry_run: bool = typer.Option(True, "--dry-run/--apply", help="Preview cleanup by default; use --apply to mutate."),
    force: bool = typer.Option(False, "--force", help="Allow cleanup of non-terminal or dirty task resources after review."),
) -> None:
    """Dry-run-first cleanup for one Git worktree-backed task."""
    try:
        actions = cleanup_task_git_resources(Path.cwd(), task_id, dry_run=dry_run, force=force)
    except (KeyError, GitWorktreeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"mode: {'dry-run' if dry_run else 'apply'}")
    typer.echo(f"task: {task_id}")
    _echo_cleanup_actions(actions, dry_run=dry_run)


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
            f"{task.id:<10} {projection.display_status:<20} {projection.verify_token:<16} "
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
    if projection.manual_agent_state:
        typer.echo(f"manual_agent_state: {projection.manual_agent_state}")
        if projection.manual_agent_handoff_path:
            typer.echo(f"manual_agent_handoff: {projection.manual_agent_handoff_path}")
        if projection.manual_agent_result_path:
            typer.echo(f"manual_agent_result: {projection.manual_agent_result_path}")
            typer.echo("manual_agent_note: Dev-Flow verification required before promotion.")
        if projection.manual_agent_question:
            typer.echo(f"manual_agent_question: {projection.manual_agent_question}")
        if projection.manual_agent_failure:
            typer.echo(f"manual_agent_failure: {projection.manual_agent_failure}")
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


@task_app.command(
    "fit",
    hidden=os.getenv("DEVFLOW_EXPERIMENTAL") != "1",
)
def task_fit_command(task_id: str) -> None:
    """[EXPERIMENTAL-READONLY] Deterministic task-fit and context-size estimation."""
    _enforce_experimental("task fit")
    root = Path.cwd()
    try:
        from devflow.control_room.estimator import estimate_task_fit, save_task_fit
        fit_data = estimate_task_fit(root, task_id)
        save_task_fit(root, task_id, fit_data)
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    # Render a beautiful terminal breakdown
    typer.echo(f"Estimated task-fit profile for task: {task_id}")
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
    hidden=os.getenv("DEVFLOW_EXPERIMENTAL") != "1",
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


@task_app.command(
    "scout",
    hidden=os.getenv("DEVFLOW_EXPERIMENTAL") != "1",
)
def task_scout_command(task_id: str, role: str) -> None:
    """[EXPERIMENTAL-READONLY] Run local scout roles to gather routing evidence and analyze risks."""
    _enforce_experimental("task scout")
    root = Path.cwd()
    roles_to_run = []
    if role == "all":
        roles_to_run = ["repo_scope", "risk", "context", "test", "stale_context"]
    else:
        roles_to_run = [role]

    try:
        from devflow.control_room.scout import run_scout_report, save_scout_report
        reports = {}
        for r in roles_to_run:
            data = run_scout_report(root, task_id, r)
            save_scout_report(root, task_id, r, data)
            reports[r] = data["scout_report"]
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    # Render beautiful breakdown
    typer.echo(f"Executed scout evaluation for task: {task_id}")
    for r in roles_to_run:
        sr = reports[r]
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

        typer.echo(f"Wrote scout-{r}.yaml under .devflow/tasks/{task_id}/")
    typer.echo("-" * 50)


@task_app.command(
    "route",
    hidden=os.getenv("DEVFLOW_EXPERIMENTAL") != "1",
)
def task_route_command(task_id: str) -> None:
    """[EXPERIMENTAL-READONLY] Run conservative routing matching to assign agent roles to a task."""
    _enforce_experimental("task route")
    root = Path.cwd()
    try:
        from devflow.control_room.router import route_task, save_routing_decision
        decision_data = route_task(root, task_id)
        save_routing_decision(root, task_id, decision_data)
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    # Render beautiful breakdown
    typer.echo(f"Executed routing mapping for task: {task_id}")
    typer.echo("-" * 50)

    rd = decision_data["routing_decision"]
    typer.echo(f"Policy Version:              {rd['policy_version']}")

    typer.echo("")
    typer.echo("Selected Agent Assignments:")
    selected = rd["selected"]
    for key in sorted(selected.keys()):
        typer.echo(f"  {key:<12}: {selected[key]}")

    typer.echo("")
    typer.echo("Recorded Reasons:")
    for reason in rd["reason"]:
        typer.echo(f"  - {reason}")

    typer.echo("")
    typer.echo("Rejected Agents:")
    rejected = rd["rejected"]
    if not rejected:
        typer.echo("  - none")
    else:
        for rej in rejected:
            typer.echo(f"  - agent:  {rej['agent']}")
            typer.echo(f"    reason: {rej['reason']}")

    typer.echo("-" * 50)
    typer.echo(f"Wrote routing-decision.yaml under .devflow/tasks/{task_id}/")


@task_app.command(
    "scorecard",
    hidden=os.getenv("DEVFLOW_EXPERIMENTAL") != "1",
)
def task_scorecard_command(task_id: str) -> None:
    """[EXPERIMENTAL-READONLY] Compile and display a task's post-run routing quality scorecard."""
    _enforce_experimental("task scorecard")
    root = Path.cwd()
    try:
        from devflow.control_room.scorecard import generate_scorecard, save_scorecard
        scorecard_data = generate_scorecard(root, task_id)
        save_scorecard(root, task_id, scorecard_data)
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    # Render beautiful scorecard breakdown
    typer.echo(f"Compiled routing-quality scorecard for task: {task_id}")
    typer.echo("-" * 50)

    sc = scorecard_data["scorecard"]
    typer.echo(f"Overall Quality Rating:     {_format_scorecard_rating(sc['overall_quality_rating'])}")
    typer.echo(f"First-Run Verification Pass: {_format_scorecard_flag(sc['first_run_pass'])}")
    typer.echo(f"Boundary Violations:        {_format_scorecard_flag(sc['boundary_violations'])}")
    typer.echo(f"Frontier Escalation Needed: {_format_scorecard_flag(sc['frontier_escalation_needed'])}")
    if "frontier_escalation_avoided" in sc:
        typer.echo(f"Frontier Escalation Avoided: {_format_scorecard_flag(sc['frontier_escalation_avoided'])}")
    typer.echo(f"Context Ceiling Exceeded:   {_format_scorecard_flag(sc['context_limit_exceeded'])}")
    typer.echo(f"Review Mistakes Found:      {_format_scorecard_flag(sc['review_mistakes_found'])}")
    typer.echo(f"Latency:                    {sc['latency_seconds']} seconds")
    typer.echo(f"Cost Avoided:               {_format_scorecard_cost(sc['cost_avoided_usd'])}")

    typer.echo("-" * 50)
    typer.echo(f"Wrote scorecard.yaml under .devflow/tasks/{task_id}/")


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


@task_app.command("local")
def task_local(
    task_id: str,
    worker: str | None = typer.Option(None, "--worker", help="Local Ollama worker name."),
    agent: str | None = typer.Option(None, "--agent", help="Local Ollama agent name (alias for --worker)."),
    input_worker: str | None = typer.Option(None, "--input-worker", help="Prior local worker output to review."),
    timeout_seconds: int | None = typer.Option(None, "--timeout-seconds", min=1),
) -> None:
    """Run a first-class local Ollama worker for a task."""
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

    # Beautiful Cost-Saving ladder output
    typer.echo("-" * 50)
    typer.echo("Local AI Cost-Saving Worker Loop Evidence Captured!")
    typer.echo(f"  Agent:             {resolved_worker}")
    typer.echo(f"  Model:             {result.model}")
    typer.echo(f"  Status:            {result.status}")
    typer.echo(f"  Run ID:            {result.run_id}")
    typer.echo(f"  Evidence Dir:      {_relative(Path.cwd(), result.artifact_dir)}")
    typer.echo(f"  Prompt evidence:   {_relative(Path.cwd(), result.prompt_path)}")
    typer.echo(f"  Response evidence: {_relative(Path.cwd(), result.response_path)}")
    typer.echo(f"  Run Metadata:      {_relative(Path.cwd(), result.run_json_path)}")
    typer.echo("-" * 50)

    # Standard compatibility outputs
    typer.echo(f"{task_id}: {result.status}")
    typer.echo(f"local_worker: {resolved_worker}")
    typer.echo(f"model: {result.model}")
    typer.echo(f"run_id: {result.run_id}")
    typer.echo(f"evidence_dir: {_relative(Path.cwd(), result.artifact_dir)}")
    typer.echo(f"prompt_path: {_relative(Path.cwd(), result.prompt_path)}")
    typer.echo(f"raw_response_path: {_relative(Path.cwd(), result.raw_response_path)}")
    typer.echo(f"response_path: {_relative(Path.cwd(), result.response_path)}")
    typer.echo(f"stderr_path: {_relative(Path.cwd(), result.stderr_path)}")
    typer.echo(f"local_worker_run: {_relative(Path.cwd(), result.run_json_path)}")

    if result.error_message:
        typer.echo(result.error_message)

    if result.status == "success":
        typer.echo("")
        typer.echo("Local Cost-Saving Ladder:")
        typer.echo("  1. Planner stage:    devflow task local <task-id> --agent qwen-planner")
        typer.echo("  2. Implementer:      devflow task local <task-id> --agent qwopus-implementer  [Preferred]")
        typer.echo("                       (or fallback --agent qwen-implementer)")
        typer.echo("  3. Reviewer stage:   devflow task local <task-id> --agent gemma-reviewer")
        typer.echo("  4. Verification:     devflow task verify <task-id> --shell \"<command>\"")
        typer.echo("  5. Frontier:         Escalate to Copilot/frontier only if local evidence is insufficient, risky, contradictory, or verification repeatedly fails.")

        if resolved_worker == "qwen-planner":
            typer.echo("")
            typer.echo("Suggested Next Action:")
            typer.echo("  Draft implementation patch using qwopus-implementer:")
            typer.echo(f"    devflow task local {task_id} --agent qwopus-implementer")
        elif resolved_worker in ("qwopus-implementer", "qwen-implementer"):
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


@task_app.command("run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def task_run(
    ctx: typer.Context,
    task_id: str,
    worker: str = typer.Option("shell", "--worker"),
    shell_command: str | None = typer.Option(None, "--shell"),
    timeout_seconds: int = typer.Option(60, "--timeout-seconds"),
) -> None:
    """Run a task with a worker command after '--'."""
    if worker == "manual":
        typer.echo("Warning: 'manual' worker is experimental and does not execute work.")
    elif worker == "shell":
        typer.echo(TRUSTED_LOCAL_WARNING)
    from devflow.control_room.agent_registry import load_agent_registry
    from devflow.control_room.worker_adapter import list_worker_adapters, UnsupportedWorkerAdapter

    registry = load_agent_registry(Path.cwd())
    valid_agents = list(registry.agents.keys())
    valid_adapters = list_worker_adapters()

    if worker not in valid_agents:
        from devflow.control_room.worker_adapter import get_worker_adapter
        try:
            get_worker_adapter(worker)
        except UnsupportedWorkerAdapter as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc

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
    handoff_path = Path.cwd() / ".devflow" / "tasks" / task.id / "agents" / worker / "handoff.md"
    if handoff_path.exists():
        typer.echo(f"manual_handoff_path: {_relative(Path.cwd(), handoff_path)}")
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


@task_app.command("apply-patch")
def task_apply_patch(
    task_id: str,
    agent: str | None = typer.Option(None, "--agent", help="The specific agent's patch to apply."),
) -> None:
    """Apply a proposed patch from a worker agent to the isolated task workspace."""
    root = Path.cwd()
    try:
        task = apply_task_patch(root, task_id, agent_id=agent)

        # Retrieve the latest patch_applied event to print details
        task_path = root / ".devflow" / "tasks" / task.id
        events_file = task_path / "events.jsonl"
        patch_hash = "unknown"
        patch_evidence_path = None
        agent_id = agent or "default"
        changed_files = []
        if events_file.exists():
            for line in events_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    evt = json.loads(line)
                    if evt.get("event") == "patch_applied":
                        patch_hash = evt.get("patch_hash", "unknown")
                        patch_evidence_path = evt.get("patch_evidence_path")
                        agent_id = evt.get("agent_id", agent_id)
                        changed_files = evt.get("changed_files", [])
                except Exception:
                    pass

        typer.echo(f"Successfully applied patch from agent '{agent_id}' to task workspace '{task.id}'.")
        typer.echo(f"Workspace: .devflow/workspaces/{task.id}")
        typer.echo(f"Patch Hash: {patch_hash}")
        if patch_evidence_path:
            typer.echo(f"Patch Evidence: {patch_evidence_path}")
        typer.echo("")
        typer.echo("Modified files:")
        for cf in changed_files:
            typer.echo(f"  - {cf['path']} ({cf['operation']})")
        typer.echo("")
        typer.echo("Next:")
        typer.echo(f"  devflow task verify {task.id} --shell \"<command>\"")

    except (PatchError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


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
    renamed = res.get("renamed", [])
    untracked = res.get("untracked", [])
    binary = res.get("binary", [])
    diffs = res["diffs"]
    baseline = res["baseline"]
    git_preview = res.get("git")

    typer.echo(f"task_baseline_commit: {baseline['task_baseline_commit'] or 'unavailable'}")
    typer.echo(f"current_main_head: {baseline['current_main_head'] or 'unavailable'}")
    typer.echo(f"baseline_status: {baseline['baseline_status']}")
    if git_preview:
        typer.echo(f"task_id: {git_preview['task_id']}")
        typer.echo(f"worker_id: {git_preview['worker_id']}")
        typer.echo(f"base_commit: {git_preview['base_commit'] or 'unavailable'}")
        typer.echo(f"main_current_head: {git_preview['main_current_head'] or 'unavailable'}")
        typer.echo(f"worker_branch: {git_preview['worker_branch']}")
        typer.echo(f"worker_branch_head: {git_preview['worker_branch_head'] or 'unavailable'}")
        typer.echo(f"merge_base: {git_preview['merge_base'] or 'unavailable'}")
        typer.echo(f"baseline_stale: {'yes' if git_preview['baseline_stale'] else 'no'}")
        typer.echo(f"conflict_prediction: {git_preview['conflict_prediction']}")
        typer.echo(f"verification_status: {git_preview['verification_status']}")
        typer.echo(f"promotion_readiness: {git_preview['promotion_readiness']}")

    if not added and not modified and not deleted and not renamed and not untracked and not binary:
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

    if renamed:
        typer.echo("Renamed files:")
        for item in renamed:
            typer.echo(f"  - {item['from']} -> {item['to']}")
        typer.echo()

    if untracked:
        typer.echo("Untracked files:")
        for name in untracked:
            typer.echo(f"  - {name}")
        typer.echo()

    if binary:
        typer.echo("Binary files:")
        for name in binary:
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
    force_stale_baseline: bool = typer.Option(
        False,
        "--force-stale-baseline",
        help="Bypass the stale task-baseline guard after manual conflict review.",
    ),
    apply_deletions: bool = typer.Option(False, "--apply-deletions", help="Apply file deletions to the main checkout."),
) -> None:
    """Promote verified changes from the isolated workspace to the main checkout."""
    try:
        from devflow.control_room.service import (
            format_promotion_refusal,
            format_stale_baseline_refusal,
            get_task,
            main_checkout_has_uncommitted_changes,
            preview_task_promotion,
            promote_task,
            promotion_baseline,
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

        baseline = promotion_baseline(Path.cwd(), task)
        if baseline["baseline_status"] == "unavailable":
            typer.echo(format_stale_baseline_refusal(Path.cwd(), task), err=True)
            raise typer.Exit(code=1)
        if baseline["baseline_status"] == "changed":
            if not force_stale_baseline:
                typer.echo(format_stale_baseline_refusal(Path.cwd(), task), err=True)
                raise typer.Exit(code=1)
            typer.echo("Warning: Forcing promotion with stale task baseline.")
            typer.echo(f"task_baseline_commit: {baseline['task_baseline_commit'] or 'unavailable'}")
            typer.echo(f"current_main_head: {baseline['current_main_head'] or 'unavailable'}")

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
    renamed = res.get("renamed", [])
    untracked = res.get("untracked", [])
    binary = res.get("binary", [])
    diffs = res["diffs"]

    if not added and not modified and not deleted and not renamed and not untracked and not binary:
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

    if renamed:
        typer.echo("Renamed files:")
        for item in renamed:
            typer.echo(f"  - {item['from']} -> {item['to']}")
        typer.echo()

    if untracked:
        typer.echo("Untracked files:")
        for name in untracked:
            typer.echo(f"  - {name}")
        typer.echo()

    if binary:
        typer.echo("Binary files:")
        for name in binary:
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
        promote_task(
            Path.cwd(),
            task_id,
            force=force,
            apply_deletions=apply_deletions,
            force_stale_baseline=force_stale_baseline,
        )
    except Exception as exc:
        typer.echo(f"Error executing promotion: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("Promotion complete.")
    if deleted:
        if apply_deletions:
            typer.echo(f"Applied deletions: {len(deleted)} file(s) removed.")
        else:
            typer.echo("Warning: Deletions are preview-only and were not applied (deletions are deferred). Use --apply-deletions to apply them.")


@task_app.command("open")
def task_open(
    task_id: str = typer.Argument(..., help="The task ID (e.g. task-0002)."),
    worker: str | None = typer.Option(None, "--worker", help="Prefer output files for this local worker."),
    raw: bool = typer.Option(False, "--raw", help="Prefer raw response/output files."),
    list_candidates: bool = typer.Option(False, "--list", help="Print candidate output files in priority order and exit."),
) -> None:
    """Open the most relevant task output artifact."""
    import fnmatch
    import sys
    import subprocess
    from devflow.control_room.service import get_task
    from devflow.control_room.paths import workspaces_dir

    root = Path.cwd()

    try:
        task = get_task(root, task_id)
    except KeyError:
        typer.echo(f"Error: Task '{task_id}' not found.", err=True)
        raise typer.Exit(code=1)

    workspace = (workspaces_dir(root) / task_id).resolve()
    if not workspace.exists() or not workspace.is_dir():
        typer.echo(f"Error: Task workspace not found at {workspace}", err=True)
        raise typer.Exit(code=1)

    all_candidate_files: list[Path] = []
    for p in workspace.rglob("*"):
        if p.is_file():
            try:
                p.resolve().relative_to(workspace)
                all_candidate_files.append(p)
            except ValueError:
                continue

    def get_sort_key(p: Path) -> tuple[int, int, str]:
        rel_path = p.relative_to(workspace).as_posix()
        rel_path_lower = rel_path.lower()
        name = p.name.lower()
        parts = rel_path_lower.split("/")

        primary_rank = 3
        if worker:
            worker_lower = worker.lower()
            if len(parts) >= 3 and parts[0] == "local-workers" and parts[1] == worker_lower:
                if name == "response.raw.md":
                    primary_rank = 0 if raw else 1
                elif name == "response.md":
                    primary_rank = 1 if raw else 0
                else:
                    primary_rank = 2

        if raw:
            patterns = [
                "local-workers/*/response.raw.md",
                "local-workers/*/response.md",
                "*response.raw.md",
                "*response*.md",
                "*review*.md",
                "*.log",
                "*.md",
                "*.txt",
            ]
        else:
            patterns = [
                "local-workers/*/response.md",
                "local-workers/*/response.raw.md",
                "*response.md",
                "*review.md",
                "*.md",
                "*.txt",
                "logs/*.log",
                "*.log",
            ]

        secondary_rank = len(patterns) + 1
        for idx, pattern in enumerate(patterns):
            if fnmatch.fnmatch(rel_path_lower, pattern) or fnmatch.fnmatch(name, pattern):
                secondary_rank = idx
                break

        return (primary_rank, secondary_rank, rel_path_lower)

    sorted_files = sorted(all_candidate_files, key=get_sort_key)

    valid_candidates = []
    for f in sorted_files:
        key = get_sort_key(f)
        if key[1] < 9:
            valid_candidates.append(f)

    if list_candidates:
        if not valid_candidates:
            typer.echo("No candidate files found.")
            return
        typer.echo("Candidate output files in priority order:")
        for idx, f in enumerate(valid_candidates, start=1):
            rel = f.relative_to(workspace)
            typer.echo(f"{idx}. {rel}")
        return

    if not valid_candidates:
        typer.echo("Error: No candidate output files found in task workspace.", err=True)
        raise typer.Exit(code=1)

    top_candidate = valid_candidates[0]

    opened = False
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(top_candidate)], check=True)
            opened = True
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(top_candidate)], check=True)
            opened = True
        elif sys.platform == "win32":
            if hasattr(os, "startfile"):
                os.startfile(str(top_candidate))
                opened = True
    except Exception:
        pass

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
    import json
    import fnmatch
    from devflow.control_room.service import get_task
    from devflow.control_room.paths import workspaces_dir, task_dir

    root = Path.cwd()

    try:
        task = get_task(root, task_id)
    except KeyError:
        typer.echo(f"Error: Task '{task_id}' not found.", err=True)
        raise typer.Exit(code=1)

    workspace = (workspaces_dir(root) / task_id).resolve()
    if not workspace.exists() or not workspace.is_dir():
        typer.echo(f"Error: Task workspace not found at {workspace}", err=True)
        raise typer.Exit(code=1)

    if local:
        _render_local_evidence_summary(root, task_id, workspace)
        return

    # 1. Print Task ID and Title
    typer.echo(f"Task: {task.id} {task.title}")

    # 2. Print Task Status
    typer.echo(f"Status: {task.status}")
    typer.echo()

    # 3. Retrieve and print Verification status
    v_status = task.verification_status or "not_run"
    v_command = task.verification_command
    v_exit_code = task.verification_exit_code

    # Check if verification.json exists
    t_dir = task_dir(root, task_id)
    v_json_path = t_dir / "verification.json"
    if v_json_path.exists():
        try:
            v_data = json.loads(v_json_path.read_text(encoding="utf-8"))
            if isinstance(v_data, dict) and v_data.get("task_id") == task_id:
                v_status = v_data.get("status", v_status)
                v_command = v_data.get("command", v_command)
                v_exit_code = v_data.get("exit_code", v_exit_code)
        except Exception:
            pass

    typer.echo("Verification:")
    if v_status == "passed":
        typer.echo(f"  passed  {v_command or ''}")
    elif v_status == "failed":
        exit_suffix = f" (exit={v_exit_code})" if v_exit_code is not None else ""
        typer.echo(f"  failed{exit_suffix}  {v_command or ''}")
    else:
        typer.echo("  not_run")
    typer.echo()

    # 4. Search and parse local worker runs
    local_workers_dir = workspace / "local-workers"
    worker_runs = []
    failed_workers = []
    timeout_workers = []
    missing_inputs = []

    if local_workers_dir.exists() and local_workers_dir.is_dir():
        for worker_subdir in sorted(local_workers_dir.iterdir()):
            if not worker_subdir.is_dir():
                continue
            run_json = worker_subdir / "run.json"
            if run_json.exists():
                try:
                    run_data = json.loads(run_json.read_text(encoding="utf-8"))
                    if isinstance(run_data, dict):
                        worker_name = run_data.get("worker_name", worker_subdir.name)
                        model = run_data.get("model", "unknown")
                        status = run_data.get("status", "unknown")
                        duration = run_data.get("duration_seconds", 0.0)
                        resp_path = run_data.get("response_path", f"local-workers/{worker_subdir.name}/response.md")

                        # Store run info
                        worker_runs.append({
                            "name": worker_name,
                            "model": model,
                            "status": status,
                            "duration": duration,
                            "response_path": resp_path,
                        })

                        # Collect potential warning contexts
                        if status == "failed":
                            failed_workers.append(worker_name)
                        elif status == "timeout":
                            timeout_workers.append(worker_name)

                        # Check for missing input in run.json error_message
                        err_msg = run_data.get("error_message") or ""
                        if "Missing input worker output" in err_msg:
                            missing_inputs.append(worker_name)
                except Exception:
                    pass

    if worker_runs:
        typer.echo("Local workers:")
        for r in worker_runs:
            resp_name = Path(r["response_path"]).name
            duration_str = f"{int(round(r['duration']))}s"
            typer.echo(f"  {r['name']:<16}  {r['status']:<8}  {duration_str:>4}  {resp_name}")
        typer.echo()

    # 5. Discover Useful Artifacts
    all_candidate_files = []
    for p in workspace.rglob("*"):
        if p.is_file():
            try:
                # Path resolution traversal safety
                p.resolve().relative_to(workspace)
                all_candidate_files.append(p)
            except ValueError:
                continue

    def get_sort_key(p: Path) -> tuple[int, str]:
        rel_path = p.relative_to(workspace).as_posix()
        rel_path_lower = rel_path.lower()
        name = p.name.lower()

        patterns = [
            "local-workers/*/response.md",
            "local-workers/*/response.raw.md",
            "*response.md",
            "*review.md",
            "*.md",
            "*.txt",
            "logs/*.log",
            "*.log",
        ]

        for idx, pattern in enumerate(patterns):
            if fnmatch.fnmatch(rel_path_lower, pattern) or fnmatch.fnmatch(name, pattern):
                return (idx, rel_path_lower)
        return (len(patterns), rel_path_lower)

    sorted_files = sorted(all_candidate_files, key=get_sort_key)
    valid_candidates = []
    for f in sorted_files:
        key = get_sort_key(f)
        if key[0] < 8:
            valid_candidates.append(f)

    if valid_candidates:
        typer.echo("Artifacts:")
        for f in valid_candidates[:10]:
            typer.echo(f"  {_relative(root, f)}")
        typer.echo()

    # 6. Warnings
    warnings = []
    for w in failed_workers:
        warnings.append(f"failed worker run: {w}")
    for w in timeout_workers:
        warnings.append(f"timeout worker run: {w}")
    for w in missing_inputs:
        warnings.append(f"missing input-worker output for: {w}")
    if v_status != "passed":
        warnings.append("unverified task")

    if warnings:
        typer.echo("Warnings:")
        for w in warnings:
            typer.echo(f"  - {w}")
        typer.echo()

    # 7. Recommended next action & Suggested next commands
    typer.echo("Recommended next action:")
    if v_status == "passed":
        if any(w["name"] == "gemma-reviewer" and w["status"] == "success" for w in worker_runs):
            typer.echo("  review gemma-reviewer response, then handoff to Codex")
        else:
            typer.echo(f"  review promotion preview, then run 'devflow task promote {task_id}'")
    else:
        if v_status == "failed":
            typer.echo(f"  fix the failure and re-run verification using 'devflow task verify {task_id} -- <command>'")
        else:
            typer.echo(f"  verify the task using 'devflow task verify {task_id} -- <command>'")

    typer.echo()
    typer.echo("Suggested next commands:")
    typer.echo(f"  devflow task open {task_id}")
    if worker_runs:
        latest_worker = worker_runs[-1]["name"]
        typer.echo(f"  devflow task open {task_id} --worker {latest_worker}")
    if v_status != "passed":
        typer.echo(f"  devflow task verify {task_id} -- <command>")
    else:
        typer.echo(f"  devflow task promote-preview {task_id}")


_LOCAL_WORKER_DISPLAY_ORDER = (
    "qwen-planner",
    "qwopus-implementer",
    "qwen-implementer",
    "gemma-reviewer",
)


def _render_local_evidence_summary(root: Path, task_id: str, workspace: Path) -> None:
    summaries = _collect_local_worker_summaries(root, workspace)

    typer.echo(f"Local runs for {task_id}")
    typer.echo()

    if not summaries:
        typer.echo("No local AI evidence found.")
        typer.echo()
        typer.echo("Recommendation:")
        typer.echo("  No local AI evidence found.")
        return

    for summary in summaries:
        typer.echo(summary["worker_name"])
        typer.echo(f"  latest run: {summary['run_id']}")
        typer.echo(f"  status: {summary['status']}")
        typer.echo(f"  exit code: {summary['exit_code']}")
        typer.echo(f"  model: {summary['model']}")
        typer.echo(f"  evidence: {summary['evidence_path']}")
        typer.echo(f"  response: {summary['response_path']}")
        typer.echo(f"  completed: {summary['completed_at']}")
        if summary.get("reviewed_worker"):
            reviewed = summary["reviewed_worker"]
            reviewed_source = summary.get("reviewed_source")
            if reviewed_source:
                reviewed = f"{reviewed} ({reviewed_source})"
            typer.echo(f"  reviewed: {reviewed}")
        typer.echo()

    typer.echo("Recommendation:")
    for line in _local_evidence_recommendations(summaries):
        typer.echo(f"  {line}")


def _collect_local_worker_summaries(root: Path, workspace: Path) -> list[dict[str, str]]:
    from devflow.control_room.local_ollama_worker import find_latest_worker_evidence

    local_workers_dir = workspace / "local-workers"
    if not local_workers_dir.exists() or not local_workers_dir.is_dir():
        return []

    try:
        worker_names = sorted(
            {child.name for child in local_workers_dir.iterdir() if child.is_dir()},
            key=_local_worker_sort_key,
        )
    except OSError:
        return []

    summaries: list[dict[str, str]] = []
    for worker_name in worker_names:
        evidence_dir, response_path = find_latest_worker_evidence(workspace, worker_name)
        if evidence_dir is None or response_path is None:
            continue

        run_json_path = evidence_dir / "run.json"
        run_data = _read_json_mapping(run_json_path)
        reviewed_worker, reviewed_source = _reviewed_input_from_metadata(evidence_dir, run_data)

        summary = {
            "worker_name": _string_metadata(run_data, "worker_name", worker_name),
            "run_id": _local_run_id(evidence_dir, run_data),
            "status": _string_metadata(run_data, "status"),
            "exit_code": _exit_code_metadata(run_data),
            "model": _string_metadata(run_data, "model"),
            "evidence_path": _metadata_path(root, workspace, run_data.get("evidence_path"), evidence_dir),
            "response_path": _metadata_path(root, workspace, run_data.get("response_path"), response_path),
            "completed_at": _completion_metadata(run_data),
        }
        if reviewed_worker:
            summary["reviewed_worker"] = reviewed_worker
        if reviewed_source:
            summary["reviewed_source"] = reviewed_source
        summaries.append(summary)

    return summaries


def _local_worker_sort_key(worker_name: str) -> tuple[int, str]:
    try:
        return (_LOCAL_WORKER_DISPLAY_ORDER.index(worker_name), "")
    except ValueError:
        return (len(_LOCAL_WORKER_DISPLAY_ORDER), worker_name)


def _read_json_mapping(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _string_metadata(run_data: dict[str, object], key: str, default: str = "unknown") -> str:
    value = run_data.get(key)
    return value if isinstance(value, str) and value else default


def _exit_code_metadata(run_data: dict[str, object]) -> str:
    if "exit_code" not in run_data:
        return "unknown"
    value = run_data.get("exit_code")
    return "none" if value is None else str(value)


def _completion_metadata(run_data: dict[str, object]) -> str:
    for key in ("completed_at", "finished_at"):
        value = run_data.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _local_run_id(evidence_dir: Path, run_data: dict[str, object]) -> str:
    run_id = run_data.get("run_id")
    if isinstance(run_id, str) and run_id:
        return run_id
    if evidence_dir.name.startswith("run_"):
        return evidence_dir.name
    return "legacy"


def _metadata_path(root: Path, workspace: Path, value: object, fallback: Path) -> str:
    if isinstance(value, str) and value.strip():
        raw_path = value.strip()
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            if raw_path.startswith("local-workers/"):
                candidate = workspace / candidate
            else:
                candidate = root / candidate
        return _relative(root, candidate)
    return _relative(root, fallback)


def _reviewed_input_from_metadata(evidence_dir: Path, run_data: dict[str, object]) -> tuple[str | None, str | None]:
    reviewed_worker = _first_string_metadata(run_data, ("reviewed_worker", "input_worker"))
    reviewed_source = _first_string_metadata(
        run_data,
        ("reviewed_response_path", "input_response_path", "input_worker_output_path"),
    )
    if reviewed_worker and reviewed_source:
        return reviewed_worker, reviewed_source

    prompt_worker, prompt_source = _reviewed_input_from_prompt(evidence_dir / "prompt.md")
    return reviewed_worker or prompt_worker, reviewed_source or prompt_source


def _first_string_metadata(run_data: dict[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = run_data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _reviewed_input_from_prompt(prompt_path: Path) -> tuple[str | None, str | None]:
    if not prompt_path.exists():
        return None, None

    reviewed_worker: str | None = None
    reviewed_source: str | None = None
    try:
        with prompt_path.open("r", encoding="utf-8") as prompt_file:
            for _ in range(200):
                line = prompt_file.readline()
                if not line:
                    break
                stripped = line.strip()
                if not reviewed_worker and stripped.startswith("Input worker:"):
                    reviewed_worker = stripped.split(":", 1)[1].strip() or None
                elif not reviewed_source and stripped.startswith("Source:"):
                    reviewed_source = stripped.split(":", 1)[1].strip() or None
                if reviewed_worker and reviewed_source:
                    break
    except OSError:
        return None, None
    return reviewed_worker, reviewed_source


def _local_evidence_recommendations(summaries: list[dict[str, str]]) -> list[str]:
    worker_names = {summary["worker_name"] for summary in summaries}
    successful_workers = {
        summary["worker_name"]
        for summary in summaries
        if summary.get("status") == "success"
    }

    if "qwopus-implementer" in successful_workers and "gemma-reviewer" in successful_workers:
        lead = "Local implementation + review evidence available."
    elif worker_names == {"qwen-planner"}:
        lead = "Planning evidence exists; implementation evidence is missing."
    else:
        lead = "Use local evidence first; escalate only if outputs are missing, failed, contradictory, or verification fails."

    if lead.startswith("Use local evidence first"):
        return [lead]
    return [
        lead,
        "Use local evidence first; escalate only if outputs are missing, failed, contradictory, or verification fails.",
    ]


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


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _format_scorecard_flag(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown" if value is None or value == "unknown" else str(value)


def _format_scorecard_rating(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value * 100}%"
    return "unknown" if value is None or value == "unknown" else str(value)


def _format_scorecard_cost(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"${value:.2f} USD"
    return "unknown" if value is None or value == "unknown" else str(value)


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


def _echo_list(label: str, values: list[str]) -> None:
    typer.echo(f"{label}:")
    if not values:
        typer.echo("  - none")
        return
    for value in values:
        typer.echo(f"  - {value}")


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


@agent_app.command("list")
def agent_list() -> None:
    """List loaded agents from the registry."""
    try:
        registry = load_agent_registry(Path.cwd())
    except AgentRegistryError as exc:
        typer.echo(f"Error loading agent registry: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    agents = registry.agents
    if not agents:
        typer.echo("No agents defined in registry.")
        return

    typer.echo(f"{'Agent':<25} {'Provider':<15} {'Model':<20} {'Role':<30} {'Enabled':<8}")
    typer.echo("-" * 102)
    for agent_id in sorted(agents.keys()):
        agent = agents[agent_id]
        enabled_str = "yes" if agent.enabled else "no"
        typer.echo(
            f"{agent.id:<25} {agent.provider:<15} {agent.model:<20} {agent.role:<30} {enabled_str:<8}"
        )


@agent_app.command("show")
def agent_show(agent_id: str) -> None:
    """Show details for a specific agent."""
    try:
        registry = load_agent_registry(Path.cwd())
    except AgentRegistryError as exc:
        typer.echo(f"Error loading agent registry: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        agent = registry.require_agent(agent_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"agent: {agent.id}")
    typer.echo(f"provider: {agent.provider}")
    typer.echo(f"model: {agent.model}")
    typer.echo(f"adapter: {agent.adapter}")
    typer.echo(f"role: {agent.role}")
    typer.echo(f"tier: {agent.tier}")
    typer.echo(f"default_mode: {agent.default_mode}")
    typer.echo(f"execution_mode: {agent.execution_mode}")
    typer.echo(f"purpose: {agent.purpose or ''}")
    typer.echo(f"workspace: {agent.workspace}")
    typer.echo(f"can_see: {', '.join(agent.can_see) if agent.can_see else 'none'}")
    typer.echo(f"can_touch: {', '.join(agent.can_touch) if agent.can_touch else 'none'}")
    typer.echo(f"cannot_touch: {', '.join(agent.cannot_touch) if agent.cannot_touch else 'none'}")
    _echo_list("allowed_reads", agent.allowed_reads)
    _echo_list("allowed_writes", agent.allowed_writes)
    _echo_list("forbidden_writes", agent.forbidden_writes)
    _echo_list("required_outputs", agent.required_outputs)
    _echo_list("completion_rules", agent.completion_rules)
    typer.echo(f"can_run_shell: {str(agent.can_run_shell).lower()}")
    typer.echo(f"can_use_network: {str(agent.can_use_network).lower()}")
    typer.echo(f"can_promote: {str(agent.can_promote).lower()}")
    typer.echo(f"enabled: {str(agent.enabled).lower()}")


@agent_app.command("packet")
def agent_packet(task_id: str, agent_id: str) -> None:
    """Build and print a task's TaskPacket bounded by the target agent's permissions."""
    try:
        registry = load_agent_registry(Path.cwd())
    except AgentRegistryError as exc:
        typer.echo(f"Error loading agent registry: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    try:
        agent = registry.require_agent(agent_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    try:
        packet = build_agent_packet(task_id, agent, root=Path.cwd())
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    packet_json = json.dumps(packet.model_dump(mode="json"), sort_keys=True, indent=2)
    typer.echo(packet_json)



if __name__ == "__main__":
    main()
