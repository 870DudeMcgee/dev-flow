from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os

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
    run_shell_task,
    verify_task,
    apply_task_patch,
)
from devflow.control_room.task_closure import (
    TaskClosureError,
    cleanup_task as cleanup_closed_task,
    closure_next_action,
    close_task,
    read_closure,
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
from devflow.control_room.maintenance import reset_dogfood_state, reset_test_state, repair_state
from devflow.control_room.patch_applier import (
    PatchError,
    PatchSelectionError,
    PatchParseError,
    PatchApplicationError,
)
from devflow.control_room.reconciliation import build_reconciliation_report

from devflow.control_room.status_projection import list_task_status_projections
from devflow.control_room.models import TaskRecord
from devflow.control_room.supervisor import DEFAULT_WORKER_COMMAND, supervise_once, supervise_poll
from devflow.control_room.token_context import write_context_packet
from devflow.control_room.worker_adapter import UnsupportedWorkerAdapter, get_worker_adapter
from devflow.control_room.agent_registry import load_agent_registry, AgentRegistryError
from devflow.control_room.agent_runtime import agent_runtime_contract
from devflow.control_room.task_packet import build_agent_packet
from devflow.control_room.proposal_normalizer import normalize_proposal
from devflow.control_room.patch_dry_run import preview_patch_dry_run
from devflow.control_room.patch_review import normalize_agent_patch_candidate, review_patch_candidate
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
from devflow.control_room.devmode_bridge import detect_devmode, render_devmode_status
from devflow.control_room.git_state import GitStateError, push_main, render_git_status, sync_main
from devflow.control_room.qwopus_evidence import write_qwopus_escalation_packet
from devflow.control_room.review_capsule import export_review_capsule_markdown, render_review_capsule
from devflow.control_room.review_readiness import (
    build_review_readiness_projection,
    render_review_readiness,
    summarize_review_readiness,
)
from devflow.control_room.question_resume import (
    answer_question,
    build_question_snapshot,
    render_question_snapshot,
    resolve_question,
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
from devflow.control_room.project_create import create_project as create_managed_project
from devflow.control_room.project_create import import_project as import_managed_project
from devflow.control_room.project_registry import (
    ProjectRootResolution,
    ProjectRegistryError,
    archive_project,
    doctor_project,
    project_task_ref,
    remove_project,
    render_project_list,
    render_project_show,
    render_project_status,
    resolve_project_root,
    update_project_remote_policy,
)


app = typer.Typer(help="Dev-Flow local control room")
task_app = typer.Typer(help="Manage control-room tasks")
agent_app = typer.Typer(help="Manage and inspect agents")
worktree_app = typer.Typer(help="Inspect and clean Dev-Flow Git worktrees")
branch_app = typer.Typer(help="Inspect and archive Dev-Flow Git branches")
git_app = typer.Typer(help="Inspect guarded Git state")
goal_app = typer.Typer(help="Manage goals and planning scaffolds")
worker_app = typer.Typer(help="Validate worker outcome metadata")
knowledge_app = typer.Typer(help="Capture and curate reusable local knowledge")
idea_app = typer.Typer(help="Capture and review raw ideas before they become goals or tasks")
dogfood_app = typer.Typer(help="Run deterministic Dev-Flow production-readiness dogfood suites")
maintenance_app = typer.Typer(help="Repair or reset ignored Dev-Flow runtime state")
release_app = typer.Typer(help="Inspect milestone release-readiness gates")
supervisor_app = typer.Typer(help="Inspect and operate Dev-Flow through supervisor-safe read-only surfaces")
hermes_app = typer.Typer(help="Inspect Hermes operator integration readiness")
project_app = typer.Typer(help="Create and manage registered projects")
map_app = typer.Typer(help="Project Code Map orientation layer (Milestone 11)")
freshness_app = typer.Typer(help="Detect stale goal/task/document guidance")
scheduler_app = typer.Typer(help="Inspect simple scheduler queue and retry evidence")
question_app = typer.Typer(help="List, answer, and resolve human-blocking worker questions")
operating_layer_app = typer.Typer(help="Local operating-layer UI and supervisor-safe controls")
loop_app = typer.Typer(help="Run durable DevFlow automation loops")
builder_judge_app = typer.Typer(help="Run builder-judge quality-control loops")
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
app.add_typer(project_app, name="project")
app.add_typer(map_app, name="map")
app.add_typer(freshness_app, name="freshness")
app.add_typer(scheduler_app, name="scheduler")
app.add_typer(question_app, name="question")
app.add_typer(operating_layer_app, name="operating-layer")
app.add_typer(loop_app, name="loop")
app.add_typer(builder_judge_app, name="builder-judge")


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


@builder_judge_app.command("run")
def builder_judge_run(
    definition_of_done: str = typer.Option(..., "--dod", "--definition-of-done", help="What does great look like? Be specific."),
    starting_point: str = typer.Option("", "--starting-point", help="Seed text for the builder to start from."),
    builder: str = typer.Option("deepseek-v4-flash-free-brainstormer", "--builder", help="Builder model profile ID."),
    judge: str = typer.Option("glm-5-2-brainstormer", "--judge", help="Judge model profile ID."),
    pass_threshold: int = typer.Option(85, "--threshold", min=50, max=100, help="Pass threshold (0-100)."),
    max_rounds: int = typer.Option(5, "--max-rounds", min=1, max=20, help="Maximum rounds."),
    no_escalate: bool = typer.Option(False, "--no-escalate", help="Don't escalate on max rounds; just stop."),
    json_output: bool = typer.Option(False, "--json", help="Print run as JSON."),
) -> None:
    """Run a builder-judge quality-control loop.

    A builder model writes a draft, a separate adversarial judge model grades it
    0-100 and lists issues, the builder revises, and the loop repeats until the
    score meets the threshold or max rounds is reached.

    Example:

        devflow builder-judge run --dod "A 5-line cold email for agency owners with one CTA"
    """
    from devflow.control_room.builder_judge_loop import (
        BuilderJudgeConfig,
        BuilderJudgeConfigError,
        BuilderJudgeRunError,
        run_builder_judge_loop,
    )

    config = BuilderJudgeConfig(
        definition_of_done=definition_of_done,
        starting_point=starting_point or None,
        builder_profile_id=builder,
        judge_profile_id=judge,
        pass_threshold=pass_threshold,
        max_rounds=max_rounds,
        escalate_on_max_rounds=not no_escalate,
    )
    try:
        run = run_builder_judge_loop(Path.cwd(), config)
    except (BuilderJudgeConfigError, BuilderJudgeRunError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(run.model_dump(mode="json"), indent=2, sort_keys=False))
    else:
        typer.echo(f"Builder-Judge Loop: {run.loop_id}")
        typer.echo(f"  Status: {run.status}")
        typer.echo(f"  Rounds: {len(run.rounds)}/{run.config.max_rounds}")
        for r in run.rounds:
            score = f"{r.score}/100" if r.score is not None else "N/A"
            passed = " ✓ PASSED" if r.passed else ""
            typer.echo(f"    Round {r.round_number}: {score}{passed}")
            for issue in r.issues:
                typer.echo(f"      - {issue}")
        if run.final_score is not None:
            typer.echo(f"  Final score: {run.final_score}/100")
        typer.echo(f"  Stop reason: {run.stop_reason}")
        typer.echo(f"  Next: {run.next_safe_action}")
        if run.evidence_path:
            typer.echo(f"  Evidence: {run.evidence_path}")

    if run.status not in ("passed",):
        raise typer.Exit(code=2)


@builder_judge_app.command("list")
def builder_judge_list(
    json_output: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """List past builder-judge loop runs."""
    from devflow.control_room.builder_judge_loop import list_builder_judge_loops

    loops = list_builder_judge_loops(Path.cwd())
    if json_output:
        typer.echo(json.dumps({"loops": loops}, indent=2))
        return
    if not loops:
        typer.echo("No builder-judge loops found.")
        return
    for loop in loops:
        score = f"{loop['final_score']}/100" if loop.get("final_score") is not None else "—"
        typer.echo(f"  {loop['loop_id']}  {loop['status']:12s}  {score:8s}  {loop['rounds_completed']} round(s)  {loop.get('started_at', '')}")


@builder_judge_app.command("show")
def builder_judge_show(
    loop_id: str = typer.Argument(..., help="Loop ID to inspect."),
    json_output: bool = typer.Option(False, "--json", help="Print full run as JSON."),
) -> None:
    """Show details of a past builder-judge loop run."""
    from devflow.control_room.builder_judge_loop import get_builder_judge_run

    run = get_builder_judge_run(Path.cwd(), loop_id)
    if run is None:
        typer.echo(f"Error: Loop not found: {loop_id}", err=True)
        raise typer.Exit(code=1)
    if json_output:
        typer.echo(json.dumps(run, indent=2, sort_keys=False))
        return
    typer.echo(f"Loop: {run.get('loop_id', loop_id)}")
    typer.echo(f"Status: {run.get('status', 'unknown')}")
    typer.echo(f"Started: {run.get('started_at', '—')}")
    typer.echo(f"Finished: {run.get('finished_at', '—')}")
    config = run.get("config", {})
    typer.echo(f"Builder: {config.get('builder_profile_id', '—')}")
    typer.echo(f"Judge: {config.get('judge_profile_id', '—')}")
    typer.echo(f"Threshold: {config.get('pass_threshold', '—')}")
    typer.echo(f"Definition of Done: {config.get('definition_of_done', '—')}")
    typer.echo("")
    for r in run.get("rounds", []):
        score = f"{r.get('score')}/100" if r.get("score") is not None else "N/A"
        passed = " ✓ PASSED" if r.get("passed") else ""
        typer.echo(f"  Round {r.get('round_number', '?')}: {score}{passed}")
        if r.get("judge_feedback"):
            typer.echo(f"    Feedback: {r['judge_feedback']}")
        for issue in r.get("issues", []):
            typer.echo(f"    - {issue}")
    if run.get("final_draft"):
        typer.echo("")
        typer.echo("=== Final Draft ===")
        typer.echo(run["final_draft"])
    typer.echo(f"\nStop reason: {run.get('stop_reason', '—')}")
    typer.echo(f"Next: {run.get('next_safe_action', '—')}")


@scheduler_app.command("status")
def scheduler_status(
    json_output: bool = typer.Option(False, "--json", help="Print scheduler status as JSON."),
) -> None:
    """Show the derived simple scheduler projection."""
    from devflow.control_room.scheduler_projection import build_scheduler_snapshot, render_scheduler_snapshot

    snapshot = build_scheduler_snapshot(Path.cwd())
    if json_output:
        typer.echo(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        typer.echo(render_scheduler_snapshot(snapshot), nl=False)


@scheduler_app.command("retry")
def scheduler_retry(
    task_id: str = typer.Argument(..., help="Task ID to mark for manual retry."),
    reason: str = typer.Option(..., "--reason", help="Human-readable retry reason."),
    json_output: bool = typer.Option(False, "--json", help="Print retry request as JSON."),
) -> None:
    """Write explicit retry-request evidence without rerunning work."""
    from devflow.control_room.scheduler_projection import request_scheduler_retry

    try:
        request = request_scheduler_retry(Path.cwd(), task_id, reason=reason)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(request.model_dump(mode="json"), indent=2, sort_keys=True))
    else:
        typer.echo(f"retry_request: {request.retry_request_path}")
        typer.echo(f"next_safe_action: {request.recommended_next_command}")


@question_app.command("list")
def question_list(json_output: bool = typer.Option(False, "--json", help="Print question projection as JSON.")) -> None:
    """Show worker and blocker questions without mutating evidence."""
    snapshot = build_question_snapshot(Path.cwd())
    if json_output:
        typer.echo(json.dumps(snapshot.model_dump(mode="json"), indent=2, sort_keys=True))
        return
    typer.echo(render_question_snapshot(snapshot), nl=False)


@question_app.command("show")
def question_show(
    question_id: str = typer.Argument(..., help="Question ID to inspect."),
    json_output: bool = typer.Option(False, "--json", help="Print question record as JSON."),
) -> None:
    """Show one derived or persisted question record."""
    snapshot = build_question_snapshot(Path.cwd())
    question = next((item for item in snapshot.questions if item.question_id == question_id), None)
    if question is None:
        typer.echo(f"Unknown question id: {question_id}", err=True)
        raise typer.Exit(code=1)
    if json_output:
        typer.echo(question.model_dump_json(indent=2))
        return
    typer.echo(f"question: {question.question_id}")
    typer.echo(f"status: {question.status}")
    typer.echo(f"task: {question.task_id}")
    typer.echo(f"question_text: {question.question}")
    typer.echo(f"resume: {question.recommended_resume_command}")


@question_app.command("answer")
def question_answer(
    question_id: str = typer.Argument(..., help="Question ID to answer."),
    answer: str = typer.Option(..., "--answer", help="Human answer to persist as evidence."),
    resume_command: str | None = typer.Option(None, "--resume-command", help="Recommended Dev-Flow resume command."),
    json_output: bool = typer.Option(False, "--json", help="Print answer record as JSON."),
) -> None:
    """Persist a human answer without running the resume command."""
    try:
        question = answer_question(Path.cwd(), question_id, answer=answer, resume_command=resume_command)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(question.model_dump_json(indent=2))
        return
    typer.echo(f"question: {question.question_id}")
    typer.echo(f"status: {question.status}")
    typer.echo(f"answer_path: {question.answer_path}")
    typer.echo(f"next_safe_action: {question.recommended_resume_command}")


@question_app.command("resolve")
def question_resolve(
    question_id: str = typer.Argument(..., help="Question ID to resolve."),
    reason: str = typer.Option(..., "--reason", help="Reason this question is no longer actionable."),
    json_output: bool = typer.Option(False, "--json", help="Print resolved record as JSON."),
) -> None:
    """Persist a resolution without deleting source question evidence."""
    try:
        question = resolve_question(Path.cwd(), question_id, reason=reason)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(question.model_dump_json(indent=2))
        return
    typer.echo(f"question: {question.question_id}")
    typer.echo(f"status: {question.status}")
    typer.echo(f"answer_path: {question.answer_path}")


@freshness_app.command("loop")
def freshness_loop(
    json_output: bool = typer.Option(False, "--json", help="Print the loop report as JSON."),
    all_projects: bool = typer.Option(False, "--all-projects", help="Run the loop across every registered project."),
) -> None:
    """Run one freshness-control loop iteration and update derived state."""
    if all_projects:
        from devflow.control_room.multi_project_freshness import (
            render_multi_project_freshness_report,
            run_multi_project_freshness_loop,
        )

        report = run_multi_project_freshness_loop()
        if json_output:
            typer.echo(json.dumps(report.model_dump(), indent=2, sort_keys=True))
        else:
            typer.echo(render_multi_project_freshness_report(report), nl=False)
        if report.status == "needs_human_decision":
            raise typer.Exit(code=2)
        return

    from devflow.control_room.freshness import render_freshness_report, run_freshness_loop
    report = run_freshness_loop(Path.cwd())
    if json_output:
        typer.echo(json.dumps(report.model_dump(), indent=2, sort_keys=True))
    else:
        typer.echo(render_freshness_report(report), nl=False)
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
    from devflow.control_room.parallel_verification import (
        VerificationBatchSelectionError,
        render_parallel_verification_run,
        run_projected_verification_batch,
    )

    try:
        run = run_projected_verification_batch(
            Path.cwd(),
            goal_id,
            batch_id,
            max_parallel=max_parallel,
            timeout_seconds=timeout_seconds,
        )
    except VerificationBatchSelectionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(run.model_dump(), indent=2, sort_keys=True))
    else:
        typer.echo(render_parallel_verification_run(run), nl=False)
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
    from devflow.control_room.parallel_worker import (
        WorkerBatchSelectionError,
        render_parallel_worker_run,
        run_projected_worker_batch,
    )

    try:
        run = run_projected_worker_batch(
            Path.cwd(),
            goal_id,
            batch_id,
            max_parallel=max_parallel,
            timeout_seconds=timeout_seconds,
        )
    except WorkerBatchSelectionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(run.model_dump(), indent=2, sort_keys=True))
    else:
        typer.echo(render_parallel_worker_run(run), nl=False)
    if run.status == "failed":
        raise typer.Exit(code=1)


@freshness_app.command("create-batch")
def freshness_create_batch(
    goal_id: str = typer.Argument(..., help="Goal ID containing the projected parallel task batch."),
    batch_id: str = typer.Argument(..., help="Projected parallel task batch ID, e.g. PB-0001."),
    json_output: bool = typer.Option(False, "--json", help="Print the task creation run report as JSON."),
) -> None:
    """Create tasks for one currently projected parallel-safe batch."""
    from devflow.control_room.parallel_task_creation import (
        ParallelTaskCreationSelectionError,
        render_parallel_task_creation_run,
        run_projected_task_creation_batch,
    )

    try:
        run = run_projected_task_creation_batch(Path.cwd(), goal_id, batch_id)
    except ParallelTaskCreationSelectionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(run.model_dump(), indent=2, sort_keys=True))
    else:
        typer.echo(render_parallel_task_creation_run(run), nl=False)


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
    from devflow.control_room.freshness_runner import (
        render_bounded_freshness_run,
        render_bounded_multi_project_freshness_run,
        run_bounded_freshness_control,
        run_bounded_multi_project_freshness_control,
    )

    if all_projects:
        if create_tasks or execute_workers or execute_verification:
            typer.echo("Error: --all-projects currently supports read-mostly bounded runs only.", err=True)
            raise typer.Exit(code=1)
        run = run_bounded_multi_project_freshness_control(max_iterations=max_iterations)
        if json_output:
            typer.echo(json.dumps(run.model_dump(), indent=2, sort_keys=True))
        else:
            typer.echo(render_bounded_multi_project_freshness_run(run), nl=False)
        if run.status == "needs_human_decision":
            raise typer.Exit(code=2)
        return

    run = run_bounded_freshness_control(
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
        typer.echo(render_bounded_freshness_run(run), nl=False)
    if run.status in {"needs_human_decision", "worker_failed", "verification_failed"}:
        raise typer.Exit(code=2)


@goal_app.command("init")
def goal_init(
    goal_id: str | None = typer.Argument(None, help="Explicit goal ID (e.g. G-0001)."),
    from_file: str = typer.Option(..., "--from", help="Path to the goal markdown brief."),
) -> None:
    """Initialize a durable goal scaffold from a markdown brief."""
    from devflow.control_room.goals import create_goal_from_markdown
    try:
        from_path = Path(from_file)
        record = create_goal_from_markdown(Path.cwd(), from_path, goal_id=goal_id)
        typer.echo(f"Initialized Goal {record.id}")
        typer.echo(f"Directory: .devflow/goals/{record.id}/")
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)


