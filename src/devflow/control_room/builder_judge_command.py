from __future__ import annotations

import json
from pathlib import Path

import typer

from devflow.control_room.builder_judge_loop import DEFAULT_BUILDER_PROFILE, DEFAULT_JUDGE_PROFILE


builder_judge_app = typer.Typer(help="Run builder-judge quality-control loops")


@builder_judge_app.command("run")
def builder_judge_run(
    definition_of_done: str = typer.Option(..., "--dod", "--definition-of-done", help="What does great look like? Be specific."),
    starting_point: str = typer.Option("", "--starting-point", help="Seed text for the builder to start from."),
    builder: str = typer.Option(DEFAULT_BUILDER_PROFILE, "--builder", help="Builder model profile ID."),
    judge: str = typer.Option(DEFAULT_JUDGE_PROFILE, "--judge", help="Judge model profile ID."),
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
        project_builder_judge_run,
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
        typer.echo(json.dumps(project_builder_judge_run(run, root=Path.cwd()), indent=2, sort_keys=False))
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
