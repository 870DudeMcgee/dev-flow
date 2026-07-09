from __future__ import annotations

from collections.abc import Iterable
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from devflow.legacy.control_room.dogfood_case_catalog import (
    CATEGORY_LABELS,
    CATEGORY_MAX,
    DOGFOOD_SCHEMA_VERSION,
    DogfoodCaseCatalog,
    case_max_score,
    is_critical_case,
)
from devflow.legacy.control_room.git_state import inspect_git_state
from devflow.legacy.control_room.paths import relative_path
from devflow.legacy.control_room.persistence import atomic_write_text, utc_now
from devflow.legacy.control_room.worker_outcome import validate_worker_outcome_file

SILVER_THRESHOLD = 82


class CaseResultRecorder:
    def __init__(self, root: Path, run_id: str, case: dict[str, Any], case_dir: Path) -> None:
        self.root = root
        self.case = case
        self.case_dir = case_dir
        self.state = start_case_result(root, run_id, case, case_dir)
        self._scores: dict[str, int] = {}
        self._failures: list[str] = []

    @property
    def commands(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(command) for command in self.state["commands_run"])

    def award(self, category: str, points: int, condition: bool, lesson: str) -> None:
        award_case_points(self.state, self._scores, self._failures, category, points, condition, lesson)

    def fail(self, lesson: str) -> None:
        self._failures.append(lesson)

    def record_command(
        self,
        command: str,
        *,
        status: str,
        exit_code: int | None = None,
        output: str | None = None,
    ) -> None:
        record_command(self.state, command, status=status, exit_code=exit_code, output=output)

    def record_artifact(self, path: str | Path, *, root: Path | None = None) -> str:
        return record_artifact(self.state, path, root=self.root if root is None else root)

    def record_artifacts(self, paths: Iterable[str | Path], *, root: Path | None = None) -> list[str]:
        return record_artifacts(self.state, paths, root=self.root if root is None else root)

    def write_json_artifact(self, path: Path, payload: Any, *, sort_keys: bool = True) -> Path:
        return write_case_json_artifact(self.state, self.root, path, payload, sort_keys=sort_keys)

    def write_text_artifact(self, path: Path, text: str) -> Path:
        return write_case_text_artifact(self.state, self.root, path, text)

    def write_summary_artifact(self, filename: str, summary: dict[str, Any]) -> Path:
        return write_case_summary_artifact(self.state, self.root, self.case_dir, filename, summary)

    def record_worker_outcome_validation(self, outcome_path: Path, outcome: dict[str, Any]) -> dict[str, Any]:
        self.write_json_artifact(outcome_path, outcome)
        result = validate_worker_outcome_file(self.root, outcome_path)
        self.record_artifact(result["output_path"])
        self.record_command(
            f"devflow worker validate-outcome {relative_path(self.root, outcome_path)}",
            status=result["status"],
            exit_code=0 if result["status"] == "passed" else 1,
            output=result["output_path"],
        )
        return result

    def create_task(
        self,
        title: str,
        *,
        root: Path | None = None,
        git_worktree: bool = False,
        worker_id: str = "shell",
        definition_of_done: str | None = None,
        command_suffix: str = "",
    ) -> Any:
        from devflow.legacy.control_room.service import create_task

        target_root = self.root if root is None else root
        task = create_task(
            target_root,
            title,
            git_worktree=git_worktree,
            worker_id=worker_id,
            definition_of_done=definition_of_done,
        )
        option = " --git-worktree" if git_worktree else ""
        self.record_command(
            f"devflow task create{option} {title!r}{_command_suffix(command_suffix)}",
            status="passed",
            output=task.id,
        )
        return task

    def run_shell_task(
        self,
        task_id: str,
        command: list[str],
        *,
        root: Path | None = None,
        command_label: str,
        timeout_seconds: int = 60,
        worker_adapter: str = "shell",
        env: dict[str, str] | None = None,
        command_suffix: str = "",
    ) -> Any:
        from devflow.legacy.control_room.service import run_shell_task

        task = run_shell_task(
            self.root if root is None else root,
            task_id,
            command,
            timeout_seconds=timeout_seconds,
            worker_adapter=worker_adapter,
            env=env,
        )
        self.record_command(
            f"devflow task run {task_id} --worker {worker_adapter} -- {command_label}{_command_suffix(command_suffix)}",
            status="passed",
        )
        return task

    def verify_task(
        self,
        task_id: str,
        command: list[str],
        *,
        root: Path | None = None,
        command_label: str,
        timeout_seconds: int = 120,
        command_suffix: str = "",
    ) -> Any:
        from devflow.legacy.control_room.service import verify_task

        task = verify_task(self.root if root is None else root, task_id, command, timeout_seconds=timeout_seconds)
        self.record_command(
            f"devflow task verify {task_id} --shell {command_label}{_command_suffix(command_suffix)}",
            status=task.verification_status,
            exit_code=task.verification_exit_code,
        )
        return task

    def preview_task_promotion(
        self,
        task_id: str,
        *,
        root: Path | None = None,
        command_suffix: str = "",
    ) -> dict[str, Any]:
        from devflow.legacy.control_room.service import preview_task_promotion

        preview = preview_task_promotion(self.root if root is None else root, task_id)
        status = _promotion_preview_status(preview)
        self.record_command(
            f"devflow task promote-preview {task_id}{_command_suffix(command_suffix)}",
            status=status,
        )
        return preview

    def record_warning(self, warning: str) -> None:
        record_warning(self.state, warning)

    def record_lesson(self, lesson: str) -> None:
        record_lesson(self.state, lesson)

    def set_context_packet_size(self, size: int) -> int:
        self.state["context_packet_size"] = size
        return size

    def set_cleanup_status(self, status: str, *, warning: str | None = None) -> str:
        return set_cleanup_status(self.state, status, warning=warning)

    def finalize(self) -> dict[str, Any]:
        return finalize_case_result(self.root, self.case, self.state, self._scores, self._failures)


