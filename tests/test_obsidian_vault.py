"""Behavior tests for the Obsidian atomic vault writer (M1-S3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from devflow.obsidian.vault import VaultWriteResult, write_vault_projection


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_write_creates_generated_dir(tmp_path: Path) -> None:
    """.generated/ directory is created if missing."""
    vault = tmp_path / "vault"
    views = {"Overview.md": "# Overview\n"}
    result = write_vault_projection(vault, "test-run", views)

    generated = vault / "Command Center" / "Projects" / "DevFlow" / ".generated"
    assert generated.is_dir()
    assert (generated / "Overview.md").is_file()
    assert result.vault_dir == str(generated)


def test_write_writes_all_files(tmp_path: Path) -> None:
    """All view files are written."""
    vault = tmp_path / "vault"
    views = {
        "Overview.md": "# Overview\n",
        "Workflow.md": "# Workflow\n",
        "Evidence.md": "# Evidence\n",
    }
    result = write_vault_projection(vault, "test-run", views)

    assert set(result.files_written) == {"Overview.md", "Workflow.md", "Evidence.md"}
    assert result.bytes_written > 0

    generated = vault / "Command Center" / "Projects" / "DevFlow" / ".generated"
    for fname in views:
        assert (generated / fname).is_file()


def test_write_atomic_no_human_note_overwrite(tmp_path: Path) -> None:
    """Human-authored notes outside .generated/ are untouched."""
    vault = tmp_path / "vault"
    # Create a human note in the parent dir (outside .generated/)
    project_dir = vault / "Command Center" / "Projects" / "DevFlow"
    project_dir.mkdir(parents=True)
    human_note = project_dir / "DevFlow.md"
    human_note.write_text("# My human project note\n\nDo not overwrite me.\n")

    write_vault_projection(vault, "test-run", {"Overview.md": "# Overview\n"})

    # Human note must be untouched
    assert human_note.read_text() == "# My human project note\n\nDo not overwrite me.\n"


def test_write_idempotent(tmp_path: Path) -> None:
    """Re-run with identical input → identical output bytes."""
    vault = tmp_path / "vault"
    views = {"Overview.md": "# Overview\nSame content\n"}
    write_vault_projection(vault, "test-run", views)

    generated = vault / "Command Center" / "Projects" / "DevFlow" / ".generated"
    first_bytes = (generated / "Overview.md").read_bytes()

    write_vault_projection(vault, "test-run", views)
    second_bytes = (generated / "Overview.md").read_bytes()

    assert first_bytes == second_bytes


def test_write_preserves_existing_generated(tmp_path: Path) -> None:
    """Re-run doesn't delete other files in .generated/."""
    vault = tmp_path / "vault"
    generated = vault / "Command Center" / "Projects" / "DevFlow" / ".generated"
    generated.mkdir(parents=True)

    # Pre-existing generated file
    existing = generated / "manual-generated.md"
    existing.write_text("# Manual\n")

    write_vault_projection(vault, "test-run", {"Overview.md": "# Overview\n"})

    assert existing.exists()
    assert existing.read_text() == "# Manual\n"
    assert (generated / "Overview.md").exists()


def test_write_result_reports_files(tmp_path: Path) -> None:
    """VaultWriteResult has correct fields."""
    vault = tmp_path / "vault"
    views = {"Overview.md": "# Overview\n", "History.md": "# History\n"}
    result = write_vault_projection(vault, "test-run", views)

    assert isinstance(result, VaultWriteResult)
    assert len(result.files_written) == 2
    assert "Overview.md" in result.files_written
    assert "History.md" in result.files_written
    assert result.bytes_written == len("# Overview\n") + len("# History\n")
    assert "Command Center" in result.vault_dir


def test_write_rejects_traversal(tmp_path: Path) -> None:
    """Path traversal attempts are rejected."""
    vault = tmp_path / "vault"
    views = {"../../etc/passwd": "# malicious\n"}

    with pytest.raises(ValueError, match="unsafe view filename"):
        write_vault_projection(vault, "test-run", views)


def test_write_rejects_absolute_path(tmp_path: Path) -> None:
    """Absolute paths are rejected."""
    vault = tmp_path / "vault"
    views = {"/etc/passwd": "# malicious\n"}

    with pytest.raises(ValueError, match="unsafe view filename"):
        write_vault_projection(vault, "test-run", views)


def test_write_rejects_subdirectory_path(tmp_path: Path) -> None:
    """Subdirectory paths are rejected — only flat filenames allowed."""
    vault = tmp_path / "vault"
    views = {"subdir/Overview.md": "# malicious\n"}

    with pytest.raises(ValueError, match="unsafe view filename"):
        write_vault_projection(vault, "test-run", views)


def test_write_overwrites_previous_generated_content(tmp_path: Path) -> None:
    """Second write with different content replaces the first."""
    vault = tmp_path / "vault"
    write_vault_projection(vault, "run-1", {"Overview.md": "# Run 1\n"})
    write_vault_projection(vault, "run-2", {"Overview.md": "# Run 2\n"})

    generated = vault / "Command Center" / "Projects" / "DevFlow" / ".generated"
    content = (generated / "Overview.md").read_text()
    assert content == "# Run 2\n"


def test_write_handles_empty_views(tmp_path: Path) -> None:
    """Empty views dict produces an empty result."""
    vault = tmp_path / "vault"
    result = write_vault_projection(vault, "test-run", {})

    assert result.files_written == ()
    assert result.bytes_written == 0


def test_write_integration_with_render(tmp_path: Path) -> None:
    """End-to-end: extract → render → write produces readable Markdown."""
    from devflow.loop.pipeline_run import create_pipeline_run
    from devflow.loop.workflow_ledger import (
        EvidenceReference,
        NodeReceipt,
        WorkflowEvent,
        initialize_workflow_run,
        record_node_outcome,
    )
    from devflow.obsidian.projection import extract_projection
    from devflow.obsidian.render import render_all, START_MARKER

    repo = tmp_path / "repo"
    repo.mkdir()

    run_id = create_pipeline_run(repo, {"repo": "test/repo"})
    initialize_workflow_run(repo, run_id)

    # Record idea success
    run_dir = repo / ".devflow" / "pipeline-runs" / run_id
    (run_dir / "idea-brief.md").write_text("# Idea\n")
    record_node_outcome(
        repo,
        run_id,
        receipt=NodeReceipt(
            receipt_id="r1",
            node_id="idea",
            outcome="success",
            evidence=(EvidenceReference(key="idea-brief", reference="idea-brief.md"),),
        ),
        event=WorkflowEvent(
            event_id="e1",
            node_id="idea",
            outcome="success",
            receipt_id="r1",
        ),
    )

    state = extract_projection(repo, run_id)
    views = render_all(state)

    vault = tmp_path / "vault"
    result = write_vault_projection(vault, run_id, views)

    assert len(result.files_written) == 5

    overview_path = vault / "Command Center" / "Projects" / "DevFlow" / ".generated" / "Overview.md"
    overview = overview_path.read_text()
    assert START_MARKER in overview
    assert "Definition" in overview  # current phase after idea completes
    assert "[[Workflow]]" in overview
