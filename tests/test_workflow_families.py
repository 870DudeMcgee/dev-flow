"""Tests for parameterized workflow family templates (M5-S1)."""

from __future__ import annotations

import pytest

from devflow.loop.workflow_definition import NodeKind, canonical_product_build_v1
from devflow.loop.workflow_library import (
    WorkflowClass,
    all_templates_validate,
    bug_template,
    chore_template,
    feature_template,
    get_template,
    hotfix_template,
    list_templates,
    select_template,
)
from devflow.loop.workflow_schema import (
    WorkflowStrategy,
    validate_workflow,
)


# ---------------------------------------------------------------------------
# All templates validate
# ---------------------------------------------------------------------------

def test_four_family_templates() -> None:
    """hotfix/feature/bug/chore all exist and validate."""
    for tid in ("hotfix@1", "feature@1", "bug@1", "chore@1"):
        template = get_template(tid)
        assert template is not None, f"{tid} missing"
        validate_workflow(template)


def test_all_templates_validate() -> None:
    """all_templates_validate() returns True."""
    assert all_templates_validate() is True


def test_list_templates_returns_all() -> None:
    """4 family templates registered."""
    templates = list_templates()
    assert set(templates) == {"hotfix@1", "feature@1", "bug@1", "chore@1"}


# ---------------------------------------------------------------------------
# Hotfix template
# ---------------------------------------------------------------------------

def test_hotfix_template_shape() -> None:
    """grounding→proposal→approval→patch→verify→review."""
    t = hotfix_template()
    node_ids = {n.id for n in t.nodes}
    assert "hotfix-grounding" in node_ids
    assert "hotfix-proposal" in node_ids
    assert "hotfix-approval" in node_ids
    assert "hotfix-patch" in node_ids
    assert "hotfix-verify" in node_ids
    assert "hotfix-review" in node_ids
    assert "hotfix-decision" in node_ids


def test_hotfix_has_approval_gate() -> None:
    """Hotfix includes a human_gate for approval."""
    t = hotfix_template()
    gate_nodes = [n for n in t.nodes if n.kind == NodeKind.human_gate]
    assert len(gate_nodes) >= 1


def test_hotfix_budget_fast() -> None:
    """Hotfix budget is fast (60 min, 2 repair rounds)."""
    t = hotfix_template()
    assert t.budget.max_runtime_minutes == 60
    assert t.budget.max_repair_rounds == 2


# ---------------------------------------------------------------------------
# Feature template
# ---------------------------------------------------------------------------

def test_feature_template_shape() -> None:
    """grounding→spec→judge→planning→build→verify→integration→review."""
    t = feature_template()
    node_ids = {n.id for n in t.nodes}
    assert "feature-grounding" in node_ids
    assert "feature-spec" in node_ids
    assert "feature-spec-judge" in node_ids
    assert "feature-planning" in node_ids
    assert "feature-build" in node_ids
    assert "feature-verify" in node_ids
    assert "feature-integration" in node_ids
    assert "feature-review" in node_ids


def test_feature_strategy_dag() -> None:
    """Feature uses DAG strategy."""
    t = feature_template()
    assert t.strategy == WorkflowStrategy.dag


def test_feature_budget_thorough() -> None:
    """Feature budget is thorough (180 min, 4 repair rounds)."""
    t = feature_template()
    assert t.budget.max_runtime_minutes == 180
    assert t.budget.max_repair_rounds == 4


# ---------------------------------------------------------------------------
# Bug template
# ---------------------------------------------------------------------------

def test_bug_template_shape() -> None:
    """reproduction→diagnosis→root-cause→repair→regression→adversarial."""
    t = bug_template()
    node_ids = {n.id for n in t.nodes}
    assert "bug-repro" in node_ids
    assert "bug-diagnosis" in node_ids
    assert "bug-root-cause" in node_ids
    assert "bug-repair" in node_ids
    assert "bug-regression" in node_ids
    assert "bug-adversarial" in node_ids


def test_bug_budget_evidence_driven() -> None:
    """Bug budget is evidence-driven (120 min, 3 repair rounds)."""
    t = bug_template()
    assert t.budget.max_runtime_minutes == 120
    assert t.budget.max_repair_rounds == 3


