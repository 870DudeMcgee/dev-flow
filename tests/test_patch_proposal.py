from __future__ import annotations

from pathlib import Path

import pytest

from devflow.legacy.control_room.patch_proposal import (
    PatchProposalParseError,
    inspect_patch_proposal,
    is_dangerous_patch_path,
    is_high_risk_patch_path,
    normalize_hunk_line_counts,
    parse_patch_proposal,
    resolve_workspace_patch_target,
)


def _modify_patch(path: str) -> str:
    return f"""diff --git a/{path} b/{path}
--- a/{path}
+++ b/{path}
@@ -1 +1 @@
-old
+new
"""


def test_patch_proposal_parses_touched_files_and_hunks() -> None:
    proposal = parse_patch_proposal(_modify_patch("docs/a.md"))

    assert proposal.touched_files == ["docs/a.md"]
    assert proposal.hunk_count == 1
    assert len(proposal.files) == 1
    file_patch = proposal.files[0]
    assert file_patch.source_file == "docs/a.md"
    assert file_patch.target_file == "docs/a.md"
    assert file_patch.target_path == "docs/a.md"
    assert file_patch.hunks[0].old_lines == 1
    assert file_patch.hunks[0].new_lines == 1
    assert file_patch.hunks[0].original_lines == ["old"]
    assert file_patch.hunks[0].patched_lines == ["new"]


def test_patch_proposal_rejects_mismatched_hunk_line_counts() -> None:
    patch = """diff --git a/docs/a.md b/docs/a.md
--- a/docs/a.md
+++ b/docs/a.md
@@ -1 +1 @@
-old
+new
+extra
"""

    with pytest.raises(PatchProposalParseError, match="Malformed hunk line counts"):
        parse_patch_proposal(patch)


def test_hunk_count_normalizer_repairs_header_counts() -> None:
    patch = """diff --git a/docs/a.md b/docs/a.md
--- a/docs/a.md
+++ b/docs/a.md
@@ -1 +1 @@
-old
+new
+extra
"""

    normalized = normalize_hunk_line_counts(patch)

    assert "@@ -1 +1,2 @@" in normalized
    proposal = parse_patch_proposal(normalized)
    assert proposal.files[0].hunks[0].old_lines == 1
    assert proposal.files[0].hunks[0].new_lines == 2


def test_patch_proposal_inspection_reports_structural_validity() -> None:
    valid = inspect_patch_proposal(_modify_patch("docs/a.md"))
    invalid = inspect_patch_proposal("not a patch")

    assert valid.structurally_valid is True
    assert valid.files_touched == ["docs/a.md"]
    assert invalid.structurally_valid is False
    assert invalid.parse_error == "Patch has no hunks."


def test_apply_parser_can_reject_unsupported_metadata() -> None:
    patch = """diff --git a/docs/a.md b/docs/a.md
old mode 100644
new mode 100755
--- a/docs/a.md
+++ b/docs/a.md
@@ -1 +1 @@
-old
+new
"""

    assert parse_patch_proposal(patch).touched_files == ["docs/a.md"]
    with pytest.raises(PatchProposalParseError, match="Unsupported metadata: old mode"):
        parse_patch_proposal(patch, reject_unsupported_apply_metadata=True)


def test_patch_path_policy_is_shared() -> None:
    assert is_dangerous_patch_path("../evil.py")
    assert is_dangerous_patch_path(".devflow/tasks/task-0001/packet.json")
    assert is_high_risk_patch_path("src/devflow/control_room/service.py")


def test_workspace_target_resolution_enforces_boundary(tmp_path: Path) -> None:
    safe = resolve_workspace_patch_target(tmp_path, "docs/a.md")
    assert safe == (tmp_path / "docs" / "a.md").resolve()

    with pytest.raises(ValueError, match="traversal rejected"):
        resolve_workspace_patch_target(tmp_path, "../evil.py")
    with pytest.raises(ValueError, match="Dangerous or generated"):
        resolve_workspace_patch_target(tmp_path, ".git/config")


def test_patch_evidence_modules_delegate_to_shared_proposal_module() -> None:
    module_sources = [
        Path("src/devflow/control_room/patch_review.py").read_text(encoding="utf-8"),
        Path("src/devflow/control_room/patch_dry_run.py").read_text(encoding="utf-8"),
        Path("src/devflow/control_room/patch_applier.py").read_text(encoding="utf-8"),
    ]

    assert all("devflow.legacy.control_room.patch_proposal" in source for source in module_sources)
    assert "def _strip_patch_prefix" not in "\n".join(module_sources)
    assert "def _file_from_diff_git" not in "\n".join(module_sources)
