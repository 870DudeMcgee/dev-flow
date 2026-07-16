"""Task Analyzer — typed workflow-family classification (M4-S2, blueprint §4.5/§5.2).

Formalizes the output of ``discover_agent_scout_context`` into a typed
:class:`TaskAnalysis` object carrying workflow family, risk level, and required
approvals. This object is consumed by the compiler (M5) and the control-plane
ticket contract.

Legacy ``AgentScoutDiscovery`` is unchanged — the analyzer reads it additively.

All names are functional — no model identity (naming rule).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from devflow.loop.scout_discovery import AgentScoutDiscovery


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WorkflowFamily(str, Enum):
    """Blueprint §8 workflow families."""

    hotfix = "hotfix"
    feature = "feature"
    bug = "bug"
    chore = "chore"
    unknown = "unknown"


class RiskLevel(str, Enum):
    """Risk classification for a task."""

    low = "low"
    medium = "medium"
    high = "high"


class Confidence(str, Enum):
    """How confident the analyzer is in its classification."""

    low = "low"
    medium = "medium"
    high = "high"


# ---------------------------------------------------------------------------
# TaskAnalysis model
# ---------------------------------------------------------------------------

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"


class TaskAnalysis(BaseModel):
    """Typed analyzer output consumed by the compiler and control plane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(pattern=_ID_PATTERN)
    family: WorkflowFamily = WorkflowFamily.unknown
    risk: RiskLevel = RiskLevel.medium
    required_approvals: tuple[str, ...] = ()
    affected_areas: tuple[str, ...] = ()
    recommended_scope: str = ""
    confidence: Confidence = Confidence.low


# ---------------------------------------------------------------------------
# Classification heuristics
# ---------------------------------------------------------------------------

# File patterns that suggest each family.
_HOTFIX_PATTERNS = ("fix", "patch", "hotfix", "repair")
_FEATURE_PATTERNS = ("new", "add", "create", "implement", "feature")
_BUG_PATTERNS = ("bug", "crash", "error", "fail", "repro", "regression")
_CHORE_PATTERNS = ("lint", "format", "config", "refactor", "cleanup", "dependency", "upgrade")

# File types that suggest a bug workflow.
_TEST_PATH_INDICATORS = ("test", "spec", "conftest")


def _classify_family(
    scout: AgentScoutDiscovery,
    title: str = "",
) -> tuple[WorkflowFamily, Confidence]:
    """Classify the workflow family from scout output + title.

    Returns (family, confidence).
    """
    title_lower = title.lower()
    files = scout.files_to_touch
    lane = scout.recommended_lane

    # Strong signal from title
    for pattern in _HOTFIX_PATTERNS:
        if pattern in title_lower:
            return WorkflowFamily.hotfix, Confidence.high
    for pattern in _BUG_PATTERNS:
        if pattern in title_lower:
            return WorkflowFamily.bug, Confidence.high
    for pattern in _CHORE_PATTERNS:
        if pattern in title_lower:
            return WorkflowFamily.chore, Confidence.high
    for pattern in _FEATURE_PATTERNS:
        if pattern in title_lower:
            return WorkflowFamily.feature, Confidence.high

    # Config/lint files → chore (before lane inference)
    if files:
        config_count = sum(
            1 for f in files
            if f.endswith((".toml", ".yaml", ".yml", ".ini", ".cfg", ".json"))
        )
        if config_count == len(files):
            return WorkflowFamily.chore, Confidence.medium

    # Test-heavy → bug workflow
    test_count = sum(1 for f in files if any(ind in f.lower() for ind in _TEST_PATH_INDICATORS))
    if test_count > 0 and len(files) <= 2:
        return WorkflowFamily.bug, Confidence.medium

    # Infer from scout lane
    if lane in ("direct_tiny_edit",):
        return WorkflowFamily.hotfix, Confidence.medium
    if lane == "builder" and len(files) > 3:
        return WorkflowFamily.feature, Confidence.medium

    return WorkflowFamily.unknown, Confidence.low


def _classify_risk(
    scout: AgentScoutDiscovery,
) -> RiskLevel:
    """Classify risk from scout output."""
    files = scout.files_to_touch
    tests = scout.tests
    risks = scout.risks

    # High risk: many files, no tests, or explicit high-risk flags
    if len(files) > 5:
        return RiskLevel.high
    if not tests and len(files) > 2:
        return RiskLevel.high
    high_risk_keywords = ("security", "migration", "breaking", "production", "deploy")
    for risk in risks:
        risk_lower = risk.lower()
        if any(kw in risk_lower for kw in high_risk_keywords):
            return RiskLevel.high

    # Low risk: 1-2 files with tests
    if len(files) <= 2 and tests:
        return RiskLevel.low

    return RiskLevel.medium


def _derive_approvals(risk: RiskLevel, family: WorkflowFamily) -> tuple[str, ...]:
    """Derive required approvals from risk and family."""
    approvals: list[str] = []
    if risk == RiskLevel.high:
        approvals.append("human_merge_approval")
    if family == WorkflowFamily.hotfix and risk != RiskLevel.low:
        approvals.append("human_review")
    if family == WorkflowFamily.feature and risk == RiskLevel.high:
        approvals.append("human_scope_approval")
    return tuple(approvals)


def _extract_areas(scout: AgentScoutDiscovery) -> tuple[str, ...]:
    """Extract affected areas (top-level directories) from target files."""
    areas: set[str] = set()
    for filepath in scout.files_to_touch:
        parts = Path(filepath).parts
        if len(parts) > 1:
            areas.add(parts[0])
        else:
            areas.add("root")
    return tuple(sorted(areas))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_task(
    scout: AgentScoutDiscovery,
    task_id: str,
    title: str = "",
) -> TaskAnalysis:
    """Analyze a scout discovery into a typed TaskAnalysis.

    Parameters
    ----------
    scout
        The output of ``discover_agent_scout_context``.
    task_id
        Stable task identifier.
    title
        Optional task title for family classification.
    """
    family, confidence = _classify_family(scout, title)
    risk = _classify_risk(scout)
    approvals = _derive_approvals(risk, family)
    areas = _extract_areas(scout)
    scope = f"{len(scout.files_to_touch)} file(s), {len(scout.tests)} test(s)"

    return TaskAnalysis(
        task_id=task_id,
        family=family,
        risk=risk,
        required_approvals=approvals,
        affected_areas=areas,
        recommended_scope=scope,
        confidence=confidence,
    )


__all__ = [
    "Confidence",
    "RiskLevel",
    "TaskAnalysis",
    "WorkflowFamily",
    "analyze_task",
]
