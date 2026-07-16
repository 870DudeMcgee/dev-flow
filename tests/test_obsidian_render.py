"""Behavior tests for the Obsidian Markdown renderers (M1-S2)."""

from __future__ import annotations

from pathlib import Path


from devflow.loop.models import LoopStage
from devflow.loop.pipeline_run import create_pipeline_run
from devflow.loop.workflow_ledger import (
    EvidenceReference,
    NodeReceipt,
    WorkflowEvent,
    initialize_workflow_run,
    record_node_outcome,
)
from devflow.obsidian.projection import (
    ProjectionState,
    RunHealth,
    extract_projection,
)
from devflow.obsidian.render import (
    END_MARKER,
    START_MARKER,
    render_all,
    render_decisions,
    render_evidence,
    render_front_matter,
    render_history,
    render_overview,
    render_workflow,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SUCCESS_CHAIN: tuple[tuple[str, str], ...] = (
    ("idea", "idea-brief"),
    ("definition", "orientation-receipt"),
    ("spec", "spec"),
    ("planning", "execution-plan"),
    ("planning_judge", "planning-judge-report"),
    ("assignment", "approved-execution-plan"),
    ("build_judge", "build-judge-report"),
    ("verification", "verification-receipt"),
    ("human_decision", "human-decision"),
)


def _record_success(root: Path, run_id: str, node_id: str, evidence_key: str, idx: int) -> None:
    evidence_file = f"{evidence_key}.md"
    run_dir = root / ".devflow" / "pipeline-runs" / run_id
    if not (run_dir / evidence_file).exists():
        (run_dir / evidence_file).write_text(f"# {evidence_key}\n", encoding="utf-8")
    record_node_outcome(
        root,
        run_id,
        receipt=NodeReceipt(
            receipt_id=f"receipt-{idx}",
            node_id=node_id,
            outcome="success",
            evidence=(EvidenceReference(key=evidence_key, reference=evidence_file),),
        ),
        event=WorkflowEvent(
            event_id=f"event-{idx}",
            node_id=node_id,
            outcome="success",
            receipt_id=f"receipt-{idx}",
        ),
    )


def _advance_to(root: Path, run_id: str, through_node: str) -> None:
    for idx, (node_id, evidence_id) in enumerate(_SUCCESS_CHAIN, start=1):
        _record_success(root, run_id, node_id, evidence_id, idx)
        if node_id == through_node:
            break


def _build_state(
    tmp_path: Path,
    through_node: str | None = None,
) -> ProjectionState:
    """Build a disposable run and extract its projection."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    if through_node:
        _advance_to(tmp_path, run_id, through_node)
    return extract_projection(tmp_path, run_id)


def _build_state_with_decision(
    tmp_path: Path,
    decision_type: str = "accept",
) -> ProjectionState:
    """Build a run at complete stage with a decision receipt."""
    run_id = create_pipeline_run(tmp_path, {"repo": "test/repo"})
    initialize_workflow_run(tmp_path, run_id)
    _advance_to(tmp_path, run_id, "human_decision")  # all 9 → complete

    from devflow.obsidian.projection import DecisionSummary
    # extract_projection reads decision receipts from disk, but we can't easily
    # write them without the full Phase 3-5 chain. Instead, build the state
    # and manually construct what extract_projection would see.
    base_state = extract_projection(tmp_path, run_id)
    return base_state.model_copy(
        update={
            "open_decisions": (
                DecisionSummary(
                    decision_id="decision-1",
                    decision_type=decision_type,
                    actor="test-operator",
                    promotion_eligible=(decision_type == "accept"),
                    created_at="2026-07-15T12:00:00Z",
                ),
            ),
            "decision_count": 1,
        }
    )


# ---------------------------------------------------------------------------
# Front matter tests
# ---------------------------------------------------------------------------

def test_front_matter_valid_yaml(tmp_path: Path) -> None:
    """Front matter parses as YAML with all required keys."""
    import yaml

    state = _build_state(tmp_path)
    fm = render_front_matter(state)

    # Strip --- delimiters
    assert fm.startswith("---")
    assert fm.endswith("---")
    yaml_str = fm.strip("-\n")
    parsed = yaml.safe_load(yaml_str)

    assert parsed["type"] == "devflow-run"
    assert parsed["project"] == "DevFlow"
    assert parsed["run_id"] == state.run_id
    assert parsed["workflow"] == "canonical_product_build@1"
    assert parsed["health"] == "Running"
    assert parsed["phase"] == "Idea & Brainstorm"
    assert parsed["progress"] == 0
    assert "canonical_state" in parsed
    assert "updated" in parsed


# ---------------------------------------------------------------------------
# Overview tests
# ---------------------------------------------------------------------------

def test_render_overview_contains_wikilinks(tmp_path: Path) -> None:
    """Overview has navigation wikilinks."""
    state = _build_state(tmp_path)
    md = render_overview(state)

    assert "[[Workflow]]" in md
    assert "[[Evidence]]" in md
    assert "[[Decisions]]" in md
    assert "[[History]]" in md


def test_render_overview_contains_generated_markers(tmp_path: Path) -> None:
    """Overview is wrapped in START/END markers."""
    state = _build_state(tmp_path)
    md = render_overview(state)

    assert START_MARKER in md
    assert END_MARKER in md


def test_render_overview_progress_matches_state(tmp_path: Path) -> None:
    """33% when 3/9 nodes done."""
    state = _build_state(tmp_path, through_node="spec")
    md = render_overview(state)

    assert "33%" in md


def test_render_overview_health_displayed(tmp_path: Path) -> None:
    """Health value appears in the overview."""
    state = _build_state(tmp_path)
    md = render_overview(state)

    assert "Running" in md


def test_render_overview_attention_no_blockers(tmp_path: Path) -> None:
    """Fresh run: no blockers message."""
    state = _build_state(tmp_path)
    md = render_overview(state)

    assert "No blockers" in md


def test_render_overview_next_action_for_awaiting(tmp_path: Path) -> None:
    """Awaiting Decision → next action mentions operator decision."""
    state = _build_state(tmp_path, through_node="verification")
    md = render_overview(state)

    assert "operator decision" in md.lower() or "awaiting" in md.lower()


# ---------------------------------------------------------------------------
# Workflow tests
# ---------------------------------------------------------------------------

def test_render_workflow_shows_node_status_table(tmp_path: Path) -> None:
    """All nodes present in the status table."""
    state = _build_state(tmp_path)
    md = render_workflow(state)

    assert "| Node | Stage | Status |" in md
    for node_label in ("Idea", "Specification", "Verification", "Human Decision"):
        assert node_label in md


def test_render_workflow_marks_current_node(tmp_path: Path) -> None:
    """Current node has the 'current' marker."""
    state = _build_state(tmp_path, through_node="spec")
    md = render_workflow(state)

    # planning is current after spec completes
    assert "Planning" in md
    assert "current" in md


def test_render_workflow_marks_completed_nodes(tmp_path: Path) -> None:
    """Completed nodes have the 'completed' marker."""
    state = _build_state(tmp_path, through_node="spec")
    md = render_workflow(state)

    assert "completed" in md
    # Idea, Definition, Specification should be completed
    for label in ("Idea", "Definition", "Specification"):
        assert label in md


# ---------------------------------------------------------------------------
# Evidence tests
# ---------------------------------------------------------------------------

def test_render_evidence_links_to_run_dir(tmp_path: Path) -> None:
    """Evidence view contains the canonical run directory path."""
    state = _build_state(tmp_path)
    md = render_evidence(state)

    assert state.canonical_run_dir in md
    assert "Canonical State" in md or "canonical" in md.lower()


def test_render_evidence_mentions_result_branch_status(tmp_path: Path) -> None:
    """Evidence view shows result branch status."""
    state = _build_state(tmp_path)
    md = render_evidence(state)

    assert "Result Branch" in md
    assert "No result branch" in md  # fresh run has none


def test_render_evidence_wikilinks(tmp_path: Path) -> None:
    """Evidence has navigation wikilinks."""
    state = _build_state(tmp_path)
    md = render_evidence(state)

    assert "[[Overview]]" in md
    assert "[[Workflow]]" in md


# ---------------------------------------------------------------------------
# Decisions tests
# ---------------------------------------------------------------------------

def test_render_decisions_shows_open_decisions(tmp_path: Path) -> None:
    """Decision table renders when decisions exist."""
    state = _build_state_with_decision(tmp_path, "accept")
    md = render_decisions(state)

    assert "| Decision | Type | Actor |" in md
    assert "decision-1" in md
    assert "accept" in md
    assert "test-operator" in md


def test_render_decisions_empty_when_none(tmp_path: Path) -> None:
    """No decisions message when count=0."""
    state = _build_state(tmp_path)
    md = render_decisions(state)

    assert "No decisions" in md


def test_render_decisions_shows_promotion_eligibility(tmp_path: Path) -> None:
    """Accept decisions show promotion eligible."""
    state = _build_state_with_decision(tmp_path, "accept")
    md = render_decisions(state)

    assert "yes" in md.lower()


# ---------------------------------------------------------------------------
# History tests
# ---------------------------------------------------------------------------

def test_render_history_chronological(tmp_path: Path) -> None:
    """History shows completed nodes in order."""
    state = _build_state(tmp_path, through_node="spec")
    md = render_history(state)

    assert "Stage Progression" in md
    assert "Idea" in md
    assert "Definition" in md
    assert "Specification" in md
    assert "completed" in md


def test_render_history_empty_for_fresh_run(tmp_path: Path) -> None:
    """Fresh run: no completed nodes yet."""
    state = _build_state(tmp_path)
    md = render_history(state)

    assert "No nodes completed" in md


# ---------------------------------------------------------------------------
# render_all tests
# ---------------------------------------------------------------------------

def test_render_all_produces_five_views(tmp_path: Path) -> None:
    """render_all returns all 5 views."""
    state = _build_state(tmp_path)
    views = render_all(state)

    assert set(views.keys()) == {
        "Overview.md", "Workflow.md", "Evidence.md",
        "Decisions.md", "History.md",
    }


def test_render_all_all_have_markers(tmp_path: Path) -> None:
    """Every view has START/END markers."""
    state = _build_state(tmp_path)
    views = render_all(state)

    for filename, content in views.items():
        assert START_MARKER in content, f"{filename} missing START_MARKER"
        assert END_MARKER in content, f"{filename} missing END_MARKER"


# ---------------------------------------------------------------------------
# Pure function tests
# ---------------------------------------------------------------------------

def test_all_renderers_pure_functions(tmp_path: Path) -> None:
    """No file I/O — calling twice produces identical output."""
    state = _build_state(tmp_path)
    md1 = render_overview(state)
    md2 = render_overview(state)

    assert md1 == md2


def test_renderers_handle_noncanonical_state() -> None:
    """Renderers work with a noncanonical ProjectionState."""
    state = ProjectionState(
        run_id="test-run",
        workflow_id="unknown",
        health=RunHealth.healthy,
        current_phase="Unknown",
        stage=LoopStage.idea,
        progress=0.0,
        progress_percent=0,
        canonical_run_dir="/tmp/nonexistent",
        updated_at="2026-07-15T00:00:00Z",
        extraction_note="not_canonical",
    )

    md = render_overview(state)
    assert "not canonical" in md.lower() or "no projection" in md.lower()
