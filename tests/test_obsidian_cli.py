"""Tests for the Obsidian CLI commands (M1-S4)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.loop.pipeline_run import create_pipeline_run
from devflow.loop.workflow_ledger import (
    EvidenceReference,
    NodeReceipt,
    WorkflowEvent,
    initialize_workflow_run,
    record_node_outcome,
)


def _build_canonical_run(root: Path, through: str | None = None) -> str:
    """Build a disposable canonical run and optionally advance it."""
    run_id = create_pipeline_run(root, {"repo": "test/repo"})
    initialize_workflow_run(root, run_id)

    chain = (
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
    for idx, (node_id, evidence_id) in enumerate(chain, start=1):
        evidence_file = f"{evidence_id}.md"
        run_dir = root / ".devflow" / "pipeline-runs" / run_id
        if not (run_dir / evidence_file).exists():
            (run_dir / evidence_file).write_text(f"# {evidence_id}\n", encoding="utf-8")
        record_node_outcome(
            root,
            run_id,
            receipt=NodeReceipt(
                receipt_id=f"r{idx}",
                node_id=node_id,
                outcome="success",
                evidence=(EvidenceReference(key=evidence_id, reference=evidence_file),),
            ),
            event=WorkflowEvent(
                event_id=f"e{idx}",
                node_id=node_id,
                outcome="success",
                receipt_id=f"r{idx}",
            ),
        )
        if node_id == through:
            break
    return run_id


def test_obsidian_help_shows_commands() -> None:
    from devflow.cli import app

    result = CliRunner().invoke(app, ["obsidian", "--help"])

    assert result.exit_code == 0, result.output
    assert "run" in result.output
    assert "list" in result.output


def test_obsidian_run_emits_generated(tmp_path: Path) -> None:
    from devflow.cli import app

    repo = tmp_path / "repo"
    vault = tmp_path / "vault"
    run_id = _build_canonical_run(repo, through="idea")

    result = CliRunner().invoke(
        app,
        ["obsidian", "run", run_id, "--root", str(repo), "--vault", str(vault), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["run_id"] == run_id
    assert payload["health"] == "Running"
    assert payload["phase"] == "Definition"
    assert len(payload["files_written"]) == 5

    generated = vault / "Command Center" / "Projects" / "DevFlow" / ".generated"
    assert (generated / "Overview.md").is_file()
    assert (generated / "Workflow.md").is_file()


def test_obsidian_run_requires_canonical_run(tmp_path: Path) -> None:
    from devflow.cli import app

    repo = tmp_path / "repo"
    run_id = create_pipeline_run(repo, {"repo": "test/repo"})
    # initialize_workflow_run NOT called — no canonical marker

    result = CliRunner().invoke(
        app,
        ["obsidian", "run", run_id, "--root", str(repo), "--vault", str(tmp_path)],
    )

    assert result.exit_code == 1, result.output
    assert "not canonical" in result.output


def test_obsidian_run_nonexistent_run(tmp_path: Path) -> None:
    from devflow.cli import app

    result = CliRunner().invoke(
        app,
        ["obsidian", "run", "nonexistent-run", "--root", str(tmp_path), "--vault", str(tmp_path)],
    )

    assert result.exit_code == 1, result.output
    assert "not canonical" in result.output


def test_obsidian_list_shows_canonical_runs(tmp_path: Path) -> None:
    from devflow.cli import app

    repo = tmp_path / "repo"
    _build_canonical_run(repo, through="spec")

    result = CliRunner().invoke(
        app,
        ["obsidian", "list", "--root", str(repo), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["health"] == "Running"
    assert payload["runs"][0]["phase"] == "Planning"


def test_obsidian_list_empty(tmp_path: Path) -> None:
    from devflow.cli import app

    result = CliRunner().invoke(
        app,
        ["obsidian", "list", "--root", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "No canonical runs" in result.output


def test_obsidian_list_skips_noncanonical(tmp_path: Path) -> None:
    from devflow.cli import app

    repo = tmp_path / "repo"
    # Create a non-canonical run (no initialize_workflow_run)
    create_pipeline_run(repo, {"repo": "test/repo"})

    result = CliRunner().invoke(
        app,
        ["obsidian", "list", "--root", str(repo), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["runs"]) == 0


def test_obsidian_run_plain_output(tmp_path: Path) -> None:
    from devflow.cli import app

    repo = tmp_path / "repo"
    vault = tmp_path / "vault"
    run_id = _build_canonical_run(repo)

    result = CliRunner().invoke(
        app,
        ["obsidian", "run", run_id, "--root", str(repo), "--vault", str(vault)],
    )

    assert result.exit_code == 0, result.output
    assert "Projected" in result.output
    assert "Health" in result.output
    assert "Files: 5" in result.output
