"""Parameterized workflow family templates (M5-S1, blueprint §8.1–8.4).

Four family templates — hotfix, feature, bug, chore — plus the Fixed
``canonical_product_build@1`` member. Each template is a
:class:`~devflow.loop.workflow_schema.WorkflowSchemaV2` definition with the
blueprint's phase shape, budget, and strategy.

Family selection uses :func:`~devflow.control_plane.task_analyzer.analyze_task`
output. All templates validate against the M2 schema; all have
``auto_promote=False`` (no autonomous promotion).

All types use functional role names only — no model identity (naming rule).
"""

from __future__ import annotations

from enum import Enum

from devflow.loop.models import LoopStage
from devflow.loop.workflow_definition import (
    NodeKind,
    WorkflowEdge,
    WorkflowNode,
)
from devflow.loop.workflow_schema import (
    BudgetPolicy,
    PromotionPolicy,
    WorkflowSchemaV2,
    WorkflowStrategy,
    validate_workflow,
)


# ---------------------------------------------------------------------------
# Workflow class
# ---------------------------------------------------------------------------

class WorkflowClass(str, Enum):
    """Blueprint §6.4 workflow classes."""

    fixed = "fixed"
    parameterized = "parameterized"
    generated = "generated"  # M6 (not yet built)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node(
    node_id: str,
    kind: NodeKind = NodeKind.agent,
    stage: LoopStage = LoopStage.spec,
    evidence: tuple[str, ...] = ("output",),
) -> WorkflowNode:
    return WorkflowNode(
        id=node_id, kind=kind, stage=stage, required_evidence=evidence,
    )


def _success(source: str, target: str, edge_id: str | None = None) -> WorkflowEdge:
    return WorkflowEdge(
        id=edge_id or f"{source}:success",
        source=source,
        target=target,
        outcome="success",
    )


def _failure(source: str, target: str = "blocked") -> WorkflowEdge:
    return WorkflowEdge(id=f"{source}:failure", source=source, target=target, outcome="failure")


def _terminal_nodes(prefix: str) -> tuple[WorkflowNode, ...]:
    return (
        WorkflowNode(
            id=f"{prefix}-complete", kind=NodeKind.code,
            stage=LoopStage.complete, required_evidence=(),
        ),
        WorkflowNode(
            id=f"{prefix}-blocked", kind=NodeKind.human,
            stage=LoopStage.blocked, required_evidence=(),
        ),
    )


def _base_edges(prefix: str, node_ids: list[str]) -> list[WorkflowEdge]:
    """Build success-chain edges + failure→blocked for a linear sequence.

    The last node in the chain gets success→complete and failure→blocked.
    """
    edges: list[WorkflowEdge] = []
    for i in range(len(node_ids) - 1):
        edges.append(_success(node_ids[i], node_ids[i + 1]))
        edges.append(_failure(node_ids[i], f"{prefix}-blocked"))
    # Last node → complete (success) + blocked (failure)
    if node_ids:
        last = node_ids[-1]
        edges.append(_success(last, f"{prefix}-complete"))
        edges.append(_failure(last, f"{prefix}-blocked"))
    return edges


# ---------------------------------------------------------------------------
# Hotfix template (§8.1)
# ---------------------------------------------------------------------------

