"""Tests for reusable orchestration patterns (M3-S3)."""

from __future__ import annotations

import pytest

from devflow.loop.patterns import (
    PATTERN_KINDS,
    PatternResult,
    PatternSpec,
    build_adversarial,
    build_competing,
    build_convergence,
    build_map_verify_reduce,
    build_pattern,
    build_scatter_gather,
)


# ---------------------------------------------------------------------------
# Scatter-gather
# ---------------------------------------------------------------------------

def test_scatter_gather_composes() -> None:
    """N readers → synthesizer, valid edges."""
    spec = PatternSpec(
        pattern_id="sg-1",
        kind="scatter_gather",
        node_prefix="sg",
        config={"investigators": 3},
    )
    result = build_scatter_gather(spec)

    # 3 investigators + synthesizer + blocked = 5 nodes
    assert len(result.nodes) == 5
    # entry = first investigator, exit = synthesizer
    assert result.entry_node_id == "sg-investigator-1"
    assert result.exit_node_id == "sg-synthesizer"


def test_scatter_gather_entry_exit() -> None:
    spec = PatternSpec(pattern_id="sg", kind="scatter_gather", node_prefix="sg")
    result = build_scatter_gather(spec)
    assert result.entry_node_id == "sg-investigator-1"
    assert result.exit_node_id == "sg-synthesizer"


def test_scatter_gather_edges_connect_to_synthesizer() -> None:
    spec = PatternSpec(
        pattern_id="sg", kind="scatter_gather", node_prefix="sg",
        config={"investigators": 2},
    )
    result = build_scatter_gather(spec)

    success_targets = {
        e.target for e in result.edges
        if e.outcome == "success" and e.source.startswith("sg-investigator")
    }
    assert success_targets == {"sg-synthesizer"}


# ---------------------------------------------------------------------------
# Competing
# ---------------------------------------------------------------------------

def test_competing_composes() -> None:
    """M planners → judge, valid edges."""
    spec = PatternSpec(
        pattern_id="comp", kind="competing", node_prefix="comp",
        config={"proposers": 3},
    )
    result = build_competing(spec)

    # 3 proposers + judge + blocked = 5 nodes
    assert len(result.nodes) == 5
    assert result.exit_node_id == "comp-judge"


def test_competing_judge_is_exit() -> None:
    spec = PatternSpec(pattern_id="comp", kind="competing", node_prefix="comp")
    result = build_competing(spec)
    assert result.exit_node_id == "comp-judge"


# ---------------------------------------------------------------------------
# Adversarial
# ---------------------------------------------------------------------------

def test_adversarial_composes() -> None:
    """Builder → reviewer, valid edges."""
    spec = PatternSpec(pattern_id="adv", kind="adversarial", node_prefix="adv")
    result = build_adversarial(spec)

    assert len(result.nodes) == 3  # builder + reviewer + blocked
    assert result.entry_node_id == "adv-builder"
    assert result.exit_node_id == "adv-reviewer"


def test_adversarial_reviewer_after_builder() -> None:
    """Reviewer depends on builder."""
    spec = PatternSpec(pattern_id="adv", kind="adversarial", node_prefix="adv")
    result = build_adversarial(spec)

    success_edges = {e.source: e.target for e in result.edges if e.outcome == "success"}
    assert success_edges.get("adv-builder") == "adv-reviewer"


# ---------------------------------------------------------------------------
# Map-verify-reduce
# ---------------------------------------------------------------------------

def test_map_verify_reduce_composes() -> None:
    """Fan-out → verify → reduce."""
    spec = PatternSpec(
        pattern_id="mvr", kind="map_verify_reduce", node_prefix="mvr",
        config={"items": 3},
    )
    result = build_map_verify_reduce(spec)

    # 3 workers + 3 verifiers + reducer + blocked = 8 nodes
    assert len(result.nodes) == 8
    assert result.exit_node_id == "mvr-reducer"


