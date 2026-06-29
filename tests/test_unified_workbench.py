from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from devflow.control_room.browser_action_policy import ACTION_APPROVAL_PHRASE
from devflow.control_room.builder_judge_loop import BuilderJudgeConfig, BuilderJudgeRun
from devflow.control_room.unified_workbench import (
    GRAPHIFY_SOURCE,
    PONYTAIL_SOURCE,
    WorkbenchError,
    build_gate_status,
    build_workbench_state,
    prepare_implementation_package,
    run_workbench_implementation,
    setup_gate,
)
from tests.helpers import setup_temp_git_repo


def _head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _write_graphify_evidence(root: Path) -> None:
    out = root / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    out.joinpath("GRAPH_REPORT.md").write_text(
        "\n".join(
            [
                "# Graph Report - Test (2026-06-29)",
                "",
                f"Built from commit: `{_head(root)}`",
                "",
                "## Graph Metrics",
                "- Nodes: 12",
                "- Edges: 24",
                "",
                "## God Nodes",
                "1. `src/devflow/control_room/operating_layer.py` - 24 edges",
                "",
                "## Suggested Questions",
                "- **Should the workbench reuse the existing bridge?**",
                "_Reuse reduces operator load._",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    out.joinpath("graph.json").write_text('{"nodes":[],"edges":[]}\n', encoding="utf-8")
    out.joinpath("Local-AI-Dev-Team-callflow.html").write_text("<html>callflow</html>\n", encoding="utf-8")
    out.joinpath("dev-flow-callflow.html").write_text("<html>callflow</html>\n", encoding="utf-8")


def _approve_ponytail(root: Path) -> None:
    setup_gate(
        root,
        {
            "gate": "ponytail",
            "human_approved": True,
            "approval_phrase": ACTION_APPROVAL_PHRASE,
            "approved_source": PONYTAIL_SOURCE,
            "reviewed_lifecycle_hooks": True,
        },
    )


def _write_brainstorm(root: Path, session_id: str = "workbench-session") -> Path:
    session_dir = root / ".devflow" / "brainstorms" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    session_dir.joinpath("transcript.jsonl").write_text(
        json.dumps(
            {
                "created_at": "2026-06-29T12:00:00Z",
                "role": "user",
                "kind": "message",
                "content": "Make the unified chat workbench real.",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    session_dir.joinpath("spec.md").write_text(
        "# Spec\n\n- Show Idea -> Brainstorm -> Spec -> Plan -> Implement.\n- Block Implement when gates are stale.\n",
        encoding="utf-8",
    )
    session_dir.joinpath("plan.md").write_text(
        "# Plan\n\n- Reuse the existing brainstorm bridge.\n- Send Implement through builder-judge first.\n",
        encoding="utf-8",
    )
    return session_dir


def _passing_run(config: BuilderJudgeConfig) -> BuilderJudgeRun:
    now = datetime.now(timezone.utc).isoformat()
    return BuilderJudgeRun(
        loop_id="workbench-implement-test",
        run_id="workbench-implement-test-run",
        status="passed",
        config=config,
        final_draft="# Implementation\n\nAccepted builder-judge package.\n",
        final_score=92,
        started_at=now,
        finished_at=now,
        evidence_path=".devflow/builder-judge-loops/workbench-implement-test/run.json",
        stop_reason="passed_threshold",
        next_safe_action="Create a Dev-Flow task from implementation.md.",
    )


def _escalated_run(config: BuilderJudgeConfig) -> BuilderJudgeRun:
    now = datetime.now(timezone.utc).isoformat()
    return BuilderJudgeRun(
        loop_id="workbench-implement-escalated",
        run_id="workbench-implement-escalated-run",
        status="escalated",
        config=config,
        final_draft="# Implementation\n\nNot good enough.\n",
        final_score=55,
        started_at=now,
        finished_at=now,
        evidence_path=".devflow/builder-judge-loops/workbench-implement-escalated/run.json",
        stop_reason="max_rounds",
        next_safe_action="Send to Refactor Loop.",
    )


def test_workbench_gates_block_missing_graphify_and_ponytail(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    gates = build_gate_status(tmp_path)
    by_id = {item.id: item for item in gates.items}

    assert gates.ready is False
    assert by_id["graphify"].ready is False
    assert by_id["graphify"].source == GRAPHIFY_SOURCE
    assert by_id["graphify"].setup_action is not None
    assert by_id["ponytail"].ready is False
    assert by_id["ponytail"].source == PONYTAIL_SOURCE
    assert "Repair gate evidence first" in gates.next_action

    state = build_workbench_state(tmp_path)
    assert state.stage == "idea"
    assert state.gate_status.ready is False


def test_ponytail_setup_requires_explicit_approved_source(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)

    with pytest.raises(WorkbenchError, match="explicit human approval"):
        setup_gate(tmp_path, {"gate": "ponytail"})

    result = setup_gate(
        tmp_path,
        {
            "gate": "ponytail",
            "human_approved": True,
            "approval_phrase": ACTION_APPROVAL_PHRASE,
            "approved_source": PONYTAIL_SOURCE,
            "reviewed_lifecycle_hooks": True,
        },
    )

    marker = tmp_path / ".devflow" / "gates" / "ponytail.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    assert result["status"] == "recorded"
    assert payload["source"] == PONYTAIL_SOURCE
    assert payload["reviewed_lifecycle_hooks"] is True


def test_implementation_package_requires_fresh_graphify_and_ponytail(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    _write_brainstorm(tmp_path)

    with pytest.raises(WorkbenchError, match="Repair gate evidence first"):
        prepare_implementation_package(tmp_path, session_id="workbench-session")

    _write_graphify_evidence(tmp_path)
    _approve_ponytail(tmp_path)

    package = prepare_implementation_package(
        tmp_path,
        session_id="workbench-session",
        definition_of_done="Keep implementation as a package, not direct code changes.",
    )

    assert package.definition_of_done["graphify_requirements"][0] == "Use Graphify evidence from safishamsi/graphify only."
    assert "Skip unnecessary work." in package.definition_of_done["ponytail_simplification_rules"]
    assert package.starting_point["graphify_summary"]
    assert ".devflow/gates/ponytail.json" in package.starting_point["evidence_paths"]
    assert "graphify-out/GRAPH_REPORT.md" in package.starting_point["evidence_paths"]
    assert "Produce a concise `implementation.md` package" in package.definition_of_done_markdown
    assert "## Ponytail Checklist" in package.starting_point_markdown


def test_workbench_implementation_writes_artifact_only_after_builder_judge_passes(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    _write_brainstorm(tmp_path)
    _write_graphify_evidence(tmp_path)
    _approve_ponytail(tmp_path)

    def fake_runner(_root: Path, config: BuilderJudgeConfig) -> BuilderJudgeRun:
        assert "Graphify Requirements" in config.definition_of_done
        assert "Ponytail Simplification Rules" in config.definition_of_done
        return _passing_run(config)

    result = run_workbench_implementation(
        tmp_path,
        session_id="workbench-session",
        run_loop=fake_runner,
    )

    implementation = tmp_path / ".devflow" / "brainstorms" / "workbench-session" / "implementation.md"
    assert result.status == "passed"
    assert result.implementation_path == ".devflow/brainstorms/workbench-session/implementation.md"
    assert implementation.read_text(encoding="utf-8").startswith("# Implementation")
    assert result.refactor_offer_path is None


def test_workbench_implementation_offers_refactor_when_builder_judge_fails(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    _write_brainstorm(tmp_path)
    _write_graphify_evidence(tmp_path)
    _approve_ponytail(tmp_path)

    def fake_runner(_root: Path, config: BuilderJudgeConfig) -> BuilderJudgeRun:
        return _escalated_run(config)

    result = run_workbench_implementation(
        tmp_path,
        session_id="workbench-session",
        run_loop=fake_runner,
    )

    implementation = tmp_path / ".devflow" / "brainstorms" / "workbench-session" / "implementation.md"
    offer = tmp_path / ".devflow" / "brainstorms" / "workbench-session" / "refactor-offer.json"
    payload: dict[str, Any] = json.loads(offer.read_text(encoding="utf-8"))

    assert result.status == "escalated"
    assert result.implementation_path is None
    assert result.refactor_offer_path == ".devflow/brainstorms/workbench-session/refactor-offer.json"
    assert not implementation.exists()
    assert payload["action"]["label"] == "Send to Refactor Loop"
    assert "Skip unnecessary work." in payload["ponytail_rules"]
