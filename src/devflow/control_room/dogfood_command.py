from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import typer

from devflow.control_room.dogfood import (
    load_dogfood_run,
    materialize_dogfood_cases,
    production_readiness_cases,
    render_dogfood_case,
    render_dogfood_case_list,
    render_dogfood_score,
    run_dogfood_suite,
)


class DogfoodCommandError(RuntimeError):
    """User-facing dogfood command error."""


@dataclass(frozen=True)
class DogfoodRunCommandResult:
    lines: tuple[str, ...]
    exit_code: int


dogfood_app = typer.Typer(help="Run deterministic Dev-Flow production-readiness dogfood suites")


def render_dogfood_list(root: Path) -> str:
    materialize_dogfood_cases(root)
    return render_dogfood_case_list(production_readiness_cases())


def render_dogfood_show(root: Path, case_id: str) -> str:
    try:
        materialize_dogfood_cases(root)
        return render_dogfood_case(case_id)
    except KeyError as exc:
        raise DogfoodCommandError(str(exc)) from exc


def build_dogfood_run_result(
    root: Path,
    *,
    suite: str,
    case_ids: Iterable[str] | None,
    write_root_runtime_evidence: bool,
    keep_runs: int,
) -> dict[str, Any]:
    try:
        return run_dogfood_suite(
            root,
            suite=suite,
            case_ids=case_ids,
            write_root_runtime_evidence=write_root_runtime_evidence,
            keep_runs=keep_runs,
        )
    except Exception as exc:
        raise DogfoodCommandError(str(exc)) from exc


def render_dogfood_run_lines(result: dict[str, Any]) -> tuple[str, ...]:
    scorecard = result["scorecard"]
    threshold = scorecard["threshold_result"]
    lines = [
        f"dogfood_run_id: {result['run_id']}",
        f"score: {scorecard['total_score']}/{scorecard['max_score']}",
        f"threshold: {threshold['achieved']}",
        f"silver_met: {'yes' if threshold['silver_met'] else 'no'}",
        f"run_path: {result['run_path']}",
        f"scorecard_path: {result['scorecard_path']}",
        f"report_path: {result['report_path']}",
    ]
    if result.get("pruned_runs"):
        lines.append("pruned_runs:")
        lines.extend(f"  - {path}" for path in result["pruned_runs"])
    if scorecard["failures"]:
        lines.append("failures:")
        lines.extend(f"  - {failure}" for failure in scorecard["failures"])
    if scorecard["warnings"]:
        lines.append("warnings:")
        lines.extend(f"  - {warning}" for warning in scorecard["warnings"])
    return tuple(lines)


def dogfood_run_exit_code(result: dict[str, Any], *, fail_below_silver: bool) -> int:
    if fail_below_silver and not result["scorecard"]["threshold_result"]["silver_met"]:
        return 1
    return 0


def run_dogfood_command(
    root: Path,
    *,
    suite: str,
    case_ids: Iterable[str] | None,
    write_root_runtime_evidence: bool,
    keep_runs: int,
    fail_below_silver: bool,
) -> DogfoodRunCommandResult:
    result = build_dogfood_run_result(
        root,
        suite=suite,
        case_ids=case_ids,
        write_root_runtime_evidence=write_root_runtime_evidence,
        keep_runs=keep_runs,
    )
    return DogfoodRunCommandResult(
        lines=render_dogfood_run_lines(result),
        exit_code=dogfood_run_exit_code(result, fail_below_silver=fail_below_silver),
    )


def render_dogfood_score_for_run(root: Path, run_id: str) -> str:
    try:
        loaded = load_dogfood_run(root, run_id)
    except KeyError as exc:
        raise DogfoodCommandError(str(exc)) from exc
    return render_dogfood_score(loaded["scorecard"])


def render_dogfood_report_for_run(root: Path, run_id: str) -> str:
    try:
        loaded = load_dogfood_run(root, run_id)
    except KeyError as exc:
        raise DogfoodCommandError(str(exc)) from exc
    return loaded["report"]


@dogfood_app.command("list")
def dogfood_list() -> None:
    """List built-in dogfood production-readiness cases."""
    typer.echo(render_dogfood_list(Path.cwd()), nl=False)


@dogfood_app.command("show")
def dogfood_show(case_id: str) -> None:
    """Show a built-in dogfood case definition."""
    try:
        typer.echo(render_dogfood_show(Path.cwd(), case_id), nl=False)
    except DogfoodCommandError as exc:
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
        output = run_dogfood_command(
            Path.cwd(),
            suite=suite,
            case_ids=case,
            write_root_runtime_evidence=write_root_runtime_evidence,
            keep_runs=keep_runs,
            fail_below_silver=fail_below_silver,
        )
    except DogfoodCommandError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for line in output.lines:
        typer.echo(line)
    if output.exit_code:
        raise typer.Exit(code=output.exit_code)


@dogfood_app.command("score")
def dogfood_score(run_id: str) -> None:
    """Show a dogfood scorecard summary for a run id, or 'latest'."""
    try:
        typer.echo(render_dogfood_score_for_run(Path.cwd(), run_id), nl=False)
    except DogfoodCommandError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@dogfood_app.command("report")
def dogfood_report(run_id: str) -> None:
    """Print a dogfood report for a run id, or 'latest'."""
    try:
        typer.echo(render_dogfood_report_for_run(Path.cwd(), run_id), nl=False)
    except DogfoodCommandError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