@goal_app.command("show")
def goal_show(goal_id: str) -> None:
    """Show a goal and its scaffolded artifacts."""
    from devflow.control_room.goals import render_goal_summary
    try:
        summary = render_goal_summary(Path.cwd(), goal_id)
        typer.echo(summary, nl=False)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)


@goal_app.command("list")
def goal_list() -> None:
    """List durable goals."""
    from devflow.control_room.goal_projection import render_goal_list
    typer.echo(render_goal_list(Path.cwd()), nl=False)


def _set_goal_lifecycle_command(goal_id: str, lifecycle: str, reason: str) -> None:
    from devflow.control_room.goal_lifecycle import (
        GoalLifecycleError,
        lifecycle_result,
        render_lifecycle_result,
        set_goal_lifecycle,
    )

    command = f"devflow goal {lifecycle if lifecycle != 'active' else 'activate'} {goal_id}"
    if reason:
        command = f"{command} --reason {reason!r}"
    try:
        state = set_goal_lifecycle(Path.cwd(), goal_id, lifecycle=lifecycle, reason=reason, command=command)
    except GoalLifecycleError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(render_lifecycle_result(lifecycle_result(Path.cwd(), state)), nl=False)


@goal_app.command("activate")
def goal_activate(
    goal_id: str,
    reason: str = typer.Option("", "--reason", help="Reason for activating this goal."),
) -> None:
    """Mark a goal active for freshness-loop projection."""
    _set_goal_lifecycle_command(goal_id, "active", reason)


@goal_app.command("pause")
def goal_pause(
    goal_id: str,
    reason: str = typer.Option(..., "--reason", help="Reason for pausing this goal."),
) -> None:
    """Pause goal execution without deleting evidence."""
    _set_goal_lifecycle_command(goal_id, "paused", reason)


@goal_app.command("block")
def goal_block(
    goal_id: str,
    reason: str = typer.Option(..., "--reason", help="Blocking reason."),
) -> None:
    """Block goal execution until a human decision or external repair."""
    _set_goal_lifecycle_command(goal_id, "blocked", reason)


@goal_app.command("complete")
def goal_complete(
    goal_id: str,
    reason: str = typer.Option(..., "--reason", help="Evidence-backed completion reason."),
) -> None:
    """Record human-approved goal completion."""
    _set_goal_lifecycle_command(goal_id, "complete", reason)


@goal_app.command("archive")
def goal_archive(
    goal_id: str,
    reason: str = typer.Option(..., "--reason", help="Archive reason."),
) -> None:
    """Archive a goal while preserving its evidence."""
    _set_goal_lifecycle_command(goal_id, "archived", reason)


@goal_app.command("status")
def goal_status(goal_id: str) -> None:
    """Show the status of a specific durable goal."""
    from devflow.control_room.goal_projection import render_goal_status
    typer.echo(render_goal_status(Path.cwd(), goal_id), nl=False)


@goal_app.command("next")
def goal_next(goal_id: str) -> None:
    """Recommend the next safest planning or implementation command for a goal."""
    from devflow.control_room.goal_projection import build_goal_status_projection
    try:
        proj = build_goal_status_projection(Path.cwd(), goal_id)
        typer.echo(f"Next action: {proj.next_action_label}")
        typer.echo(f"Command:     {proj.next_action_command or 'None'}")
        typer.echo(f"Reason:      {proj.next_action_reason}")
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)


@goal_app.command("slices")
def goal_slices(goal_id: str) -> None:
    """Show task slices from task-slices.yaml in a compact reviewable format."""
    from devflow.control_room.goal_tasks import render_goal_slices
    try:
        output = render_goal_slices(Path.cwd(), goal_id)
        typer.echo(output, nl=False)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)


@goal_app.command("create-task")
def goal_create_task(
    goal_id: str,
    slice_id: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be created without writing any task artifacts."),
) -> None:
    """Create a normal DevFlow task from a selected goal task slice."""
    from devflow.control_room.goal_tasks import get_goal_task_slice, create_task_from_goal_slice
    try:
        if dry_run:
            slice_data = get_goal_task_slice(Path.cwd(), goal_id, slice_id)
            typer.echo(f"[Dry Run] Would create task from {goal_id} / {slice_id}")
            typer.echo(f"Title: {slice_data.title}")
            return

        created = create_task_from_goal_slice(Path.cwd(), goal_id, slice_id)
        typer.echo(f"Created {created.task_id} from {created.goal_id} / {created.slice_id}\n")
        typer.echo("Task:")
        typer.echo(f"  {created.task_id} — {created.task_title}\n")
        typer.echo("Linked artifacts:")
        typer.echo(f"  goal: {created.goal_path}")
        typer.echo(f"  slice: {created.slice_id}")
        typer.echo(f"  task: {created.task_path}\n")
        typer.echo("Next:")
        typer.echo(f"  devflow task show {created.task_id}")

        slice_data = get_goal_task_slice(Path.cwd(), goal_id, slice_id)
        if slice_data.execution_mode == "HITL":
            typer.echo("\nThis slice is HITL. Human review is required before execution/promotion.")
        elif slice_data.execution_mode == "AFK":
            typer.echo("\nThis slice is AFK-classified, but execution is still explicit.")
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1)



TRUSTED_LOCAL_WARNING = "Security: shell execution is path-isolated, not sandboxed; run only trusted local commands."


def _resolve_task_project_root(project: str | None) -> ProjectRootResolution:
    try:
        return resolve_project_root(Path.cwd(), project)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _task_ref(task_id: str, project_id: str | None) -> str:
    return project_task_ref(task_id, project_id)


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


@project_app.command("create")
def project_create_command(
    name: str = typer.Argument(..., help="Project display name."),
    projects_root: str | None = typer.Option(None, "--projects-root", help="Directory that will contain managed projects."),
    source_control: str = typer.Option("local-git", "--source-control", help="none, local-git, remote-git, or github-managed."),
    private_context: bool = typer.Option(False, "--private-context", help="Ignore all .devflow/ context in the new repo."),
    remote_url: str | None = typer.Option(None, "--remote-url", help="Explicit remote URL for remote-git/github-managed projects."),
) -> None:
    """Create a separate local project root and register it with DevFlow."""
    try:
        result = create_managed_project(
            name,
            projects_root=Path(projects_root) if projects_root else None,
            source_control=source_control,
            private_context=private_context,
            remote_url=remote_url,
        )
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Created project {result.project_id}")
    typer.echo(f"path: {result.path}")
    typer.echo(f"source_control: {result.source_control_mode}")
    typer.echo(f"remote_url: {result.remote_url or 'none'}")
    typer.echo("github: disabled unless explicitly connected/published")