def test_map_verify_reduce_chain() -> None:
    """worker_i → verifier_i → reducer."""
    spec = PatternSpec(
        pattern_id="mvr", kind="map_verify_reduce", node_prefix="mvr",
        config={"items": 2},
    )
    result = build_map_verify_reduce(spec)

    success_edges = {e.source: e.target for e in result.edges if e.outcome == "success"}
    assert success_edges["mvr-worker-1"] == "mvr-verifier-1"
    assert success_edges["mvr-verifier-1"] == "mvr-reducer"


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------

def test_convergence_composes() -> None:
    """Check → repair → recheck."""
    spec = PatternSpec(
        pattern_id="conv", kind="convergence", node_prefix="conv",
        config={"max_rounds": 3, "stop_if_no_progress": 2},
    )
    result = build_convergence(spec)

    # checker + repair + passed + blocked = 4 nodes
    assert len(result.nodes) == 4
    assert result.entry_node_id == "conv-checker"
    assert result.exit_node_id == "conv-passed"


def test_convergence_loop_back_edge() -> None:
    """Repair → checker (loop back)."""
    spec = PatternSpec(pattern_id="conv", kind="convergence", node_prefix="conv")
    result = build_convergence(spec)

    success_edges = {e.source: e.target for e in result.edges if e.outcome == "success"}
    assert success_edges["conv-repair"] == "conv-checker"


def test_convergence_failure_to_repair() -> None:
    """Checker failure → repair."""
    spec = PatternSpec(pattern_id="conv", kind="convergence", node_prefix="conv")
    result = build_convergence(spec)

    failure_edges = {e.source: e.target for e in result.edges if e.outcome == "failure"}
    assert failure_edges["conv-checker"] == "conv-repair"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def test_build_pattern_dispatches() -> None:
    """build_pattern routes by kind."""
    for kind in PATTERN_KINDS:
        spec = PatternSpec(pattern_id=f"test-{kind}", kind=kind, node_prefix=f"p-{kind}")
        result = build_pattern(spec)
        assert isinstance(result, PatternResult)
        assert len(result.nodes) > 0


def test_unknown_pattern_raises() -> None:
    """Unknown kind → ValueError."""
    spec = PatternSpec(pattern_id="bad", kind="nonexistent", node_prefix="bad")
    with pytest.raises(ValueError, match="unknown pattern kind"):
        build_pattern(spec)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

def test_pattern_nodes_use_functional_roles() -> None:
    """No model names in generated nodes (naming rule)."""
    forbidden = {"qwen", "qwopus", "ornith", "glm", "gpt", "llama", "codex"}
    for kind in PATTERN_KINDS:
        spec = PatternSpec(pattern_id=f"test-{kind}", kind=kind, node_prefix=f"p-{kind}")
        result = build_pattern(spec)
        for node in result.nodes:
            node_lower = node.id.lower()
            for name in forbidden:
                assert name not in node_lower, f"Node {node.id} contains {name!r}"


def test_pattern_result_is_frozen() -> None:
    """PatternResult is immutable."""
    spec = PatternSpec(pattern_id="t", kind="adversarial", node_prefix="t")
    result = build_adversarial(spec)
    with pytest.raises(Exception):
        result.entry_node_id = "modified"  # type: ignore[misc]


def test_pattern_spec_is_frozen() -> None:
    """PatternSpec is immutable."""
    spec = PatternSpec(pattern_id="t", kind="adversarial", node_prefix="t")
    with pytest.raises(Exception):
        spec.kind = "competing"  # type: ignore[misc]


def test_pattern_spec_validation() -> None:
    """PatternSpec requires min_length fields."""
    with pytest.raises(Exception):
        PatternSpec(pattern_id="", kind="adversarial", node_prefix="t")
    with pytest.raises(Exception):
        PatternSpec(pattern_id="t", kind="", node_prefix="t")


def test_all_five_patterns_produce_nodes_and_edges() -> None:
    """Every pattern produces at least 2 nodes and 2 edges."""
    for kind in PATTERN_KINDS:
        spec = PatternSpec(pattern_id=f"test-{kind}", kind=kind, node_prefix=f"p-{kind}")
        result = build_pattern(spec)
        assert len(result.nodes) >= 2, f"{kind} produced too few nodes"
        assert len(result.edges) >= 2, f"{kind} produced too few edges"
