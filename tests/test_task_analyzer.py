"""Tests for the task analyzer (M4-S2)."""

from __future__ import annotations


import pytest

from devflow.control_plane.task_analyzer import (
    Confidence,
    RiskLevel,
    TaskAnalysis,
    WorkflowFamily,
    analyze_task,
)
from devflow.loop.scout_discovery import AgentScoutDiscovery


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scout(
    files: list[str] | None = None,
    tests: list[str] | None = None,
    risks: list[str] | None = None,
    lane: str = "direct_tiny_edit",
) -> AgentScoutDiscovery:
    return AgentScoutDiscovery(
        handoff_path=None,
        handoff_read=False,
        files_to_touch=files or [],
        files_to_read_next=[],
        tests=tests or [],
        risks=risks or [],
        recommended_lane=lane,
        verification="",
        map_freshness={},
        evidence_paths=[],
        context_brief=[],
    )


# ---------------------------------------------------------------------------
# Family classification tests
# ---------------------------------------------------------------------------

def test_emits_family_and_approvals() -> None:
    """analyze_task returns WorkflowFamily + required_approvals."""
    scout = _scout(files=["src/main.py"], tests=["test_main.py"], lane="direct_tiny_edit")
    analysis = analyze_task(scout, task_id="t-1", title="Fix bug in main")

    assert isinstance(analysis, TaskAnalysis)
    assert isinstance(analysis.family, WorkflowFamily)
    assert isinstance(analysis.required_approvals, tuple)


def test_hotfix_classification() -> None:
    """Small fix → hotfix."""
    scout = _scout(files=["src/main.py"], tests=["test_main.py"], lane="direct_tiny_edit")
    analysis = analyze_task(scout, task_id="t-1", title="Fix crash in parser")

    assert analysis.family == WorkflowFamily.hotfix
    assert analysis.confidence == Confidence.high


def test_feature_classification() -> None:
    """New files → feature."""
    scout = _scout(
        files=["src/new_module.py", "src/api.py", "src/models.py", "src/handlers.py"],
        tests=[],
        lane="builder",
    )
    analysis = analyze_task(scout, task_id="t-1", title="Add new feature module")

    assert analysis.family == WorkflowFamily.feature


def test_bug_classification() -> None:
    """Test-heavy, bug title → bug."""
    scout = _scout(files=["test_repro.py"], tests=["test_repro.py"], lane="direct_tiny_edit")
    analysis = analyze_task(scout, task_id="t-1", title="Reproduce race condition bug")

    assert analysis.family == WorkflowFamily.bug


def test_chore_classification() -> None:
    """Config/lint → chore."""
    scout = _scout(files=["pyproject.toml", ".ruff.toml"], tests=[], lane="direct_tiny_edit")
    analysis = analyze_task(scout, task_id="t-1", title="Update lint config")

    assert analysis.family == WorkflowFamily.chore


def test_chore_from_file_patterns() -> None:
    """All config files → chore even without title."""
    scout = _scout(files=["config.yaml", "settings.json"], tests=[], lane="direct_tiny_edit")
    analysis = analyze_task(scout, task_id="t-1")

    assert analysis.family == WorkflowFamily.chore


def test_unknown_when_uncertain() -> None:
    """Ambiguous → unknown."""
    scout = _scout(files=["src/main.py"], tests=[], lane="builder")
    analysis = analyze_task(scout, task_id="t-1", title="Update something")

    assert analysis.family == WorkflowFamily.unknown
    assert analysis.confidence == Confidence.low


# ---------------------------------------------------------------------------
# Risk classification tests
# ---------------------------------------------------------------------------

def test_risk_level_low() -> None:
    """1 file, has tests → low."""
    scout = _scout(files=["src/main.py"], tests=["test_main.py"], lane="direct_tiny_edit")
    analysis = analyze_task(scout, task_id="t-1", title="Fix typo")

    assert analysis.risk == RiskLevel.low


