from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

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