def test_bug_has_reproduction_first() -> None:
    """Bug starts with reproduction (code node)."""
    t = bug_template()
    # Find the entry node — it should have no incoming success edges
    targets = {e.target for e in t.edges if e.outcome == "success"}
    entry_nodes = [n for n in t.nodes if n.id not in targets and n.id != "bug-blocked"]
    assert any("repro" in n.id for n in entry_nodes)


# ---------------------------------------------------------------------------
# Chore template
# ---------------------------------------------------------------------------

def test_chore_template_shape() -> None:
    """scope→change→lint→ci→review."""
    t = chore_template()
    node_ids = {n.id for n in t.nodes}
    assert "chore-scope" in node_ids
    assert "chore-change" in node_ids
    assert "chore-lint" in node_ids
    assert "chore-ci" in node_ids
    assert "chore-review" in node_ids


def test_chore_budget_minimal() -> None:
    """Chore budget is minimal (30 min, 1 repair round)."""
    t = chore_template()
    assert t.budget.max_runtime_minutes == 30
    assert t.budget.max_repair_rounds == 1


# ---------------------------------------------------------------------------
# Canonical product build still fixed
# ---------------------------------------------------------------------------

def test_canonical_product_build_still_fixed() -> None:
    """v1 canonical_product_build@1 is unchanged and valid."""
    defn = canonical_product_build_v1()
    assert defn.workflow_id == "canonical_product_build@1"
    validate_workflow(defn)


# ---------------------------------------------------------------------------
# select_template
# ---------------------------------------------------------------------------

def test_select_template_from_analysis() -> None:
    """WorkflowFamily value → correct template_id."""
    assert select_template("hotfix") == "hotfix@1"
    assert select_template("feature") == "feature@1"
    assert select_template("bug") == "bug@1"
    assert select_template("chore") == "chore@1"


def test_unknown_family_falls_back() -> None:
    """Unknown → canonical_product_build@1."""
    assert select_template("unknown") == "canonical_product_build@1"
    assert select_template("nonexistent") == "canonical_product_build@1"


# ---------------------------------------------------------------------------
# Budgets differ
# ---------------------------------------------------------------------------

def test_template_budgets_differ() -> None:
    """Each family has a different runtime budget."""
    budgets = {
        "hotfix": hotfix_template().budget.max_runtime_minutes,
        "feature": feature_template().budget.max_runtime_minutes,
        "bug": bug_template().budget.max_runtime_minutes,
        "chore": chore_template().budget.max_runtime_minutes,
    }
    assert budgets["hotfix"] < budgets["feature"]
    assert budgets["chore"] < budgets["bug"]
    assert budgets["bug"] < budgets["feature"]


# ---------------------------------------------------------------------------
# No auto-promote
# ---------------------------------------------------------------------------

def test_no_auto_promote_in_any_template() -> None:
    """All templates have auto_promote=False."""
    for tid in list_templates():
        template = get_template(tid)
        assert template is not None
        assert template.promotion.auto_promote is False


# ---------------------------------------------------------------------------
# Naming rule
# ---------------------------------------------------------------------------

def test_templates_use_functional_roles() -> None:
    """No model names in any template node IDs."""
    forbidden = {"qwen", "qwopus", "ornith", "glm", "gpt", "llama", "codex"}
    for tid in list_templates():
        template = get_template(tid)
        assert template is not None
        for node in template.nodes:
            node_lower = node.id.lower()
            for name in forbidden:
                assert name not in node_lower, f"Node {node.id} in {tid} contains {name!r}"


# ---------------------------------------------------------------------------
# Schema version + class
# ---------------------------------------------------------------------------

def test_all_templates_are_v2() -> None:
    """All family templates are version v2."""
    for tid in list_templates():
        template = get_template(tid)
        assert template is not None
        assert template.version == "v2"


def test_workflow_class_enum() -> None:
    """WorkflowClass has fixed/parameterized/generated."""
    assert WorkflowClass.fixed.value == "fixed"
    assert WorkflowClass.parameterized.value == "parameterized"
    assert WorkflowClass.generated.value == "generated"


# ---------------------------------------------------------------------------
# get_template
# ---------------------------------------------------------------------------

def test_get_template_not_found() -> None:
    """Unknown ID → None."""
    assert get_template("nonexistent@1") is None


def test_get_template_returns_frozen() -> None:
    """Template is a frozen model."""
    t = hotfix_template()
    with pytest.raises(Exception):
        t.workflow_id = "modified"  # type: ignore[misc]