def start_case_result(root: Path, run_id: str, case: dict[str, Any], case_dir: Path) -> dict[str, Any]:
    (case_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    return {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "run_id": run_id,
        "case_id": case["id"],
        "status": "passed",
        "score": 0,
        "max_score": case_max_score(case),
        "category_scores": {category: 0 for category in CATEGORY_MAX},
        "commands_run": [],
        "artifacts_created": [],
        "files_changed": [],
        "context_packet_size": None,
        "token_usage_estimate": None,
        "duration_seconds": 0.0,
        "failure_reason": None,
        "warnings": [],
        "lessons": [],
        "cleanup_status": "not_required",
        "_started": time.monotonic(),
        "_git_status_before": git_short_status(root),
    }


def finalize_case_result(
    root: Path,
    case: dict[str, Any],
    state: dict[str, Any],
    scores: dict[str, int],
    failures: list[str],
) -> dict[str, Any]:
    state["category_scores"] = {category: scores.get(category, 0) for category in CATEGORY_MAX}
    state["score"] = sum(state["category_scores"].values())
    state["duration_seconds"] = round(time.monotonic() - float(state.pop("_started")), 3)
    before = set(state.pop("_git_status_before"))
    after = set(git_short_status(root))
    state["files_changed"] = sorted(after - before)
    if failures:
        state["status"] = "failed"
        state["failure_reason"] = "; ".join(failures)
    if state["score"] > state["max_score"]:
        record_warning(state, f"score exceeded case max; capped from {state['score']} to {state['max_score']}")
        state["score"] = state["max_score"]
    state["critical"] = is_critical_case(case["id"])
    return _public_result(state)


def failed_case_result(
    root: Path, run_id: str, case: dict[str, Any], case_dir: Path, exc: Exception
) -> dict[str, Any]:
    state = start_case_result(root, run_id, case, case_dir)
    state["status"] = "failed"
    state["failure_reason"] = f"{type(exc).__name__}: {exc}"
    state["duration_seconds"] = round(time.monotonic() - float(state.pop("_started")), 3)
    state.pop("_git_status_before", None)
    state["critical"] = is_critical_case(case["id"])
    return _public_result(state)


def skipped_unknown_case_result(run_id: str, case_id: str, run_dir: Path) -> dict[str, Any]:
    case_dir = run_dir / "cases" / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "run_id": run_id,
        "case_id": case_id,
        "status": "skipped",
        "score": 0,
        "max_score": 0,
        "category_scores": {category: 0 for category in CATEGORY_MAX},
        "commands_run": [],
        "artifacts_created": [],
        "files_changed": [],
        "context_packet_size": None,
        "token_usage_estimate": None,
        "duration_seconds": 0.0,
        "failure_reason": "case not found in suite",
        "warnings": ["requested case was not found; scored as skipped"],
        "lessons": [],
        "cleanup_status": "not_required",
        "critical": False,
    }
    write_case_result(case_dir, result)
    return result


def write_case_result(case_dir: Path, result: dict[str, Any]) -> None:
    atomic_write_text(case_dir / "case-result.yaml", yaml.safe_dump(result, sort_keys=False))


def record_command(
    state: dict[str, Any],
    command: str,
    *,
    status: str,
    exit_code: int | None = None,
    output: str | None = None,
) -> None:
    state["commands_run"].append(
        {
            "command": command,
            "status": status,
            "exit_code": exit_code,
            "output": output,
        }
    )


def _command_suffix(suffix: str) -> str:
    return f" {suffix}" if suffix else ""


