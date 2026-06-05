from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from devflow.control_room.dogfood import load_dogfood_run
from devflow.control_room.git_state import inspect_git_state
from devflow.control_room.operating_layer_visual_qa import DEFAULT_VISUAL_QA_DIR, VIEWPORTS
from devflow.control_room.paths import relative_path


SCHEMA_VERSION = 1
PRODUCTION_READINESS_SUITE = "production-readiness"
PYTEST_COMMAND = "PYTHONPATH=src:. .venv/bin/pytest -q"
GIT_STATUS_COMMAND = "PYTHONPATH=src:. .venv/bin/devflow git status"
DOGFOOD_COMMAND = "PYTHONPATH=src:. .venv/bin/devflow dogfood run --suite production-readiness"
VISUAL_QA_COMMAND = (
    "PYTHONPATH=src:. .venv/bin/devflow operating-layer visual-qa --write-current --update-baseline --json"
)
STALE_CONTEXT_COMMAND = (
    "rg -n \"(must use /Users/jewelbait/Desktop/DevFlow|old checkout path is current|"
    "legacy workflow authority|autonomous routing is active)\" "
    "AGENTS.md PRODUCT_NORTH_STAR.md README.md docs src/devflow/control_room tests "
    "--glob '!src/devflow/control_room/release_readiness.py'"
)


def build_release_readiness_report(
    root: Path,
    *,
    pytest_evidence: Path | None = None,
    stale_context_evidence: Path | None = None,
    dogfood_run_id: str = "latest",
) -> dict[str, Any]:
    project_root = root.resolve()
    checks = [
        _git_status_check(project_root),
        _pytest_check(project_root, pytest_evidence),
        _dogfood_check(project_root, dogfood_run_id),
        _visual_qa_check(project_root, dogfood_run_id),
        _stale_context_check(project_root, stale_context_evidence),
        _handoff_check(project_root),
    ]
    status = "passed" if all(check["status"] == "passed" for check in checks) else "blocked"
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "project_root": project_root.as_posix(),
        "checks": checks,
        "next_safe_action": _next_safe_action(checks),
    }


def render_release_readiness_report(report: dict[str, Any]) -> str:
    lines = [
        "# Dev-Flow Release Readiness",
        "",
        f"status: {report['status']}",
        "",
        "## Checks",
        "",
    ]
    for check in report["checks"]:
        evidence = ", ".join(check["evidence"]) if check["evidence"] else "none"
        lines.extend(
            [
                f"- {check['id']}: {check['status']}",
                f"  command: `{check['command']}`",
                f"  evidence: {evidence}",
                f"  details: {check['details']}",
            ]
        )
    lines.extend(["", "## Next Safe Action", "", f"- {report['next_safe_action']}", ""])
    return "\n".join(lines)


def _git_status_check(root: Path) -> dict[str, Any]:
    state = inspect_git_state(root)
    passed = bool(state.is_repo and not state.dirty and state.operation_in_progress is None and state.branch == "main")
    details = "clean main checkout" if passed else "expected a clean main checkout with no Git operation in progress"
    return _check(
        "clean-devflow-git-status",
        "Clean Dev-Flow Git status",
        "passed" if passed else "failed",
        GIT_STATUS_COMMAND,
        [state.head_sha] if state.head_sha else [],
        details,
    )


def _pytest_check(root: Path, evidence: Path | None) -> dict[str, Any]:
    if evidence is None:
        return _check(
            "full-pytest",
            "Full pytest suite",
            "needs_evidence",
            PYTEST_COMMAND,
            [],
            "provide --pytest-evidence pointing at the full-suite pytest output",
        )
    path = _evidence_path(root, evidence)
    if not path.exists():
        return _check(
            "full-pytest",
            "Full pytest suite",
            "needs_evidence",
            PYTEST_COMMAND,
            [relative_path(root, path)],
            "pytest evidence file is missing",
        )
    text = path.read_text(encoding="utf-8", errors="replace")
    passed = bool(re.search(r"\b\d+\s+passed\b", text)) and not re.search(r"\bfailed\b|\berrors?\b", text, re.I)
    return _check(
        "full-pytest",
        "Full pytest suite",
        "passed" if passed else "failed",
        PYTEST_COMMAND,
        [relative_path(root, path)],
        "full pytest evidence reports passing tests" if passed else "pytest evidence does not prove a clean full-suite pass",
    )