def test_risk_level_high_many_files() -> None:
    """Many files → high."""
    scout = _scout(
        files=["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
        tests=[],
        lane="builder",
    )
    analysis = analyze_task(scout, task_id="t-1", title="Refactor module")

    assert analysis.risk == RiskLevel.high


def test_risk_level_high_no_tests() -> None:
    """No tests, >2 files → high."""
    scout = _scout(files=["a.py", "b.py", "c.py"], tests=[], lane="builder")
    analysis = analyze_task(scout, task_id="t-1", title="Update modules")

    assert analysis.risk == RiskLevel.high


def test_risk_level_high_from_keywords() -> None:
    """Security/migration keywords → high."""
    scout = _scout(
        files=["src/auth.py"],
        tests=["test_auth.py"],
        risks=["security-sensitive migration"],
        lane="direct_tiny_edit",
    )
    analysis = analyze_task(scout, task_id="t-1", title="Fix auth")

    assert analysis.risk == RiskLevel.high


def test_risk_level_medium_default() -> None:
    """3 files with tests → medium."""
    scout = _scout(
        files=["a.py", "b.py", "c.py"],
        tests=["test_a.py"],
        lane="builder",
    )
    analysis = analyze_task(scout, task_id="t-1", title="Update")

    assert analysis.risk == RiskLevel.medium


# ---------------------------------------------------------------------------
# Required approvals tests
# ---------------------------------------------------------------------------

def test_required_approvals_high_risk() -> None:
    """High risk → human_merge_approval."""
    scout = _scout(
        files=["a.py", "b.py", "c.py", "d.py", "e.py", "f.py"],
        tests=[],
        lane="builder",
    )
    analysis = analyze_task(scout, task_id="t-1", title="Big change")

    assert "human_merge_approval" in analysis.required_approvals


def test_required_approvals_hotfix_review() -> None:
    """Hotfix with non-low risk → human_review."""
    scout = _scout(
        files=["src/main.py", "src/api.py", "src/db.py"],
        tests=[],
        lane="direct_tiny_edit",
    )
    analysis = analyze_task(scout, task_id="t-1", title="Fix critical bug")

    assert analysis.family == WorkflowFamily.hotfix
    assert analysis.risk == RiskLevel.high
    assert "human_review" in analysis.required_approvals


def test_no_approvals_for_low_risk() -> None:
    """Low risk → no approvals."""
    scout = _scout(files=["src/main.py"], tests=["test_main.py"], lane="direct_tiny_edit")
    analysis = analyze_task(scout, task_id="t-1", title="Fix typo")

    assert analysis.required_approvals == ()


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

def test_affected_areas() -> None:
    """Affected areas derived from file paths."""
    scout = _scout(
        files=["src/main.py", "tests/test_main.py"],
        tests=["tests/test_main.py"],
        lane="direct_tiny_edit",
    )
    analysis = analyze_task(scout, task_id="t-1", title="Fix")

    assert "src" in analysis.affected_areas
    assert "tests" in analysis.affected_areas


def test_recommended_scope() -> None:
    """Scope summary includes file and test count."""
    scout = _scout(files=["a.py", "b.py"], tests=["test_a.py"], lane="direct_tiny_edit")
    analysis = analyze_task(scout, task_id="t-1", title="Fix")

    assert "2 file" in analysis.recommended_scope
    assert "1 test" in analysis.recommended_scope


def test_task_analysis_frozen() -> None:
    """TaskAnalysis is immutable."""
    scout = _scout(files=["a.py"], tests=[], lane="direct_tiny_edit")
    analysis = analyze_task(scout, task_id="t-1", title="Fix")

    with pytest.raises(Exception):
        analysis.family = WorkflowFamily.feature  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Legacy compatibility
# ---------------------------------------------------------------------------

def test_legacy_scout_output_preserved() -> None:
    """AgentScoutDiscovery is unchanged after analysis."""
    scout = _scout(files=["src/main.py"], tests=["test_main.py"], lane="direct_tiny_edit")
    original_files = list(scout.files_to_touch)
    original_tests = list(scout.tests)

    analyze_task(scout, task_id="t-1", title="Fix")

    assert scout.files_to_touch == original_files
    assert scout.tests == original_tests
