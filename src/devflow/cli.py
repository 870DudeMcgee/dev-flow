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


app = typer.Typer(help="Dev-Flow local control room")
task_app = typer.Typer(help="Manage control-room tasks")
agent_app = typer.Typer(help="Manage and inspect agents")
app.add_typer(task_app, name="task")
app.add_typer(agent_app, name="agent")

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
    typer.echo(f"Overall Quality Rating:     {sc['overall_quality_rating'] * 100}%")
    typer.echo(f"First-Run Verification Pass:{' yes' if sc['first_run_pass'] else ' no'}")
    typer.echo(f"Boundary Violations:        {' yes' if sc['boundary_violations'] else ' no'}")
    typer.echo(f"Frontier Escalation Needed: {' yes' if sc['frontier_escalation_needed'] else ' no'}")
    typer.echo(f"Context Ceiling Exceeded:   {' yes' if sc['context_limit_exceeded'] else ' no'}")
    typer.echo(f"Review Mistakes Found:      {' yes' if sc['review_mistakes_found'] else ' no'}")
    typer.echo(f"Latency:                    {sc['latency_seconds']} seconds")
    typer.echo(f"Cost Avoided:               ${sc['cost_avoided_usd']:.2f} USD")
    
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
    diffs = res["diffs"]
    baseline = res["baseline"]

    typer.echo(f"task_baseline_commit: {baseline['task_baseline_commit'] or 'unavailable'}")
    typer.echo(f"current_main_head: {baseline['current_main_head'] or 'unavailable'}")
    typer.echo(f"baseline_status: {baseline['baseline_status']}")

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