@project_app.command("import")
def project_import_command(
    path: str = typer.Argument(..., help="Existing project directory to register."),
    project_id: str | None = typer.Option(None, "--project-id", help="Explicit registry id when metadata does not exist."),
    name: str | None = typer.Option(None, "--name", help="Display name when metadata does not exist."),
    private_context: bool = typer.Option(False, "--private-context", help="Ignore all .devflow/ context if metadata is created."),
) -> None:
    """Register an existing project root with DevFlow."""
    try:
        result = import_managed_project(
            Path(path),
            project_id=project_id,
            name=name,
            private_context=private_context,
        )
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Imported project {result.project_id}")
    typer.echo(f"path: {result.path}")
    typer.echo(f"source_control: {result.source_control_mode}")
    typer.echo(f"remote_url: {result.remote_url or 'none'}")


@project_app.command("list")
def project_list_command(
    include_archived: bool = typer.Option(False, "--include-archived", help="Include archived projects."),
) -> None:
    """List registered projects."""
    try:
        typer.echo(render_project_list(include_archived=include_archived), nl=False)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@project_app.command("show")
def project_show_command(project_id: str) -> None:
    """Show registry and project-local metadata for one project."""
    try:
        typer.echo(render_project_show(project_id), nl=False)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@project_app.command("status")
def project_status_command(project_id: str) -> None:
    """Show task health for one registered project."""
    try:
        typer.echo(render_project_status(project_id), nl=False)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@project_app.command("doctor")
def project_doctor_command(project_id: str) -> None:
    """Check one registered project's metadata and source-control policy."""
    try:
        checks = doctor_project(project_id)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    failed = False
    for name, ok, detail in checks:
        marker = "ok" if ok else "missing"
        typer.echo(f"{marker}: {name} ({detail})")
        failed = failed or not ok
    if failed:
        raise typer.Exit(code=1)


@project_app.command("archive")
def project_archive_command(project_id: str) -> None:
    """Archive a project in the registry without deleting files."""
    try:
        record = archive_project(project_id)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Archived project {record.project_id}")


@project_app.command("remove")
def project_remove_command(
    project_id: str,
    registry_only: bool = typer.Option(False, "--registry-only", help="Remove only the registry entry; project files are never deleted."),
) -> None:
    """Remove a project from the registry without deleting its directory."""
    if not registry_only:
        typer.echo("Error: project remove requires --registry-only. DevFlow does not delete project directories.", err=True)
        raise typer.Exit(code=1)
    try:
        record = remove_project(project_id)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Removed project {record.project_id} from registry")


@project_app.command("connect-github")
def project_connect_github_command(
    project_id: str,
    remote_url: str = typer.Option(..., "--remote-url", help="Existing GitHub repository URL."),
    allow_push: bool = typer.Option(False, "--allow-push", help="Opt in to devflow push-main for this project."),
) -> None:
    """Attach an explicit GitHub remote policy to a registered local Git project."""
    try:
        metadata = update_project_remote_policy(project_id, remote_url=remote_url, push_allowed=allow_push)
    except ProjectRegistryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Connected GitHub remote for {metadata.project_id}")
    typer.echo(f"remote_url: {metadata.source_control.remote_url}")
    typer.echo(f"push_allowed: {'yes' if metadata.remote_publication.push_allowed else 'no'}")


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


@maintenance_app.command("reset-dogfood-state")
def maintenance_reset_dogfood_state(
    preview: bool = typer.Option(False, "--preview", help="Preview ignored runtime artifact removal."),
    yes: bool = typer.Option(False, "--yes", help="Apply ignored runtime artifact removal."),
) -> None:
    """Reset disposable dogfood/task runtime artifacts while preserving tracked seed state."""
    if preview == yes:
        typer.echo("Choose exactly one of --preview or --yes.", err=True)
        raise typer.Exit(code=1)
    result = reset_dogfood_state(Path.cwd(), apply=yes)
    typer.echo(f"mode: {'apply' if yes else 'preview'}")
    _echo_maintenance_result(result)
    if result.refused:
        raise typer.Exit(code=1)


@maintenance_app.command("reset-test-state")
def maintenance_reset_test_state(
    preview: bool = typer.Option(False, "--preview", help="Preview local test runtime artifact removal."),
    yes: bool = typer.Option(False, "--yes", help="Apply local test runtime artifact removal."),
) -> None:
    """Reset local test task/workspace/worktree artifacts while preserving project state."""
    if preview == yes:
        typer.echo("Choose exactly one of --preview or --yes.", err=True)
        raise typer.Exit(code=1)
    result = reset_test_state(Path.cwd(), apply=yes)
    typer.echo(f"mode: {'apply' if yes else 'preview'}")
    _echo_maintenance_result(result)
    if result.refused:
        raise typer.Exit(code=1)


@maintenance_app.command("repair-state")
def maintenance_repair_state(
    preview: bool = typer.Option(False, "--preview", help="Preview missing task baseline artifact repair."),
    yes: bool = typer.Option(False, "--yes", help="Restore missing task baseline artifacts."),
) -> None:
    """Restore missing task baseline artifacts without overwriting existing evidence."""
    if preview == yes:
        typer.echo("Choose exactly one of --preview or --yes.", err=True)
        raise typer.Exit(code=1)
    result = repair_state(Path.cwd(), apply=yes)
    typer.echo(f"mode: {'apply' if yes else 'preview'}")
    _echo_maintenance_result(result)
    if result.refused:
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