def _dogfood_check(root: Path, run_id: str) -> dict[str, Any]:
    try:
        loaded = load_dogfood_run(root, run_id)
    except KeyError as exc:
        return _check(
            "dogfood-production-readiness",
            "Production-readiness dogfood",
            "needs_evidence",
            DOGFOOD_COMMAND,
            [],
            str(exc),
        )
    scorecard = loaded["scorecard"]
    suite_ok = scorecard.get("suite") == PRODUCTION_READINESS_SUITE or loaded["run"].get("suite") == PRODUCTION_READINESS_SUITE
    silver = bool((scorecard.get("threshold_result") or {}).get("silver_met"))
    passed = suite_ok and silver
    evidence = [relative_path(root, loaded["run_dir"] / "scorecard.yaml")]
    return _check(
        "dogfood-production-readiness",
        "Production-readiness dogfood",
        "passed" if passed else "failed",
        DOGFOOD_COMMAND,
        evidence,
        "latest production-readiness dogfood met Silver" if passed else "dogfood evidence must be production-readiness and Silver-or-better",
    )


def _visual_qa_check(root: Path, run_id: str) -> dict[str, Any]:
    dogfood_evidence = _dogfood_visual_evidence(root, run_id)
    direct_evidence = _direct_visual_qa_evidence(root)
    if dogfood_evidence or direct_evidence:
        return _check(
            "operating-layer-visual-qa-evidence",
            "Operating-layer visual QA evidence",
            "passed",
            VISUAL_QA_COMMAND,
            dogfood_evidence + direct_evidence,
            "desktop/mobile visual QA evidence is present",
        )
    return _check(
        "operating-layer-visual-qa-evidence",
        "Operating-layer visual QA evidence",
        "needs_evidence",
        VISUAL_QA_COMMAND,
        [],
        "write or seed desktop/mobile current and baseline visual QA artifacts",
    )


def _stale_context_check(root: Path, evidence: Path | None) -> dict[str, Any]:
    if evidence is None:
        return _check(
            "stale-context-scan",
            "Stale-context poison scan",
            "needs_evidence",
            STALE_CONTEXT_COMMAND,
            [],
            "provide --stale-context-evidence from the stale-context scan",
        )
    path = _evidence_path(root, evidence)
    if not path.exists():
        return _check(
            "stale-context-scan",
            "Stale-context poison scan",
            "needs_evidence",
            STALE_CONTEXT_COMMAND,
            [relative_path(root, path)],
            "stale-context evidence file is missing",
        )
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    passed = not text or text.lower() in {"no matches", "0 matches"}
    return _check(
        "stale-context-scan",
        "Stale-context poison scan",
        "passed" if passed else "failed",
        STALE_CONTEXT_COMMAND,
        [relative_path(root, path)],
        "stale-context scan found no unreviewed matches" if passed else "stale-context scan has matches that need review or cleanup",
    )


def _handoff_check(root: Path) -> dict[str, Any]:
    path = root / "docs" / "handoff-template.md"
    passed = path.exists()
    return _check(
        "standard-handoff-report",
        "Standard handoff report",
        "passed" if passed else "needs_evidence",
        "write final report using docs/handoff-template.md",
        [relative_path(root, path)] if passed else [],
        "standard handoff template is available" if passed else "docs/handoff-template.md is missing",
    )


def _dogfood_visual_evidence(root: Path, run_id: str) -> list[str]:
    try:
        loaded = load_dogfood_run(root, run_id)
    except KeyError:
        return []
    visual_case_dir = loaded["run_dir"] / "cases" / "operating-layer-visual-qa-hardening"
    visual_result = visual_case_dir / "artifacts" / "visual-qa-result.json"
    case_status = {
        item.get("case_id"): item.get("status")
        for item in loaded["run"].get("cases_run", [])
        if isinstance(item, dict)
    }
    if case_status.get("operating-layer-visual-qa-hardening") == "passed" and visual_result.exists():
        return [relative_path(root, visual_result)]
    return []


def _direct_visual_qa_evidence(root: Path) -> list[str]:
    base = root / DEFAULT_VISUAL_QA_DIR
    evidence: list[str] = []
    for viewport in VIEWPORTS:
        name = str(viewport["name"])
        required = [
            base / "current" / f"{name}.png",
            base / "baseline" / f"{name}.png",
            base / "current" / f"{name}.svg",
            base / "baseline" / f"{name}.svg",
        ]
        if not all(path.exists() for path in required):
            return []
        evidence.extend(relative_path(root, path) for path in required)
    return evidence


def _next_safe_action(checks: list[dict[str, Any]]) -> str:
    first_blocked = next((check for check in checks if check["status"] != "passed"), None)
    if first_blocked is None:
        return "Release readiness is satisfied; tag or build the release from this clean checkpoint after human approval."
    return f"Run or repair the first blocked gate: {first_blocked['label'].lower()} ({first_blocked['details']})."


def _evidence_path(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _check(
    check_id: str,
    label: str,
    status: str,
    command: str,
    evidence: list[str],
    details: str,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "command": command,
        "evidence": evidence,
        "details": details,
    }