def hotfix_template() -> WorkflowSchemaV2:
    """Parallel Grounding → Proposal → Approval Gate → Patch → Verify → Review.

    Optimized for speed, containment, explicit risk control.
    """
    p = "hotfix"
    nodes = (
        _node(f"{p}-grounding", NodeKind.agent, LoopStage.definition, ("grounding-packet",)),
        _node(f"{p}-proposal", NodeKind.agent, LoopStage.spec, ("hotfix-proposal",)),
        _node(f"{p}-approval", NodeKind.human_gate, LoopStage.planning_judge, ("approval",)),
        _node(f"{p}-patch", NodeKind.agent, LoopStage.assignment, ("patch",)),
        _node(f"{p}-verify", NodeKind.code, LoopStage.verification, ("verification-receipt",)),
        _node(f"{p}-review", NodeKind.agent, LoopStage.build_judge, ("review-report",)),
        _node(f"{p}-decision", NodeKind.human_gate, LoopStage.human_decision, ("decision",)),
        *_terminal_nodes(p),
    )
    chain = [n.id for n in nodes if not n.id.endswith(("-complete", "-blocked"))]
    edges = tuple(_base_edges(p, chain))

    return WorkflowSchemaV2(
        version="v2",
        workflow_id=f"{p}@1",
        strategy=WorkflowStrategy.sequence,
        budget=BudgetPolicy(
            max_runtime_minutes=60,
            max_agent_runs=15,
            max_repair_rounds=2,
            heavy_model_slots=1,
        ),
        promotion=PromotionPolicy(human_required=True, auto_promote=False),
        nodes=nodes,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Feature template (§8.2)
# ---------------------------------------------------------------------------

def feature_template() -> WorkflowSchemaV2:
    """Grounding → Spec ↔ Judge → Planning → {Build ∥ Build-Tests} → Integration → Verify → Review → Decision.

    Optimized for spec quality, decomposable work, integration confidence.

    Genuine DAG (not a mislabeled linear chain): after ``feature-planning``
    the work fans out to two independent build branches — ``feature-build``
    (implementation) and ``feature-build-tests`` (test harness) — each with
    its own success and failure routes. Both successful branches join at the
    non-terminal ``feature-integration`` reduce node, which then continues to
    verify/review/decision/complete. Every non-terminal node routes failure
    to ``feature-blocked``.
    """
    p = "feature"
    nodes = (
        _node(f"{p}-grounding", NodeKind.agent, LoopStage.definition, ("grounding-packet",)),
        _node(f"{p}-spec", NodeKind.agent, LoopStage.spec, ("spec",)),
        _node(f"{p}-spec-judge", NodeKind.agent, LoopStage.planning_judge, ("spec-judge-report",)),
        _node(f"{p}-planning", NodeKind.agent, LoopStage.planning, ("execution-plan",)),
        _node(f"{p}-build", NodeKind.agent, LoopStage.assignment, ("build-result",)),
        _node(f"{p}-build-tests", NodeKind.code, LoopStage.verification, ("build-tests-result",)),
        _node(f"{p}-integration", NodeKind.agent, LoopStage.build_judge, ("integration-result",)),
        _node(f"{p}-verify", NodeKind.code, LoopStage.verification, ("verification-receipt",)),
        _node(f"{p}-review", NodeKind.agent, LoopStage.verification, ("review-report",)),
        _node(f"{p}-decision", NodeKind.human_gate, LoopStage.human_decision, ("decision",)),
        *_terminal_nodes(p),
    )
    # Linear spine up to the fan-out point.
    edges = (
        _success(f"{p}-grounding", f"{p}-spec"),
        _failure(f"{p}-grounding", f"{p}-blocked"),
        _success(f"{p}-spec", f"{p}-spec-judge"),
        _failure(f"{p}-spec", f"{p}-blocked"),
        _success(f"{p}-spec-judge", f"{p}-planning"),
        _failure(f"{p}-spec-judge", f"{p}-blocked"),
        # Fan-out after planning to two independent build branches.
        _success(f"{p}-planning", f"{p}-build", edge_id=f"{p}-planning:success:build"),
        _success(f"{p}-planning", f"{p}-build-tests", edge_id=f"{p}-planning:success:tests"),
        _failure(f"{p}-planning", f"{p}-blocked"),
        # Branch 1 — implementation build.
        _success(f"{p}-build", f"{p}-integration"),
        _failure(f"{p}-build", f"{p}-blocked"),
        # Branch 2 — test harness build.
        _success(f"{p}-build-tests", f"{p}-integration"),
        _failure(f"{p}-build-tests", f"{p}-blocked"),
        # Join at the non-terminal integration reduce node, then verify/review/decision.
        _success(f"{p}-integration", f"{p}-verify"),
        _failure(f"{p}-integration", f"{p}-blocked"),
        _success(f"{p}-verify", f"{p}-review"),
        _failure(f"{p}-verify", f"{p}-blocked"),
        _success(f"{p}-review", f"{p}-decision"),
        _failure(f"{p}-review", f"{p}-blocked"),
        _success(f"{p}-decision", f"{p}-complete"),
        _failure(f"{p}-decision", f"{p}-blocked"),
    )

    return WorkflowSchemaV2(
        version="v2",
        workflow_id=f"{p}@1",
        strategy=WorkflowStrategy.dag,
        budget=BudgetPolicy(
            max_runtime_minutes=180,
            max_agent_runs=30,
            max_repair_rounds=4,
            heavy_model_slots=1,
        ),
        promotion=PromotionPolicy(human_required=True, auto_promote=False),
        nodes=nodes,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Bug template (§8.3)
# ---------------------------------------------------------------------------

def bug_template() -> WorkflowSchemaV2:
    """Reproduction → Diagnosis → Root-Cause Judge → Repair → Regression → Adversarial Review.

    Optimized for reproduction and causal evidence.
    """
    p = "bug"
    nodes = (
        _node(f"{p}-repro", NodeKind.code, LoopStage.verification, ("reproduction",)),
        _node(f"{p}-diagnosis", NodeKind.agent, LoopStage.spec, ("diagnosis-report",)),
        _node(f"{p}-root-cause", NodeKind.agent, LoopStage.planning_judge, ("root-cause-judgment",)),
        _node(f"{p}-repair", NodeKind.agent, LoopStage.assignment, ("repair-patch",)),
        _node(f"{p}-regression", NodeKind.code, LoopStage.verification, ("regression-receipt",)),
        _node(f"{p}-adversarial", NodeKind.agent, LoopStage.build_judge, ("adversarial-review",)),
        _node(f"{p}-decision", NodeKind.human_gate, LoopStage.human_decision, ("decision",)),
        *_terminal_nodes(p),
    )
    chain = [n.id for n in nodes if not n.id.endswith(("-complete", "-blocked"))]
    edges = tuple(_base_edges(p, chain))

    return WorkflowSchemaV2(
        version="v2",
        workflow_id=f"{p}@1",
        strategy=WorkflowStrategy.sequence,
        budget=BudgetPolicy(
            max_runtime_minutes=120,
            max_agent_runs=20,
            max_repair_rounds=3,
            heavy_model_slots=1,
        ),
        promotion=PromotionPolicy(human_required=True, auto_promote=False),
        nodes=nodes,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Chore template (§8.4)
# ---------------------------------------------------------------------------

def chore_template() -> WorkflowSchemaV2:
    """Scope Check → Bounded Change → Lint/Format → CI/CD → Review.

    Optimized for low overhead.
    """
    p = "chore"
    nodes = (
        _node(f"{p}-scope", NodeKind.agent, LoopStage.definition, ("scope-check",)),
        _node(f"{p}-change", NodeKind.agent, LoopStage.assignment, ("change-result",)),
        _node(f"{p}-lint", NodeKind.code, LoopStage.verification, ("lint-receipt",)),
        _node(f"{p}-ci", NodeKind.code, LoopStage.verification, ("ci-receipt",)),
        _node(f"{p}-review", NodeKind.agent, LoopStage.build_judge, ("review-report",)),
        _node(f"{p}-decision", NodeKind.human_gate, LoopStage.human_decision, ("decision",)),
        *_terminal_nodes(p),
    )
    chain = [n.id for n in nodes if not n.id.endswith(("-complete", "-blocked"))]
    edges = tuple(_base_edges(p, chain))

    return WorkflowSchemaV2(
        version="v2",
        workflow_id=f"{p}@1",
        strategy=WorkflowStrategy.sequence,
        budget=BudgetPolicy(
            max_runtime_minutes=30,
            max_agent_runs=10,
            max_repair_rounds=1,
            heavy_model_slots=1,
        ),
        promotion=PromotionPolicy(human_required=True, auto_promote=False),
        nodes=nodes,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Workflow library registry
# ---------------------------------------------------------------------------

WORKFLOW_LIBRARY: dict[str, WorkflowSchemaV2] = {}


def _register_library() -> None:
    """Populate the library with all templates."""
    global WORKFLOW_LIBRARY
    templates = {
        "hotfix@1": hotfix_template(),
        "feature@1": feature_template(),
        "bug@1": bug_template(),
        "chore@1": chore_template(),
    }
    WORKFLOW_LIBRARY = templates


_register_library()


def get_template(workflow_id: str) -> WorkflowSchemaV2 | None:
    """Return a template by workflow_id, or None."""
    return WORKFLOW_LIBRARY.get(workflow_id)


def list_templates() -> tuple[str, ...]:
    """Return all registered template IDs."""
    return tuple(sorted(WORKFLOW_LIBRARY.keys()))


def select_template(family: str) -> str:
    """Map a WorkflowFamily value to a template workflow_id.

    Falls back to ``canonical_product_build@1`` for unknown families.
    """
    mapping = {
        "hotfix": "hotfix@1",
        "feature": "feature@1",
        "bug": "bug@1",
        "chore": "chore@1",
    }
    return mapping.get(family, "canonical_product_build@1")


def all_templates_validate() -> bool:
    """Verify every template in the library passes validation."""
    for workflow_id, template in WORKFLOW_LIBRARY.items():
        try:
            validate_workflow(template)
        except Exception:
            return False
    return True


__all__ = [
    "WORKFLOW_LIBRARY",
    "WorkflowClass",
    "all_templates_validate",
    "bug_template",
    "chore_template",
    "feature_template",
    "get_template",
    "hotfix_template",
    "list_templates",
    "select_template",
]