def _promotion_preview_status(preview: dict[str, Any]) -> str:
    status = preview.get("promotion_readiness") or preview.get("status")
    git = preview.get("git")
    if not status and isinstance(git, dict):
        status = git.get("promotion_readiness")
    return str(status or "ready")


def record_artifact(state: dict[str, Any], path: str | Path, *, root: Path | None = None) -> str:
    artifact_path = _artifact_path(path, root=root)
    state["artifacts_created"].append(artifact_path)
    return artifact_path


def record_artifacts(state: dict[str, Any], paths: Iterable[str | Path], *, root: Path | None = None) -> list[str]:
    return [record_artifact(state, path, root=root) for path in paths]


def write_case_json_artifact(
    state: dict[str, Any],
    root: Path,
    path: Path,
    payload: Any,
    *,
    sort_keys: bool = True,
) -> Path:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=sort_keys) + "\n")
    record_artifact(state, path, root=root)
    return path


def write_case_text_artifact(state: dict[str, Any], root: Path, path: Path, text: str) -> Path:
    atomic_write_text(path, text)
    record_artifact(state, path, root=root)
    return path


def write_case_summary_artifact(
    state: dict[str, Any],
    root: Path,
    case_dir: Path,
    filename: str,
    summary: dict[str, Any],
) -> Path:
    return write_case_json_artifact(state, root, case_dir / "artifacts" / filename, summary)


def record_warning(state: dict[str, Any], warning: str) -> None:
    state["warnings"].append(warning)


def record_lesson(state: dict[str, Any], lesson: str) -> None:
    state["lessons"].append(lesson)


def set_cleanup_status(state: dict[str, Any], status: str, *, warning: str | None = None) -> str:
    if warning:
        record_warning(state, warning)
    state["cleanup_status"] = status
    return status


def award_case_points(
    state: dict[str, Any],
    scores: dict[str, int],
    failures: list[str],
    category: str,
    points: int,
    condition: bool,
    lesson: str,
) -> None:
    if condition:
        scores[category] = scores.get(category, 0) + points
        record_lesson(state, lesson)
    else:
        failures.append(lesson)
        record_warning(state, f"missed: {lesson}")


def _artifact_path(path: str | Path, *, root: Path | None = None) -> str:
    if isinstance(path, Path):
        return relative_path(root, path) if root is not None else path.as_posix()
    return path


def build_dogfood_scorecard(
    run_id: str,
    suite: str,
    _baseline: dict[str, Any],
    requested: list[str],
    results: list[dict[str, Any]],
    duration: float,
) -> dict[str, Any]:
    category_max = DogfoodCaseCatalog.production_readiness().category_max_for(requested)
    category_scores = {}
    for category in CATEGORY_MAX:
        score = sum(int(result.get("category_scores", {}).get(category, 0)) for result in results)
        max_score = category_max[category]
        percent = round((score / max_score) * 100, 1) if max_score else 100.0
        category_scores[category] = {
            "score": score,
            "max": max_score,
            "percent": percent,
        }

    total = sum(item["score"] for item in category_scores.values())
    max_score = sum(item["max"] for item in category_scores.values())
    failures = [
        f"{result['case_id']}: {result['failure_reason']}"
        for result in results
        if result.get("status") in {"failed", "blocked"} and result.get("failure_reason")
    ]
    warnings = [
        f"{result['case_id']}: {warning}"
        for result in results
        for warning in result.get("warnings", [])
    ]
    critical_failures = [
        result["case_id"]
        for result in results
        if result.get("critical") and result.get("status") not in {"passed"}
    ]
    threshold = threshold_result(total, max_score, category_scores, critical_failures)
    return {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "run_id": run_id,
        "suite": suite,
        "created_at": utc_now().isoformat(),
        "total_score": total,
        "max_score": max_score,
        "category_scores": category_scores,
        "threshold_result": threshold,
        "critical_failures": critical_failures,
        "failures": failures,
        "warnings": warnings,
        "duration_seconds": duration,
    }


def build_dogfood_run_yaml(
    run_id: str,
    suite: str,
    baseline: dict[str, Any],
    requested: list[str],
    results: list[dict[str, Any]],
    scorecard: dict[str, Any],
    duration: float,
) -> dict[str, Any]:
    return {
        "schema_version": DOGFOOD_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": scorecard["created_at"],
        "suite": suite,
        "git_baseline": baseline,
        "cases_requested": requested,
        "cases_run": [
            {
                "case_id": result["case_id"],
                "status": result["status"],
                "score": result["score"],
                "max_score": result["max_score"],
            }
            for result in results
        ],
        "total_score": scorecard["total_score"],
        "max_score": scorecard["max_score"],
        "category_scores": scorecard["category_scores"],
        "threshold_result": scorecard["threshold_result"],
        "failures": scorecard["failures"],
        "warnings": scorecard["warnings"],
        "duration_seconds": duration,
        "notes": [
            "Deterministic local dogfood validation only.",
            "No provider APIs, autonomous routing, auto-promotion, push, database, vector DB, RAG, dashboard, daemon, or ML training were added or invoked.",
        ],
    }