@operating_layer_app.command("snapshot")
def operating_layer_snapshot_command(
    json_output: bool = typer.Option(False, "--json", help="Print the operating-layer snapshot as JSON."),
) -> None:
    """Render the local operating-layer snapshot."""
    from devflow.control_room.operating_layer import (
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
    from devflow.control_room.operating_layer_server import run_operating_layer_server

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
    from devflow.control_room.operating_layer_service import install_operating_layer_launch_agent

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
    typer.echo(f"Starts at login: yes")
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
    from devflow.control_room.operating_layer_visual_qa import (
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
    typer.echo(f"Wrote {_relative(plan.repo_root, plan.packet_path)}")
    typer.echo(f"mode: {plan.context_mode}")
    typer.echo(f"recommended_tools: {', '.join(plan.recommended_tools)}")
    typer.echo(f"events: {_relative(plan.repo_root, plan.events_path)}")


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
    typer.echo(f"Created {_task_ref(task.id, scope.project_id)}: {task.title}")
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
    rows = [(_task_ref(projection.task.id, scope.project_id), projection) for projection in projections]
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
        typer.echo(f"export_path: {_relative(root, export_path)}")


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
    typer.echo(f"Estimated task-fit profile for task: {_task_ref(task_id, scope.project_id)}")
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
            scout_role: _relative(root, save_scout_report(root, task_id, scout_role, data))
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
    typer.echo(f"Executed scout evaluation for task: {_task_ref(task_id, scope.project_id)}")
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
        from devflow.control_room.router import route_task, save_routing_decision
        decision_data = route_task(root, task_id, project_id=scope.project_id)
        save_routing_decision(root, task_id, decision_data)
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    artifact_path = f".devflow/tasks/{task_id}/routing-decision.yaml"
    if json_output:
        payload = {
            "artifact_path": artifact_path,
            "routing_decision": decision_data["routing_decision"],
            "task_id": task_id,
        }
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    # Render beautiful breakdown
    typer.echo(f"Executed routing mapping for task: {_task_ref(task_id, scope.project_id)}")
    typer.echo("-" * 50)

    rd = decision_data["routing_decision"]
    typer.echo(f"Policy Version:              {rd.get('policy_version')}")

    typer.echo("")
    typer.echo("Selected Agent Assignments:")
    selected = rd.get("selected", {})
    for key in sorted(selected.keys()):
        typer.echo(f"  {key:<12}: {selected[key]}")
    if not selected:
        typer.echo("  - none")

    typer.echo("")
    typer.echo("Recorded Reasons:")
    for reason in rd.get("reason", []):
        typer.echo(f"  - {reason}")

    typer.echo("")
    typer.echo("Rejected Agents:")
    rejected = rd.get("rejected", [])
    if not rejected:
        typer.echo("  - none")
    else:
        for rej in rejected:
            typer.echo(f"  - agent:  {rej.get('agent', 'unknown')}")
            typer.echo(f"    reason: {rej.get('reason', 'unspecified')}")

    typer.echo("")
    typer.echo("Blocked Candidates:")
    blocked = rd.get("blocked", [])
    if not blocked:
        typer.echo("  - none")
    else:
        for item in blocked:
            typer.echo(f"  - role:   {item.get('role', 'unknown')}")
            typer.echo(f"    agent:  {item.get('agent', 'unknown')}")
            typer.echo(f"    status: {item.get('status', 'unknown')}")
            typer.echo(f"    reason: {item.get('reason', 'unspecified')}")

    typer.echo("")
    typer.echo("Unresolved Decisions:")
    unresolved = rd.get("unresolved", [])
    if not unresolved:
        typer.echo("  - none")
    else:
        for item in unresolved:
            typer.echo(f"  - role:   {item.get('role', 'unknown')}")
            typer.echo(f"    status: {item.get('status', 'unknown')}")
            typer.echo(f"    reason: {item.get('reason', 'unspecified')}")
            if item.get("next_command"):
                typer.echo(f"    next:   {item['next_command']}")

    typer.echo("")
    typer.echo("Recommended Next Commands:")
    recommended_next_commands = rd.get("recommended_next_commands", {})
    if not recommended_next_commands:
        typer.echo("  - none")
    else:
        for role in sorted(recommended_next_commands.keys()):
            typer.echo(f"  {role:<12}: {recommended_next_commands[role]}")

    typer.echo("-" * 50)
    typer.echo(f"Wrote routing-decision.yaml under .devflow/tasks/{task_id}/")


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
        from devflow.control_room.scorecard import generate_scorecard, save_scorecard
        scorecard_data = generate_scorecard(root, task_id)
        saved_path = save_scorecard(root, task_id, scorecard_data)

        # Update runtime profile from scorecard result
        try:
            from devflow.control_room.model_runtime_profiles import update_from_scorecard
            from devflow.control_room.estimator import estimate_task_fit
            sc = scorecard_data.get("scorecard", {})
            rd = scorecard_data.get("routing_decision", {})
            selected = rd.get("selected", {})
            worker_id = selected.get("worker") if isinstance(selected, dict) else None
            rs = scorecard_data.get("repo_scan", {})
            context_estimate = int(rs.get("total_context_estimate") or 0) if isinstance(rs, dict) else 0
            if worker_id:
                update_from_scorecard(
                    root=root,
                    scorecard=scorecard_data,
                    model_id=worker_id,
                    context_estimate=context_estimate,
                    latency_seconds=sc.get("latency_seconds", 0),
                )
        except Exception:
            pass  # non-critical — scorecard succeeded even if profile update fails
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    artifact_path = _relative(root, saved_path)
    sc = scorecard_data["scorecard"]
    if json_output:
        typer.echo(json.dumps(
            {
                "task_id": task_id,
                "artifact_path": artifact_path,
                "scorecard": sc,
            },
            indent=2,
            sort_keys=True,
        ))
        return

    # Render beautiful scorecard breakdown
    typer.echo(f"Compiled routing-quality scorecard for task: {_task_ref(task_id, scope.project_id)}")
    typer.echo("-" * 50)

    typer.echo(f"Decision Mode:              {sc.get('decision_mode', 'unknown')}")
    typer.echo(f"Verification Passed:        {_format_scorecard_flag(sc.get('verification_passed'))}")
    typer.echo(f"Promotion Ready:            {_format_scorecard_flag(sc.get('promotion_ready'))}")
    typer.echo(f"Selected Roles:             {_format_scorecard_list(sc.get('selected_roles'))}")
    typer.echo(f"Unresolved Roles:           {_format_scorecard_list(sc.get('unresolved_roles'))}")
    typer.echo(f"State Mutation:             {sc.get('state_mutation', 'unknown')}")
    typer.echo(f"Overall Quality Rating:     {_format_scorecard_rating(sc.get('overall_quality_rating'))}")
    typer.echo(f"First-Run Verification Pass: {_format_scorecard_flag(sc.get('first_run_pass'))}")
    typer.echo(f"Boundary Violations:        {_format_scorecard_flag(sc.get('boundary_violations'))}")
    typer.echo(f"Frontier Escalation Needed: {_format_scorecard_flag(sc.get('frontier_escalation_needed'))}")
    if "frontier_escalation_avoided" in sc:
        typer.echo(f"Frontier Escalation Avoided: {_format_scorecard_flag(sc.get('frontier_escalation_avoided'))}")
    typer.echo(f"Context Ceiling Exceeded:   {_format_scorecard_flag(sc.get('context_limit_exceeded'))}")
    typer.echo(f"Review Mistakes Found:      {_format_scorecard_flag(sc.get('review_mistakes_found'))}")
    typer.echo(f"Latency:                    {sc.get('latency_seconds', 'unknown')} seconds")
    typer.echo(f"Cost Avoided:               {_format_scorecard_cost(sc.get('cost_avoided_usd'))}")

    typer.echo("-" * 50)
    typer.echo(f"Wrote routing-quality-scorecard.yaml under .devflow/tasks/{task_id}/")


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
            rel_p = _relative(root, p)
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
    root = scope.root
    try:
        if agent:
            run_id = normalize_agent_patch_candidate(root, task_id, agent, project_id=scope.project_id)
        review = review_patch_candidate(root, task_id, run_id=run_id, project_id=scope.project_id)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    run_dir = root / ".devflow" / "tasks" / task_id / "local-model-runs" / review.run_id
    typer.echo(f"Patch Review for {_task_ref(task_id, scope.project_id)}")
    if scope.project_id:
        typer.echo(f"project_root: {root}")
    typer.echo("")
    typer.echo(f"Run: {review.run_id}")
    typer.echo(f"Proposal classification: {review.proposal_classification}")
    typer.echo(f"Patch candidate: {'yes' if review.has_patch_candidate else 'no'}")
    typer.echo(f"Review status: {review.review_status}")
    typer.echo(f"Risk: {review.risk}")
    typer.echo("")
    typer.echo("Files touched:")
    if review.files_touched:
        for file_path in review.files_touched:
            typer.echo(f"- {file_path}")
    else:
        typer.echo("- None")
    if review.generated_or_forbidden_paths:
        typer.echo("")
        typer.echo("Artifact paths:")
        for file_path in review.generated_or_forbidden_paths:
            typer.echo(f"- {file_path}")
    typer.echo("")
    typer.echo("Artifacts:")
    typer.echo(f"patch_review: {_relative(root, run_dir / 'patch-review.md')}")
    typer.echo(f"patch_review_json: {_relative(root, run_dir / 'patch-review.json')}")
    typer.echo("")
    typer.echo("Next:")
    typer.echo(review.next_action.get("command") or "None")


@task_app.command("patch-dry-run")
def task_patch_dry_run(
    task_id: str,
    run_id: str | None = typer.Option(None, "--run-id", help="Dry-run a specific reviewed local model run id."),
    agent: str | None = typer.Option(None, "--agent", help="Dry-run a reviewed proposal.patch from a task agent."),
    project: str | None = typer.Option(None, "--project", help="Dry-run patch evidence from a registered project root."),
) -> None:
    """Preview whether reviewed proposal.patch evidence would apply without mutating files."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        if agent:
            run_id = normalize_agent_patch_candidate(root, task_id, agent, project_id=scope.project_id)
        result = preview_patch_dry_run(root, task_id, run_id=run_id, project_id=scope.project_id)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    run_dir = root / ".devflow" / "tasks" / task_id / "local-model-runs" / result.run_id
    typer.echo(f"Patch Dry-run Preview for {_task_ref(task_id, scope.project_id)}")
    if scope.project_id:
        typer.echo(f"project_root: {root}")
    typer.echo("")
    typer.echo(f"Run: {result.run_id}")
    typer.echo(f"Patch review status: {_patch_review_status(root, task_id, result.run_id)}")
    typer.echo(f"Dry-run status: {result.dry_run_status}")
    typer.echo(f"Risk: {result.risk}")
    typer.echo("")
    typer.echo("Files checked:")
    if result.files_checked:
        for file_path in result.files_checked:
            typer.echo(f"- {file_path}")
    else:
        typer.echo("- None")
    typer.echo("")
    typer.echo("Hunks:")
    typer.echo(f"checked: {result.hunks_checked}")
    typer.echo(f"matched: {result.hunks_matched}")
    typer.echo(f"failed: {result.hunks_failed}")
    if result.findings:
        typer.echo("")
        typer.echo("Findings:")
        for finding in result.findings:
            typer.echo(f"- {finding}")
    if result.warnings:
        typer.echo("")
        typer.echo("Warnings:")
        for warning in result.warnings:
            typer.echo(f"- {warning}")
    typer.echo("")
    typer.echo("Artifacts:")
    typer.echo(f"dry_run: {_relative(root, run_dir / 'patch-dry-run.md')}")
    typer.echo(f"dry_run_json: {_relative(root, run_dir / 'patch-dry-run.json')}")
    typer.echo("")
    typer.echo("Next:")
    typer.echo("Review dry-run evidence manually. Do not apply anything automatically.")


def _patch_review_status(root: Path, task_id: str, run_id: str) -> str:
    review_path = root / ".devflow" / "tasks" / task_id / "local-model-runs" / run_id / "patch-review.json"
    try:
        data = json.loads(review_path.read_text(encoding="utf-8"))
    except Exception:
        return "unknown"
    if not isinstance(data, dict):
        return "unknown"
    return str(data.get("review_status") or "unknown")


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
    typer.echo(f"  Evidence Dir:      {_relative(Path.cwd(), result.artifact_dir)}")
    typer.echo(f"  Prompt evidence:   {_relative(Path.cwd(), result.prompt_path)}")
    typer.echo(f"  Response evidence: {_relative(Path.cwd(), result.response_path)}")
    typer.echo(f"  Run Metadata:      {_relative(Path.cwd(), result.run_json_path)}")
    typer.echo("-" * 50)

    # Standard compatibility outputs
    typer.echo(f"{task_id}: {result.status}")
    typer.echo(f"local_worker: {resolved_worker}")
    typer.echo(f"model: {result.model}")
    typer.echo("local_worker_mode: legacy_advisory")
    typer.echo("canonical_implementation_command: devflow task run <task-id> --worker qwopus-implementer")
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
    from devflow.control_room.paths import relative_path

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
    typer.echo(f"  1. Review the generated proposal evidence at:")
    typer.echo(f"     {rel_response_path}")
    typer.echo(f"  2. Explicitly choose to run implementer, apply patch, or verify task:")
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
    if worker == "manual":
        typer.echo("Warning: 'manual' worker is experimental and does not execute work.")
    elif worker == "shell":
        typer.echo(TRUSTED_LOCAL_WARNING)
    from devflow.control_room.agent_registry import load_agent_registry
    from devflow.control_room.worker_adapter import list_worker_adapters, UnsupportedWorkerAdapter

    registry = load_agent_registry(root)
    valid_agents = list(registry.agents.keys())
    valid_adapters = list_worker_adapters()
    selected_agent = registry.agents.get(worker)
    if selected_agent is not None and selected_agent.provider == "ollama" and selected_agent.adapter == "ollama_chat":
        typer.echo("worker_mode: registry_backed_local_ollama_patch_worker")
        typer.echo("worker_note: writes proposal.patch evidence only; Dev-Flow applies patches separately and verifies separately.")

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
        task = run_shell_task(root, task_id, command, timeout_seconds=timeout_seconds, worker_adapter=worker)
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"{_task_ref(task.id, scope.project_id)}: {task.status}")
    if scope.project_id:
        typer.echo(f"project_root: {root}")
    typer.echo(f"log_path: {task.log_path}")
    typer.echo(f"result_path: {task.result_path}")
    if selected_agent is not None and selected_agent.provider == "ollama" and selected_agent.adapter == "ollama_chat":
        _echo_registry_patch_worker_evidence_paths(root, task.id, worker)
    handoff_path = root / ".devflow" / "tasks" / task.id / "agents" / worker / "handoff.md"
    if handoff_path.exists():
        typer.echo(f"manual_handoff_path: {_relative(root, handoff_path)}")
    if task.latest_log_line:
        typer.echo(f"latest_log_line: {task.latest_log_line}")
    if selected_agent is not None and selected_agent.provider == "ollama" and selected_agent.adapter == "ollama_chat" and task.status == "complete":
        typer.echo(f"suggested_next_action: devflow task review-patch {task.id} --agent {worker}")
    _echo_review_capsule(root, task.id)
    if task.status != "complete":
        exit_code = task.last_exit_code if task.last_exit_code is not None else 1
        raise typer.Exit(code=exit_code)


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
    root = scope.root
    project_option = f" --project {project}" if project else ""

    from devflow.control_room.router import route_task, save_routing_decision
    from devflow.control_room.estimator import estimate_task_fit, save_task_fit

    # Step 1: Fit (classify archetype)
    fit_data = estimate_task_fit(root, task_id)
    task_fit = fit_data.get("task_fit", {})
    save_task_fit(root, task_id, fit_data)
    archetype_id = task_fit.get("archetype_id", "unknown")
    context_estimate = fit_data.get("repo_scan", {}).get("total_context_estimate", 0)
    requires_vision = task_fit.get("requires_vision", False)
    requires_thinking = task_fit.get("requires_thinking", "optional")

    typer.echo(f"task_id: {task_id}")
    typer.echo(f"archetype: {archetype_id}")
    typer.echo(f"context_estimate: {context_estimate} tokens")
    typer.echo(f"requires_vision: {requires_vision}")
    typer.echo(f"requires_thinking: {requires_thinking}")
    typer.echo(f"---")

    # Step 2: Route (select best worker)
    decision_data = route_task(root, task_id, project_id=project)
    save_routing_decision(root, task_id, decision_data)
    rd = decision_data.get("routing_decision", {})
    selected = rd.get("selected", {})
    worker_id = selected.get("worker") if isinstance(selected, dict) else None
    reasons = rd.get("reason", [])
    unresolved = rd.get("unresolved", [])

    if worker_id:
        typer.echo(f"selected_worker: {worker_id}")
        for reason in reasons:
            if "score=" in reason or "tuned" in reason or "selected:" in reason:
                typer.echo(f"  reason: {reason}")
        if unresolved:
            for item in unresolved:
                typer.echo(f"  unresolved: {item.get('role')} - {item.get('reason', '')}")
    else:
        typer.echo("no eligible worker selected")
        for item in unresolved:
            typer.echo(f"  unresolved: {item.get('role')} - {item.get('reason', '')}")
        if not dry_run:
            raise typer.Exit(code=1)

    if dry_run:
        if worker_id:
            typer.echo(f"---")
            typer.echo(f"Dry-run mode — to execute: devflow task run {task_id}{project_option} --worker {worker_id}")
        return

    # Step 3: Run
    typer.echo(f"---")
    typer.echo(f"Executing worker: {worker_id}")

    from devflow.control_room.worker_adapter import UnsupportedWorkerAdapter, list_worker_adapters
    from devflow.control_room.agent_registry import load_agent_registry

    registry = load_agent_registry(root)
    selected_agent = registry.agents.get(worker_id) if worker_id else None

    if selected_agent is not None and selected_agent.provider == "ollama" and selected_agent.adapter == "ollama_chat":
        typer.echo("worker_mode: registry_backed_local_ollama_patch_worker")
        typer.echo("worker_note: writes proposal.patch evidence only; Dev-Flow applies patches separately and verifies separately.")

    valid_agents = list(registry.agents.keys())
    valid_adapters_list = list_worker_adapters()
    if worker_id not in valid_agents and worker_id not in valid_adapters_list:
        from devflow.control_room.worker_adapter import get_worker_adapter
        try:
            get_worker_adapter(worker_id)
        except UnsupportedWorkerAdapter as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=1) from exc

    try:
        task = run_shell_task(root, task_id, [], worker_adapter=worker_id)
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    typer.echo(f"status: {task.status}")
    typer.echo(f"log_path: {task.log_path}")
    if task.latest_log_line:
        typer.echo(f"latest_log_line: {task.latest_log_line}")

    if selected_agent is not None and selected_agent.provider == "ollama" and selected_agent.adapter == "ollama_chat" and task.status == "complete":
        typer.echo(f"suggested_next_action: devflow task review-patch {task.id} --agent {worker_id}")

    if task.status != "complete":
        exit_code = task.last_exit_code if task.last_exit_code is not None else 1
        raise typer.Exit(code=exit_code)


def _echo_registry_patch_worker_evidence_paths(root: Path, task_id: str, agent_id: str) -> None:
    agent_dir = root / ".devflow" / "tasks" / task_id / "agents" / agent_id
    typer.echo(f"agent_packet_path: {_relative(root, agent_dir / 'packet.json')}")
    typer.echo(f"raw_output_path: {_relative(root, agent_dir / 'raw_output.md')}")
    typer.echo(f"proposal_patch_path: {_relative(root, agent_dir / 'proposal.patch')}")
    typer.echo(f"run_metadata_path: {_relative(root, agent_dir / 'run.json')}")
    typer.echo(f"agent_result_path: {_relative(root, agent_dir / 'result.md')}")
    typer.echo(f"agent_log_path: {_relative(root, agent_dir / 'logs' / 'worker.log')}")


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
    typer.echo(f"escalation_packet_path: {_relative(root, packet_path)}")
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

    typer.echo(f"{_task_ref(task.id, scope.project_id)}: verification {task.verification_status}")
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
        task = apply_task_patch(root, task_id, agent_id=agent, run_id=run_id)

        # Retrieve the latest patch_applied event to print details
        task_path = root / ".devflow" / "tasks" / task.id
        events_file = task_path / "events.jsonl"
        patch_hash = "unknown"
        patch_evidence_path = None
        patch_review_path = None
        patch_dry_run_path = None
        agent_id = agent or "default"
        applied_run_id = run_id
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
                        patch_review_path = evt.get("patch_review_path")
                        patch_dry_run_path = evt.get("patch_dry_run_path")
                        agent_id = evt.get("agent_id") or agent_id
                        applied_run_id = evt.get("run_id", applied_run_id)
                        changed_files = evt.get("changed_files", [])
                except Exception:
                    pass

        typer.echo(
            f"Successfully applied patch from agent '{agent_id}' "
            f"to task workspace '{_task_ref(task.id, scope.project_id)}'."
        )
        if scope.project_id:
            typer.echo(f"project_root: {root}")
        typer.echo(f"Workspace: .devflow/workspaces/{task.id}")
        if applied_run_id:
            typer.echo(f"Run ID: {applied_run_id}")
        typer.echo(f"Patch Hash: {patch_hash}")
        if patch_review_path:
            typer.echo(f"Patch Review: {patch_review_path}")
        if patch_dry_run_path:
            typer.echo(f"Patch Dry-run: {patch_dry_run_path}")
        if patch_evidence_path:
            typer.echo(f"Patch Evidence: {patch_evidence_path}")
        typer.echo("")
        typer.echo("Modified files:")
        for cf in changed_files:
            typer.echo(f"  - {cf['path']} ({cf['operation']})")
        typer.echo("")
        typer.echo("Next:")
        if scope.project_id:
            typer.echo(
                f"  devflow task verify {task.id} --project {scope.project_id} --shell \"<command>\""
            )
        else:
            typer.echo(f"  devflow task verify {task.id} --shell \"<command>\"")

    except (PatchError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


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


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


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


def _format_scorecard_list(value: object) -> str:
    if value is None or value == "unknown":
        return "unknown"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "none"
    return str(value)


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


def _echo_maintenance_result(result: Any) -> None:
    for path in result.would_remove:
        typer.echo(f"would_remove: {path}")
    for path in result.removed:
        typer.echo(f"removed: {path}")
    for path in result.would_repair:
        typer.echo(f"would_repair: {path}")
    for path in result.repaired:
        typer.echo(f"repaired: {path}")
    for item in result.refused:
        typer.echo(f"refused: {item}")
    if not (
        result.would_remove
        or result.removed
        or result.would_repair
        or result.repaired
        or result.refused
    ):
        typer.echo("nothing_to_do: yes")


def _echo_list(label: str, values: list[str]) -> None:
    typer.echo(f"{label}:")
    if not values:
        typer.echo("  - none")
        return
    for value in values:
        typer.echo(f"  - {value}")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _runtime_status_line(contract: dict[str, Any], *, include_refusal: bool) -> str:
    parts = [
        f"runtime: {contract['execution_surface']}",
        f"task_run: {_yes_no(bool(contract['task_run_allowed']))}",
        f"agent_run: {_yes_no(bool(contract['agent_run_allowed']))}",
        f"packet: {_yes_no(bool(contract['packet_allowed']))}",
    ]
    if contract.get("next_command"):
        parts.append(f"next: {contract['next_command']}")
    elif include_refusal and contract.get("refusal_reason"):
        parts.append(f"refusal: {contract['refusal_reason']}")
    elif contract.get("refusal_reason"):
        parts.append("refusal: see agent show")
    return "  " + " | ".join(parts)


def _echo_runtime_contract(contract: dict[str, Any]) -> None:
    typer.echo("runtime_contract:")
    typer.echo(f"  execution_surface: {contract['execution_surface']}")
    typer.echo(f"  task_run_allowed: {str(contract['task_run_allowed']).lower()}")
    typer.echo(f"  agent_run_allowed: {str(contract['agent_run_allowed']).lower()}")
    typer.echo(f"  packet_allowed: {str(contract['packet_allowed']).lower()}")
    typer.echo(f"  refusal_reason: {contract.get('refusal_reason') or 'none'}")
    typer.echo(f"  next_command: {contract.get('next_command') or 'none'}")
    evidence = contract.get("evidence_contract") or {}
    _echo_list("  evidence_required_outputs", list(evidence.get("required_outputs") or []))
    _echo_list("  evidence_optional_outputs", list(evidence.get("optional_outputs") or []))
    _echo_list("  evidence_forbidden_outputs", list(evidence.get("forbidden_outputs") or []))


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


@dogfood_app.command("list")
def dogfood_list() -> None:
    """List built-in dogfood production-readiness cases."""
    from devflow.control_room.dogfood import materialize_dogfood_cases, production_readiness_cases, render_dogfood_case_list

    materialize_dogfood_cases(Path.cwd())
    typer.echo(render_dogfood_case_list(production_readiness_cases()), nl=False)


@dogfood_app.command("show")
def dogfood_show(case_id: str) -> None:
    """Show a built-in dogfood case definition."""
    try:
        from devflow.control_room.dogfood import materialize_dogfood_cases, render_dogfood_case

        materialize_dogfood_cases(Path.cwd())
        typer.echo(render_dogfood_case(case_id), nl=False)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@dogfood_app.command("run")
def dogfood_run(
    suite: str = typer.Option("production-readiness", "--suite"),
    case: list[str] | None = typer.Option(None, "--case", help="Run only the selected case id. Repeatable."),
    write_root_runtime_evidence: bool = typer.Option(
        False,
        "--write-root-runtime-evidence",
        help="Unsafe/noisy: write dogfood-created tasks and runtime evidence into this repo instead of a temp scratch project.",
    ),
    fail_below_silver: bool = typer.Option(
        True,
        "--fail-below-silver/--no-fail-below-silver",
        help="Exit non-zero when the run does not satisfy the Silver threshold.",
    ),
    keep_runs: int = typer.Option(
        1,
        "--keep-runs",
        min=1,
        help="How many dogfood run reports to retain under .devflow/dogfood/runs.",
    ),
) -> None:
    """Run a deterministic local production-readiness dogfood suite."""
    try:
        from devflow.control_room.dogfood import run_dogfood_suite

        result = run_dogfood_suite(
            Path.cwd(),
            suite=suite,
            case_ids=case,
            write_root_runtime_evidence=write_root_runtime_evidence,
            keep_runs=keep_runs,
        )
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    scorecard = result["scorecard"]
    threshold = scorecard["threshold_result"]
    typer.echo(f"dogfood_run_id: {result['run_id']}")
    typer.echo(f"score: {scorecard['total_score']}/{scorecard['max_score']}")
    typer.echo(f"threshold: {threshold['achieved']}")
    typer.echo(f"silver_met: {'yes' if threshold['silver_met'] else 'no'}")
    typer.echo(f"run_path: {result['run_path']}")
    typer.echo(f"scorecard_path: {result['scorecard_path']}")
    typer.echo(f"report_path: {result['report_path']}")
    if result.get("pruned_runs"):
        typer.echo("pruned_runs:")
        for path in result["pruned_runs"]:
            typer.echo(f"  - {path}")
    if scorecard["failures"]:
        typer.echo("failures:")
        for failure in scorecard["failures"]:
            typer.echo(f"  - {failure}")
    if scorecard["warnings"]:
        typer.echo("warnings:")
        for warning in scorecard["warnings"]:
            typer.echo(f"  - {warning}")
    if fail_below_silver and not threshold["silver_met"]:
        raise typer.Exit(code=1)


@dogfood_app.command("score")
def dogfood_score(run_id: str) -> None:
    """Show a dogfood scorecard summary for a run id, or 'latest'."""
    try:
        from devflow.control_room.dogfood import load_dogfood_run, render_dogfood_score

        loaded = load_dogfood_run(Path.cwd(), run_id)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(render_dogfood_score(loaded["scorecard"]), nl=False)


@dogfood_app.command("report")
def dogfood_report(run_id: str) -> None:
    """Print a dogfood report for a run id, or 'latest'."""
    try:
        from devflow.control_room.dogfood import load_dogfood_run

        loaded = load_dogfood_run(Path.cwd(), run_id)
    except KeyError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(loaded["report"], nl=False)


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


@idea_app.command("capture")
def idea_capture(
    text: str,
    title: str | None = typer.Option(None, "--title", help="Optional title override."),
    source: str = typer.Option("manual", "--source", help="Source label for this idea."),
    tag: list[str] = typer.Option([], "--tag", help="Repeatable idea tag."),
) -> None:
    """Capture a raw idea as local, human-reviewed intake evidence."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, capture_idea

        item = capture_idea(Path.cwd(), text, title=title, source=source, tags=tag)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo(f"maturity: {item['maturity']}")
    typer.echo(f"path: .devflow/ideas/{item['id']}/idea.json")
    typer.echo("created_goal: no")
    typer.echo("created_task: no")


@idea_app.command("list")
def idea_list(
    status: str | None = typer.Option(None, "--status", help="Filter by idea status."),
) -> None:
    """List local Idea Foundry items."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, list_ideas, render_idea_list

        typer.echo(render_idea_list(list_ideas(Path.cwd(), status=status)), nl=False)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@idea_app.command("show")
def idea_show(idea_id: str) -> None:
    """Show one Idea Foundry item and its evidence notes."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, render_idea_show, show_idea

        metadata, raw, classification, promotion = show_idea(Path.cwd(), idea_id)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(render_idea_show(metadata, raw, classification, promotion), nl=False)


@idea_app.command("classify")
def idea_classify(
    idea_id: str,
    maturity: str = typer.Option(..., "--maturity", help="spark, concept, candidate, goal_ready, or task_ready."),
    note: str = typer.Option("", "--note", help="Human classification note."),
    tag: list[str] = typer.Option([], "--tag", help="Repeatable replacement tag."),
) -> None:
    """Classify an idea with human-supplied maturity and tags."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, classify_idea

        item = classify_idea(Path.cwd(), idea_id, maturity=maturity, note=note, tags=tag)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo(f"maturity: {item['maturity']}")
    typer.echo("model_called: no")


@idea_app.command("promote")
def idea_promote(
    idea_id: str,
    target: str = typer.Option(..., "--to", help="Promotion target: goal or task."),
    rationale: str = typer.Option(..., "--rationale", help="Human rationale for the promotion decision."),
    title: str | None = typer.Option(None, "--title", help="Optional suggested goal/task title."),
) -> None:
    """Record a human promotion decision without creating goals or tasks."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, promote_idea

        item = promote_idea(Path.cwd(), idea_id, target=target, rationale=rationale, title=title)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo(f"promotion_target: {item['promotion_target']}")
    typer.echo("created_goal: no")
    typer.echo("created_task: no")


@idea_app.command("create-goal")
def idea_create_goal(
    idea_id: str,
    title: str | None = typer.Option(None, "--title", help="Optional goal title override."),
    goal_id: str | None = typer.Option(None, "--goal-id", help="Optional explicit goal id."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without creating goal artifacts."),
) -> None:
    """Create a durable goal scaffold from a promoted goal-ready idea."""
    try:
        from devflow.control_room.idea_execution_bridge import (
            IdeaExecutionBridgeError,
            create_goal_from_idea,
            preview_goal_from_idea,
        )

        result = (
            preview_goal_from_idea(Path.cwd(), idea_id, title=title, goal_id=goal_id)
            if dry_run
            else create_goal_from_idea(Path.cwd(), idea_id, title=title, goal_id=goal_id)
        )
    except IdeaExecutionBridgeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if dry_run:
        typer.echo("would_create_goal: yes")
    typer.echo(f"idea_id: {result.idea_id}")
    typer.echo(f"created_goal_id: {result.created_id}")
    typer.echo(f"created_goal_path: {result.created_path}")
    typer.echo(f"link_path: {result.link_path}")
    typer.echo(f"next: {result.next_command}")
    typer.echo("worker_ran: no")
    typer.echo("verification_ran: no")


@idea_app.command("scaffold-goal")
def idea_scaffold_goal(
    idea_id: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing scaffold evidence."),
) -> None:
    """Create reviewable intent-to-goal scaffold evidence from an idea."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError
        from devflow.control_room.intent_scaffold import (
            preview_scaffold_from_idea,
            write_scaffold_from_idea,
        )

        proposal = (
            preview_scaffold_from_idea(Path.cwd(), idea_id)
            if dry_run
            else write_scaffold_from_idea(Path.cwd(), idea_id)
        )
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if dry_run:
        typer.echo("would_write_scaffold: yes")
    typer.echo(f"idea_id: {idea_id}")
    typer.echo(f"status: {proposal['status']}")
    typer.echo(f"title: {proposal['normalized_intent']['title']}")
    if not dry_run and proposal["status"] == "ready_for_review":
        typer.echo(f"scaffold_path: .devflow/ideas/{idea_id}/scaffold-goal.json")
    for command in proposal.get("next_commands") or []:
        typer.echo(f"next: {command}")
    typer.echo("created_goal: no")
    typer.echo("created_task: no")
    typer.echo("worker_ran: no")
    typer.echo("verification_ran: no")


@idea_app.command("create-task")
def idea_create_task(
    idea_id: str,
    title: str | None = typer.Option(None, "--title", help="Optional task title override."),
    git_worktree: bool = typer.Option(
        False,
        "--git-worktree",
        help="Create the task with the existing Git-native worktree lane.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without creating task artifacts."),
) -> None:
    """Create a Dev-Flow task from a promoted task-ready idea."""
    try:
        from devflow.control_room.idea_execution_bridge import (
            IdeaExecutionBridgeError,
            create_task_from_idea,
            preview_task_from_idea,
        )

        result = (
            preview_task_from_idea(Path.cwd(), idea_id, title=title, git_worktree=git_worktree)
            if dry_run
            else create_task_from_idea(Path.cwd(), idea_id, title=title, git_worktree=git_worktree)
        )
    except IdeaExecutionBridgeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if dry_run:
        typer.echo("would_create_task: yes")
    typer.echo(f"idea_id: {result.idea_id}")
    typer.echo(f"created_task_id: {result.created_id}")
    typer.echo(f"created_task_path: {result.created_path}")
    typer.echo(f"link_path: {result.link_path}")
    typer.echo(f"git_worktree: {'yes' if result.git_worktree else 'no'}")
    typer.echo(f"next: {result.next_command}")
    typer.echo("worker_ran: no")
    typer.echo("verification_ran: no")


@idea_app.command("park")
def idea_park(
    idea_id: str,
    reason: str = typer.Option("No reason supplied.", "--reason", help="Why this idea is safe to revisit later."),
) -> None:
    """Park an idea without losing its evidence."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, park_idea

        item = park_idea(Path.cwd(), idea_id, reason=reason)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo("evidence_deleted: no")


@idea_app.command("archive")
def idea_archive(
    idea_id: str,
    reason: str = typer.Option("No reason supplied.", "--reason", help="Human archive reason."),
) -> None:
    """Archive an idea while preserving its evidence."""
    try:
        from devflow.control_room.idea_foundry import IdeaFoundryError, archive_idea

        item = archive_idea(Path.cwd(), idea_id, reason=reason)
    except IdeaFoundryError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"idea_id: {item['id']}")
    typer.echo(f"status: {item['status']}")
    typer.echo("evidence_deleted: no")


@agent_app.command("catalog")
def agent_catalog(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    provider: str | None = typer.Option(None, "--provider", help="Filter catalog to one provider id."),
) -> None:
    """Show providers, profiles, runtime contracts, env readiness, and local model discovery."""
    from devflow.control_room.agent_onboarding import AgentOnboardingError, build_agent_catalog

    try:
        payload = build_agent_catalog(Path.cwd(), provider_id=provider)
    except (AgentRegistryError, AgentOnboardingError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo("providers:")
    for item in payload["providers"]:
        missing = " missing-env" if item["api_key_env_missing"] else ""
        typer.echo(f"- {item['id']} ({item['adapter']}){missing}")
    typer.echo("profiles:")
    for profile in payload["profiles"]:
        contract = profile["runtime_contract"]
        typer.echo(
            f"- {profile['id']}: {profile['provider']}/{profile['model']} "
            f"{profile['authority']} -> {contract['execution_surface']}"
        )
    local = payload["local_ollama"]
    typer.echo(f"local_ollama: {local['status']}")
    if local.get("unregistered_models"):
        typer.echo("unregistered_local_models:")
        for model in local["unregistered_models"]:
            typer.echo(f"- {model}")


@agent_app.command("add-provider")
def agent_add_provider(
    provider_id: str,
    adapter: str = typer.Option(..., "--adapter", help="Provider adapter, such as ollama_chat or openai_compatible."),
    base_url: str = typer.Option(..., "--base-url", help="Provider base URL."),
    api_key_env: str | None = typer.Option(None, "--api-key-env", help="Environment variable name for the API key."),
    timeout_seconds: int | None = typer.Option(None, "--timeout-seconds", min=1, help="Default timeout in seconds."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate and preview without writing."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Register a provider config under .devflow/providers."""
    from devflow.control_room.agent_onboarding import AgentOnboardingError, add_provider

    try:
        result = add_provider(
            Path.cwd(),
            provider_id,
            adapter=adapter,
            base_url=base_url,
            api_key_env=api_key_env,
            timeout_seconds=timeout_seconds,
            dry_run=dry_run,
        )
    except AgentOnboardingError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    payload = result.to_payload(Path.cwd())
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"status: {payload['status']}")
    typer.echo(f"provider_id: {payload['provider']['id']}")
    typer.echo(f"adapter: {payload['provider']['adapter']}")
    typer.echo(f"path: {payload['path']}")
    typer.echo(f"dry_run: {str(payload['dry_run']).lower()}")


@agent_app.command("add-model")
def agent_add_model(
    provider_id: str = typer.Option(..., "--provider", help="Existing provider id."),
    model_id: str = typer.Option(..., "--model", help="Model slug or local Ollama model id."),
    authority: str = typer.Option(..., "--authority", help="read-only, advisory, patch-proposer, or disabled."),
    role: str = typer.Option(..., "--role", help="Registered role id for this profile."),
    profile_id: str | None = typer.Option(None, "--profile-id", help="Optional safe explicit profile id."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate and preview without writing."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Register or upsert a safe model profile under .devflow/agents/registry.yaml."""
    from devflow.control_room.agent_onboarding import AgentOnboardingError, add_model

    try:
        result = add_model(
            Path.cwd(),
            provider_id=provider_id,
            model_id=model_id,
            authority=authority,
            role=role,
            profile_id=profile_id,
            dry_run=dry_run,
        )
    except (AgentRegistryError, AgentOnboardingError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    payload = result.to_payload(Path.cwd())
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"status: {payload['status']}")
    typer.echo(f"profile_id: {payload['profile_id']}")
    typer.echo(f"provider: {payload['agent']['provider']}")
    typer.echo(f"model: {payload['agent']['model']}")
    typer.echo(f"runtime: {payload['runtime_contract']['execution_surface']}")
    typer.echo(f"path: {payload['path']}")
    typer.echo(f"dry_run: {str(payload['dry_run']).lower()}")


@agent_app.command("list")
def agent_list(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """List loaded agents from the registry."""
    try:
        registry = load_agent_registry(Path.cwd())
    except AgentRegistryError as exc:
        typer.echo(f"Error loading agent registry: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        from devflow.control_room.local_model_worker_pool import registry_json_payload

        typer.echo(json.dumps(registry_json_payload(Path.cwd()), indent=2, sort_keys=True))
        return

    agents = registry.agents
    if not agents:
        typer.echo("No agents defined in registry.")
        return

    typer.echo(f"{'Agent':<42} {'Provider':<10} {'Model':<34} {'Role':<30} {'Mode':<14} {'Hermes':<8} {'Enabled':<8}")
    typer.echo("-" * 155)
    for agent_id in sorted(agents.keys()):
        agent = agents[agent_id]
        enabled_str = "yes" if agent.enabled else "no"
        hermes_str = "yes" if agent.hermes_delegable else "no"
        contract = agent_runtime_contract(Path.cwd(), agent)
        typer.echo(
            f"{agent.id:<42} {agent.provider:<10} {agent.model:<34} {agent.role:<30} {agent.default_mode:<14} {hermes_str:<8} {enabled_str:<8}"
        )
        typer.echo(_runtime_status_line(contract, include_refusal=False))


@agent_app.command("show")
def agent_show(
    agent_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
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

    if json_output:
        from devflow.control_room.local_model_worker_pool import agent_json_payload

        typer.echo(json.dumps(agent_json_payload(Path.cwd(), agent_id), indent=2, sort_keys=True))
        return

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
    typer.echo(f"hermes_delegable: {str(agent.hermes_delegable).lower()}")
    typer.echo(f"enabled: {str(agent.enabled).lower()}")
    _echo_runtime_contract(agent_runtime_contract(Path.cwd(), agent))


@agent_app.command("policy")
def agent_policy(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show local worker-pool enforcement policy."""
    from devflow.control_room.local_model_worker_pool import agent_policy_payload

    payload = agent_policy_payload()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"policy_id: {payload['policy_id']}")
    typer.echo(f"source_of_truth: {payload['source_of_truth']}")
    typer.echo(f"worker_outputs_are: {payload['worker_outputs_are']}")
    _echo_list("execution_gates", payload["execution_gates"])
    _echo_list("forbidden", payload["forbidden"])
    _echo_list("allowed_evidence_outputs", payload["allowed_evidence_outputs"])


@agent_app.command("serial-packet")
def agent_serial_packet(
    phase: str = typer.Option(..., "--phase", help="Serial local-agent phase to packetize."),
    provider: str = typer.Option(..., "--provider", help="Local/runtime provider id, such as ollama."),
    model: str = typer.Option(..., "--model", help="Provider model id for the manual worker launch."),
    allowed_files: list[str] | None = typer.Option(
        None,
        "--allowed-file",
        help="Repo-relative file the local worker may edit. Repeat for each allowed file.",
    ),
    verification_commands: list[str] | None = typer.Option(
        None,
        "--verify",
        help="Verification command for the completion verifier. Repeat for each command.",
    ),
    mission: str | None = typer.Option(None, "--mission", help="Optional packet mission text."),
    run_id: str | None = typer.Option(None, "--run-id", help="Optional stable run id."),
    task_id: str | None = typer.Option(None, "--task-id", help="Optional DevFlow task id."),
    worker_id: str | None = typer.Option(None, "--worker-id", help="Optional intended worker id."),
    runtime: str = typer.Option("manual", "--runtime", help="Intended runtime: manual or hermes-profile."),
    hermes_profile: str | None = typer.Option(
        None, "--hermes-profile", help="Hermes profile id when --runtime hermes-profile."
    ),
    toolsets: list[str] | None = typer.Option(
        None, "--toolset", help="Hermes toolset to record for the packet. Repeat for each toolset."
    ),
) -> None:
    """Write a packet-only serial local-agent run directory without launching a worker."""
    from devflow.control_room.serial_local_agent_run import (
        SerialLocalAgentRunError,
        create_serial_local_agent_run,
    )

    root = Path.cwd()
    try:
        result = create_serial_local_agent_run(
            root,
            phase=phase,
            provider=provider,
            model=model,
            allowed_files=allowed_files or [],
            verification_commands=verification_commands or [],
            mission=mission,
            run_id=run_id,
            task_id=task_id,
            worker_id=worker_id,
            runtime_kind=runtime,
            hermes_profile=hermes_profile,
            toolsets=toolsets or [],
        )
    except SerialLocalAgentRunError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    run_dir = _relative(root, result.run_dir)
    artifacts = result.manifest["artifacts"]
    preflight = result.manifest["preflight"]
    runtime_payload = result.manifest.get("runtime") or {}
    typer.echo(f"run_id: {result.run_id}")
    typer.echo(f"run_dir: {run_dir}")
    typer.echo(f"worker_packet: {run_dir}/{artifacts['worker_packet']}")
    typer.echo(f"preflight: {run_dir}/{artifacts['preflight']}")
    typer.echo(f"completion_verifier: {run_dir}/{artifacts['completion_verifier']}")
    typer.echo(f"runtime_preflight_state: {preflight['state']}")
    typer.echo(f"launch_packet_ready: {str(preflight['launch_packet_ready']).lower()}")
    typer.echo(f"runtime: {runtime_payload.get('kind') or 'manual'}")
    if runtime_payload.get("hermes_profile"):
        typer.echo(f"hermes_profile: {runtime_payload['hermes_profile']}")
    if runtime_payload.get("toolsets"):
        typer.echo(f"toolsets: {', '.join(runtime_payload['toolsets'])}")
    typer.echo("model_launch: false")
    typer.echo("worker_ran: no")
    typer.echo("git_mutation: false")
    if runtime_payload.get("kind") == "hermes-profile":
        launch_target = f"Hermes profile {runtime_payload['hermes_profile']} manually outside DevFlow/browser"
    else:
        launch_target = "one single-flight local worker manually"
    typer.echo(
        "next_safe_manual_launch: review "
        f"{run_dir}/{artifacts['preflight']} and {run_dir}/{artifacts['worker_packet']}; "
        f"if launch_packet_ready=true, launch {launch_target}, "
        "then run completion-verifier.py from the packet directory."
    )


@agent_app.command("hermes-run")
def agent_hermes_run(
    run_id: str,
    profile: str = typer.Option(..., "--profile", help="Hermes profile id to use for this packet."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview the Hermes command without launching it."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Allow using a Hermes command for a non-Hermes runtime packet.",
    ),
    hermes_bin: str = typer.Option("hermes", "--hermes-bin", help="Hermes executable path."),
    timeout_seconds: int = typer.Option(900, "--timeout-seconds", min=1, help="Hermes launch timeout."),
) -> None:
    """Validate a serial packet and run or preview a Hermes worker command."""
    from devflow.control_room.hermes_worker_runtime import (
        HermesWorkerRuntimeError,
        dry_run_hermes_worker_runtime,
        run_hermes_worker_runtime,
    )

    try:
        if dry_run:
            payload = dry_run_hermes_worker_runtime(
                Path.cwd(),
                run_id=run_id,
                hermes_profile=profile,
                force=force,
                hermes_executable=hermes_bin,
            )
        else:
            payload = run_hermes_worker_runtime(
                Path.cwd(),
                run_id=run_id,
                hermes_profile=profile,
                force=force,
                hermes_executable=hermes_bin,
                timeout_seconds=timeout_seconds,
            )
    except HermesWorkerRuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        _echo_hermes_run_payload(payload)

    exit_code = payload.get("exit_code")
    if not dry_run and exit_code not in (None, 0):
        raise typer.Exit(code=int(exit_code) if isinstance(exit_code, int) else 1)


def _echo_hermes_run_payload(payload: dict[str, object]) -> None:
    typer.echo(f"will_launch_hermes: {str(payload['will_launch_hermes']).lower()}")
    typer.echo(f"run_id: {payload['run_id']}")
    typer.echo(f"packet_path: {payload['packet_path']}")
    typer.echo(f"hermes_profile: {payload['hermes_profile']}")
    typer.echo(f"preflight_state: {payload['preflight_state']}")
    typer.echo(f"launch_allowed: {str(payload.get('launch_allowed')).lower()}")
    if "launch_status" in payload:
        typer.echo(f"launch_status: {payload['launch_status']}")
        typer.echo(f"exit_code: {payload['exit_code']}")
        typer.echo(f"stdout_path: {payload['stdout_path']}")
        typer.echo(f"stderr_path: {payload['stderr_path']}")
        typer.echo(f"hermes_run_path: {payload['hermes_run_path']}")
        typer.echo(f"next_safe_action: {payload['next_safe_action']}")
    typer.echo("command_preview:")
    command_preview = payload.get("command_preview")
    if not isinstance(command_preview, list):
        command_preview = []
    for index, arg in enumerate(command_preview):
        typer.echo(f"  [{index}] {arg}")


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


@agent_app.command("context-pack")
def agent_context_pack(
    task_id: str,
    agent_id: str,
    role: str = typer.Option("implementation_worker", "--role", help="Role label for the context pack."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Write a context pack from a registered project root."),
) -> None:
    """Write a role-scoped context pack derived from a task packet."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        from devflow.control_room.context_pack import write_context_pack

        result = write_context_pack(root, task_id, agent_id=agent_id, role=role)
    except (KeyError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    payload = {
        "task_id": result.pack.task_id,
        "agent_id": result.pack.agent_id,
        "role": result.pack.role,
        "permission_mode": result.pack.permission_mode,
        "estimated_chars": result.pack.estimated_chars,
        "estimated_tokens": result.pack.estimated_tokens,
        "json_path": _relative(root, result.json_path),
        "markdown_path": _relative(root, result.markdown_path),
        "packet_path": _relative(root, result.packet_path),
    }
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"task_id: {payload['task_id']}")
    typer.echo(f"agent_id: {payload['agent_id']}")
    typer.echo(f"role: {payload['role']}")
    typer.echo(f"permission_mode: {payload['permission_mode']}")
    typer.echo(f"estimated_tokens: {payload['estimated_tokens']}")
    typer.echo(f"json_path: {payload['json_path']}")
    typer.echo(f"markdown_path: {payload['markdown_path']}")
    typer.echo(f"packet_path: {payload['packet_path']}")


@agent_app.command("evidence")
def agent_evidence(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Show a derived summary of task-local agent evidence."""
    root = Path.cwd()
    try:
        from devflow.control_room.agent_evidence import summarize_agent_evidence

        summary = summarize_agent_evidence(root, task_id)
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    payload = summary.to_dict()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"task_id: {payload['task_id']}")
    typer.echo(f"has_worker_evidence: {str(payload['has_worker_evidence']).lower()}")
    typer.echo(f"local_model_run_count: {len(payload['local_model_runs'])}")
    typer.echo(f"local_patch_agent_count: {len(payload['local_patch_agents'])}")
    typer.echo(f"manual_result_present: {str(payload['manual_result_present']).lower()}")
    typer.echo(f"next_safe_action: {payload['next_safe_action']}")


@agent_app.command("discover-local")
def agent_discover_local(
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
) -> None:
    """Discover installed local Ollama models and classify their capabilities."""
    try:
        from devflow.control_room.local_agent_discovery import discover_local_ollama_models

        report = discover_local_ollama_models()
    except Exception as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    payload = report.to_dict()
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"provider: {payload['provider']}")
    typer.echo(f"installed_model_count: {len(payload['installed_models'])}")
    for model in payload["installed_models"]:
        typer.echo(f"- {model['name']} ({model['size']})")
    if payload["errors"]:
        typer.echo("errors:")
        for error in payload["errors"]:
            typer.echo(f"- {error['model']}: {error['error']}")


@agent_app.command("select-local")
def agent_select_local(
    task_id: str,
    role: str = typer.Option("implementation_worker", "--role", help="Role to select a local agent for."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Write selection evidence under a registered project root."),
) -> None:
    """Rank installed local agents for a role and write selection evidence."""
    scope = _resolve_task_project_root(project)
    root = scope.root
    try:
        from devflow.control_room.local_agent_discovery import (
            discover_local_ollama_models,
            rank_local_agent_candidates,
            selection_payload_with_path,
            write_selected_agent_evidence,
        )

        report = discover_local_ollama_models()
        registry = load_agent_registry(root)
        selection = rank_local_agent_candidates(registry, report.installed_models, role=role)
        selection_path = write_selected_agent_evidence(root, task_id, selection, project_id=scope.project_id)
        payload = selection_payload_with_path(root, task_id, selection, selection_path, project_id=scope.project_id)
    except (AgentRegistryError, FileNotFoundError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(f"task_id: {_task_ref(task_id, scope.project_id)}")
        if scope.project_id:
            typer.echo(f"project_root: {root}")
        typer.echo(f"role: {payload['role']}")
        typer.echo(f"status: {payload['status']}")
        typer.echo(f"selected_agent_id: {payload['selected_agent_id'] or 'none'}")
        typer.echo(f"selected_model: {payload['selected_model'] or 'none'}")
        typer.echo(f"selection_path: {payload['selection_path']}")
        if payload["next_command"]:
            typer.echo(f"next: {payload['next_command']}")

    if payload["status"] != "selected":
        raise typer.Exit(code=1)


@agent_app.command("audition")
def agent_audition(
    task_id: str,
    job: str = typer.Option(..., "--job", help="Audition job type, such as review-debug or summary-status."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan an audition without calling models."),
    execute: bool = typer.Option(False, "--execute", help="Run selected candidates sequentially through local worker-pool evidence."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Write audition evidence under a registered project root."),
) -> None:
    """Plan a read-only local model audition for a task."""
    from devflow.control_room.model_audition import (
        ModelAuditionError,
        execute_model_audition,
        write_model_audition_dry_run_plan,
    )

    if dry_run == execute:
        typer.echo("Error: Provide exactly one of --dry-run or --execute.", err=True)
        raise typer.Exit(code=1)

    scope = _resolve_task_project_root(project)
    try:
        payload = (
            execute_model_audition(scope.root, task_id, job, project_id=scope.project_id)
            if execute
            else write_model_audition_dry_run_plan(
                scope.root,
                task_id,
                job,
                project_id=scope.project_id,
            )
        )
    except ModelAuditionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"task_id: {_task_ref(task_id, scope.project_id)}")
    typer.echo(f"job_type: {payload['job_type']}")
    typer.echo(f"status: {payload['status']}")
    typer.echo(f"audition_id: {payload['audition_id']}")
    typer.echo(f"plan_path: {payload['plan_path']}")
    if payload["dry_run"]:
        typer.echo(f"selected_candidate_count: {len(payload['selected_candidates'])}")
        for candidate in payload["selected_candidates"]:
            typer.echo(f"- {candidate['candidate_alias']}: {candidate['profile_id']} ({candidate['model']})")
        typer.echo("will_call_models: no")
    else:
        typer.echo(f"run_count: {payload['run_count']}")
        typer.echo(f"runs_path: {payload['runs_path']}")
        typer.echo(f"scorecard_path: {payload['scorecard_path']}")
        typer.echo(f"report_path: {payload['report_path']}")
        typer.echo("will_call_models: yes")


@agent_app.command("hyperplane", hidden=True)
def agent_hyperplane(
    task_id: str,
    suite: str = typer.Option(..., "--suite", help="Hyperplane suite id, such as worker-safety."),
    target: str = typer.Option(..., "--target", help="Target under test: control-room or a local model profile id."),
    judge: str = typer.Option(..., "--judge", help="Local model profile used as the Hyperplane judge."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Write a no-model Hyperplane plan."),
    execute: bool = typer.Option(False, "--execute", help="Run Hyperplane sequentially and write task-local evidence."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Write Hyperplane evidence under a registered project root."),
    depth: int = typer.Option(12, "--depth", min=1, help="Hyperplane depth budget."),
    breadth: int = typer.Option(2, "--breadth", min=1, help="Hyperplane breadth budget."),
    timeout_seconds: int | None = typer.Option(None, "--timeout-seconds", min=1, help="Override local judge timeout."),
    output_budget_tokens: int | None = typer.Option(None, "--output-budget-tokens", min=1, help="Override local judge output budget."),
    allow_self_grading: bool = typer.Option(
        False,
        "--allow-self-grading",
        help="Explicitly allow target and judge to be the same local model profile.",
    ),
) -> None:
    """Quarantined experimental Hyperplane evidence runner."""
    from devflow.control_room.hyperplane_harness import (
        HyperplaneHarnessError,
        execute_hyperplane_run,
        write_hyperplane_dry_run_plan,
    )

    if dry_run == execute:
        typer.echo("Error: Provide exactly one of --dry-run or --execute.", err=True)
        raise typer.Exit(code=1)

    scope = _resolve_task_project_root(project)
    try:
        payload = (
            execute_hyperplane_run(
                scope.root,
                task_id,
                suite,
                target,
                judge,
                project_id=scope.project_id,
                depth=depth,
                breadth=breadth,
                timeout_seconds=timeout_seconds,
                output_budget_tokens=output_budget_tokens,
                allow_self_grading=allow_self_grading,
            )
            if execute
            else write_hyperplane_dry_run_plan(
                scope.root,
                task_id,
                suite,
                target,
                judge,
                project_id=scope.project_id,
                depth=depth,
                breadth=breadth,
                timeout_seconds=timeout_seconds,
                output_budget_tokens=output_budget_tokens,
                allow_self_grading=allow_self_grading,
            )
        )
    except HyperplaneHarnessError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    typer.echo(f"task_id: {_task_ref(task_id, scope.project_id)}")
    typer.echo(f"suite: {payload['suite']}")
    typer.echo(f"target: {payload['target']}")
    typer.echo(f"judge: {payload['judge']}")
    typer.echo(f"status: {payload['status']}")
    typer.echo(f"run_id: {payload['run_id']}")
    typer.echo(f"run_dir: {payload['run_dir']}")
    typer.echo(f"plan_path: {payload['plan_path']}")
    typer.echo(f"will_call_hyperplane: {str(payload['will_call_hyperplane']).lower()}")
    typer.echo(f"will_call_models: {str(payload['will_call_models']).lower()}")
    if payload.get("summary_path"):
        typer.echo(f"summary_path: {payload['summary_path']}")
    if payload.get("findings_path"):
        typer.echo(f"findings_path: {payload['findings_path']}")
    if payload.get("report_path"):
        typer.echo(f"report_path: {payload['report_path']}")


@agent_app.command("hyperplane-list", hidden=True)
def agent_hyperplane_list(
    task_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Read Hyperplane evidence from a registered project root."),
) -> None:
    """List task-local Hyperplane evidence runs."""
    from devflow.control_room.hyperplane_harness import list_hyperplane_runs

    scope = _resolve_task_project_root(project)
    payload = list_hyperplane_runs(scope.root, task_id)
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    typer.echo(f"task_id: {_task_ref(task_id, scope.project_id)}")
    for run in payload["runs"]:
        typer.echo(f"- {run['run_id']}: {run.get('status', 'unknown')} ({run.get('suite') or 'unknown-suite'})")


@agent_app.command("hyperplane-show", hidden=True)
def agent_hyperplane_show(
    task_id: str,
    run_id: str,
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    project: str | None = typer.Option(None, "--project", help="Read Hyperplane evidence from a registered project root."),
) -> None:
    """Show a task-local Hyperplane evidence run."""
    from devflow.control_room.hyperplane_harness import HyperplaneHarnessError, show_hyperplane_run

    scope = _resolve_task_project_root(project)
    try:
        payload = show_hyperplane_run(scope.root, task_id, run_id)
    except HyperplaneHarnessError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        return
    summary = payload.get("summary") or {}
    typer.echo(f"task_id: {_task_ref(task_id, scope.project_id)}")
    typer.echo(f"run_id: {run_id}")
    typer.echo(f"status: {summary.get('status', 'unknown')}")
    typer.echo(f"run_dir: {payload['run_dir']}")
    if payload["missing_files"]:
        typer.echo("missing_files:")
        for item in payload["missing_files"]:
            typer.echo(f"- {item}")



@agent_app.command("advise")
def agent_advise(
    profile_id: str = typer.Option(..., "--profile", help="Remote advisory profile id."),
    task_id: str | None = typer.Option(None, "--task", help="Optional Dev-Flow task id for task-scoped advice."),
    job: str = typer.Option(..., "--job", help="Advisory job: gap-analysis, review, or status."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Build the bounded prompt plan without calling OpenRouter."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    max_prompt_chars: int = typer.Option(200_000, "--max-prompt-chars", min=1),
) -> None:
    """Write bounded remote advisory evidence through an OpenRouter profile."""
    from devflow.control_room.openrouter_agent import (
        OpenRouterAgentError,
        dry_run_advice,
        run_advice,
    )

    try:
        payload = (
            dry_run_advice(
                root=Path.cwd(),
                profile_id=profile_id,
                task_id=task_id,
                job=job,
                max_prompt_chars=max_prompt_chars,
            )
            if dry_run
            else run_advice(
                root=Path.cwd(),
                profile_id=profile_id,
                task_id=task_id,
                job=job,
                max_prompt_chars=max_prompt_chars,
            )
        )
    except OpenRouterAgentError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(f"status: {payload['status']}")
        typer.echo(f"profile_id: {payload['profile_id']}")
        typer.echo(f"job: {payload['job']}")
        typer.echo(f"provider: {payload['provider']}")
        typer.echo(f"model: {payload['model']}")
        typer.echo(f"dry_run: {str(payload['dry_run']).lower()}")
        typer.echo(f"evidence_dir: {payload['evidence_dir']}")
        typer.echo(f"will_call_provider: {str(payload['will_call_provider']).lower()}")
        if payload.get("recommendations"):
            typer.echo("recommendations:")
            for recommendation in payload["recommendations"]:
                typer.echo(f"- {recommendation['next_safe_action']}")
        if payload.get("error"):
            typer.echo(f"error: {payload['error']}")
    if payload.get("status") == "failed":
        raise typer.Exit(code=1)


@agent_app.command("propose-patch")
def agent_propose_patch(
    task_id: str = typer.Option(..., "--task", help="Dev-Flow task id for explicit patch proposal evidence."),
    profile_id: str = typer.Option(..., "--profile", help="Patch-proposal profile id."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    max_prompt_chars: int = typer.Option(200_000, "--max-prompt-chars", min=1),
) -> None:
    """Write explicit remote patch proposal evidence without applying it."""
    from devflow.control_room.openrouter_agent import OpenRouterAgentError, run_patch_proposal

    try:
        payload = run_patch_proposal(
            root=Path.cwd(),
            task_id=task_id,
            profile_id=profile_id,
            max_prompt_chars=max_prompt_chars,
        )
    except OpenRouterAgentError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(f"status: {payload['status']}")
        typer.echo(f"task_id: {payload['task_id']}")
        typer.echo(f"profile_id: {payload['profile_id']}")
        typer.echo(f"prompt_mode: {payload.get('prompt_mode', 'standard')}")
        typer.echo(f"prompt_chars: {payload.get('prompt_chars', 0)}")
        typer.echo(f"proposal_patch_path: {payload['proposal_patch_path'] or 'none'}")
        typer.echo(f"run_metadata_path: {payload['run_metadata_path']}")
        typer.echo(f"result_path: {payload['result_path']}")
        typer.echo(f"next_safe_action: {payload['next_safe_action']}")
        if payload.get("error"):
            typer.echo(f"error: {payload['error']}")
    if payload.get("status") != "success":
        raise typer.Exit(code=1)


@agent_app.command("ask")
def agent_ask(
    agent_id: str = typer.Argument(..., help="The local agent name."),
    prompt: list[str] = typer.Argument(None, help="The prompt to send."),
    file: str | None = typer.Option(None, "--file", help="File to include."),
    show_paths: bool = typer.Option(False, "--show-paths"),
    no_save: bool = typer.Option(False, "--no-save"),
    allow_disabled: bool = typer.Option(False, "--allow-disabled"),
) -> None:
    """[LEGACY] Ask a local agent a prompt directly."""
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
    runner = AgentTerminalRunner(repo_root=Path.cwd(), agent_name=agent_id, allow_disabled=allow_disabled)
    runner.run_one_shot(
        command="ask",
        prompt=prompt_text,
        file_to_include=file,
        no_save=no_save,
        show_paths=show_paths,
    )


@agent_app.command("chat")
def agent_chat(
    agent_id: str = typer.Argument(..., help="The local agent name."),
    no_save: bool = typer.Option(False, "--no-save"),
    allow_disabled: bool = typer.Option(False, "--allow-disabled"),
) -> None:
    """[LEGACY] Start an interactive chat session with a local agent."""
    from devflow.control_room.agent_terminal import AgentTerminalRunner
    runner = AgentTerminalRunner(repo_root=Path.cwd(), agent_name=agent_id, allow_disabled=allow_disabled)
    runner.run_chat(no_save=no_save)


@agent_app.command("run")
def agent_run(
    agent_id: str | None = typer.Argument(None, help="The local agent name for legacy runs, or profile id when --task is set."),
    task_id: str | None = typer.Option(None, "--task", help="Dev-Flow task id for registry-backed local worker-pool runs."),
    profile_id: str | None = typer.Option(None, "--profile", help="Agent registry profile id for local worker-pool runs."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview worker-pool run without calling the model or writing evidence."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON for worker-pool runs."),
    base_url: str | None = typer.Option(None, "--base-url", help="Override local OpenAI-compatible base URL for worker-pool runs."),
    timeout_seconds: int | None = typer.Option(None, "--timeout-seconds", min=1, help="Override local model timeout seconds."),
    temperature: float | None = typer.Option(None, "--temperature", min=0.0, max=2.0, help="Local model temperature."),
    max_packet_chars: int = typer.Option(200_000, "--max-packet-chars", help="Capping size of rendered task packet text."),
    prompt: str | None = typer.Option(None, "--prompt"),
    prompt_file: str | None = typer.Option(None, "--prompt-file"),
    stdin: bool = typer.Option(False, "--stdin"),
    file: str | None = typer.Option(None, "--file"),
    show_paths: bool = typer.Option(False, "--show-paths"),
    no_save: bool = typer.Option(False, "--no-save"),
    allow_disabled: bool = typer.Option(False, "--allow-disabled"),
) -> None:
    """[LEGACY] Run a task-less one-shot prompt with a local agent."""
    if task_id is not None or profile_id is not None:
        from devflow.control_room.local_model_worker_pool import (
            LocalModelWorkerPoolError,
            dry_run_local_model_profile,
            run_local_model_profile,
        )

        resolved_profile = profile_id or agent_id
        if task_id is None or resolved_profile is None:
            typer.echo("Error: --task and --profile are required for local worker-pool runs.", err=True)
            raise typer.Exit(code=1)
        try:
            if dry_run:
                payload = dry_run_local_model_profile(
                    root=Path.cwd(),
                    task_id=task_id,
                    profile_id=resolved_profile,
                    max_packet_chars=max_packet_chars,
                )
            else:
                payload = run_local_model_profile(
                    root=Path.cwd(),
                    task_id=task_id,
                    profile_id=resolved_profile,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    temperature=temperature,
                    max_packet_chars=max_packet_chars,
                )
        except LocalModelWorkerPoolError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        if json_output:
            typer.echo(json.dumps(payload, indent=2, sort_keys=True))
        else:
            typer.echo(f"task_id: {payload['task_id']}")
            typer.echo(f"profile_id: {payload['profile_id']}")
            typer.echo(f"model: {payload['model']}")
            typer.echo(f"adapter: {payload['adapter']}")
            typer.echo(f"adapter_maturity: {payload['adapter_maturity']}")
            typer.echo(f"permission_mode: {payload['permission_mode']}")
            typer.echo(f"hermes_delegable: {str(payload['hermes_delegable']).lower()}")
            typer.echo(f"dry_run: {str(payload['dry_run']).lower()}")
            if payload["dry_run"]:
                typer.echo("will_call_model: false")
                _echo_list("safety_warnings", payload["safety_warnings"])
                _echo_list("expected_evidence_outputs", list(payload["expected_evidence_outputs"].values()))
            else:
                typer.echo(f"status: {payload['status']}")
                typer.echo(f"run_id: {payload['run_id']}")
                typer.echo(f"evidence_dir: {payload['evidence_dir']}")
                typer.echo(f"response_path: {payload['response_path']}")
                typer.echo(f"raw_output_path: {payload['raw_output_path']}")
                if payload.get("error_message"):
                    typer.echo(f"error: {payload['error_message']}")
        if not dry_run and payload.get("status") != "success":
            raise typer.Exit(code=1)
        return

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
    runner = AgentTerminalRunner(repo_root=Path.cwd(), agent_name=agent_id, allow_disabled=allow_disabled)
    runner.run_one_shot(
        command="run",
        prompt=prompt_text,
        file_to_include=file,
        no_save=no_save,
        show_paths=show_paths,
    )


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