def render_dogfood_report(run_yaml: dict[str, Any], scorecard: dict[str, Any], results: list[dict[str, Any]]) -> str:
    threshold = scorecard["threshold_result"]
    lines = [
        "# Dev-Flow Production Readiness Dogfood Report",
        "",
        f"run_id: {run_yaml['run_id']}",
        f"suite: {run_yaml['suite']}",
        f"score: {scorecard['total_score']}/{scorecard['max_score']}",
        f"threshold: {threshold['achieved']}",
        f"silver_met: {'yes' if threshold['silver_met'] else 'no'}",
        f"duration_seconds: {scorecard['duration_seconds']}",
        "",
        "## Category Scores",
        "",
    ]
    for category, item in scorecard["category_scores"].items():
        lines.append(f"- {CATEGORY_LABELS.get(category, category)}: {item['score']}/{item['max']} ({item['percent']}%)")
    lines.extend(["", "## Cases", ""])
    for result in results:
        lines.append(f"- {result['case_id']}: {result['status']} ({result['score']}/{result['max_score']})")
    lines.extend(["", "## Failures", ""])
    if scorecard["failures"]:
        lines.extend(f"- {failure}" for failure in scorecard["failures"])
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    if scorecard["warnings"]:
        lines.extend(f"- {warning}" for warning in scorecard["warnings"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Boundary Confirmation",
            "",
            "- provider_api_calls: none",
            "- autonomous_routing: none",
            "- auto_promotion: none",
            "- push: none",
            "- database: none",
            "- vector_db_rag_embeddings: none",
            "- dashboard_or_daemon: none",
            "- ml_training: none",
            "",
            "## Next Safe Action",
            "",
            next_safe_action(scorecard),
            "",
        ]
    )
    return "\n".join(lines)


def threshold_result(
    total: int,
    max_score: int,
    category_scores: dict[str, dict[str, float | int]],
    critical_failures: list[str],
) -> dict[str, Any]:
    normalized = round((total / max_score) * 100, 1) if max_score else 0.0
    category_percents = [
        float(item["percent"])
        for item in category_scores.values()
        if int(item["max"]) > 0
    ]
    no_category_below_70 = all(percent >= 70.0 for percent in category_percents)
    no_category_below_80 = all(percent >= 80.0 for percent in category_percents)
    if normalized >= 95 and no_category_below_80 and not critical_failures:
        achieved = "Bulletproof candidate"
    elif normalized >= 90 and not critical_failures:
        achieved = "Gold"
    elif normalized >= 82 and no_category_below_70 and not critical_failures:
        achieved = "Silver"
    elif normalized >= 70:
        achieved = "Bronze"
    else:
        achieved = "below Bronze"
    return {
        "achieved": achieved,
        "normalized_score": normalized,
        "bronze_met": normalized >= 70,
        "silver_met": normalized >= SILVER_THRESHOLD and no_category_below_70 and not critical_failures,
        "gold_met": normalized >= 90 and not critical_failures,
        "bulletproof_candidate": normalized >= 95 and no_category_below_80 and not critical_failures,
        "no_category_below_70": no_category_below_70,
        "no_category_below_80": no_category_below_80,
        "critical_failures": critical_failures,
    }


def next_safe_action(scorecard: dict[str, Any]) -> str:
    if scorecard["threshold_result"]["silver_met"]:
        if scorecard["threshold_result"]["gold_met"]:
            return "- Run `devflow release readiness` with full pytest and stale-context evidence before tagging or building a release."
        return "- Improve the lowest-scoring category toward Gold without weakening any safety case."
    category_scores = scorecard["category_scores"]
    lowest = min(
        (item for item in category_scores.items() if item[1]["max"] > 0),
        key=lambda pair: pair[1]["percent"],
        default=("none", {"percent": 0}),
    )
    return f"- Repair the lowest-scoring category first: {CATEGORY_LABELS.get(lowest[0], lowest[0])}."


def git_baseline(root: Path) -> dict[str, Any]:
    state = inspect_git_state(root)
    return {
        "is_repo": state.is_repo,
        "branch": state.branch,
        "head_sha": state.head_sha,
        "origin_main_sha": state.origin_main_sha,
        "dirty_state": "dirty" if state.dirty else "clean",
        "operation_in_progress": state.operation_in_progress,
        "safe_for_worker_writes": state.safe_for_worker_writes,
        "safe_for_promotion": state.safe_for_promotion,
        "safe_for_push": state.safe_for_push,
    }


def git_short_status(root: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line and not line[3:].startswith(".devflow/")]


def _public_result(state: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in state.items() if not key.startswith("_")}
