from __future__ import annotations

import pytest
from pathlib import Path
from devflow.control_room.patch_applier import (
    PatchError,
    PatchParseError,
    PatchSelectionError,
    PatchApplicationError,
    parse_unified_diff,
    apply_patch_files,
)

def test_exceptions_exist():
    assert issubclass(PatchSelectionError, PatchError)
    assert issubclass(PatchParseError, PatchError)
    assert issubclass(PatchApplicationError, PatchError)

def test_parse_empty_diff_raises_parse_error():
    with pytest.raises(PatchParseError, match="Empty diff"):
        parse_unified_diff("")

def test_parse_valid_diff_with_ignored_metadata():
    diff = (
        "diff --git a/hello.txt b/hello.txt\n"
        "index abc123..def456 100644\n"
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -1,3 +1,3 @@\n"
        " hello\n"
        "-world\n"
        "+universe\n"
        " ok\n"
    )
    files = parse_unified_diff(diff)
    assert len(files) == 1
    assert files[0].source_file == "hello.txt"
    assert files[0].target_file == "hello.txt"
    assert len(files[0].hunks) == 1
    assert files[0].hunks[0].old_start == 1

def test_parse_rejected_metadata_raises():
    diff_with_mode = (
        "diff --git a/hello.txt b/hello.txt\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/hello.txt\n"
    )
    with pytest.raises(PatchParseError, match="Unsupported metadata: new file mode"):
        parse_unified_diff(diff_with_mode)

def test_apply_modify_exact_match(tmp_path: Path):
    target = tmp_path / "hello.txt"
    target.write_text("line one\nline two\nline three\n", encoding="utf-8")
    diff = (
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -2,2 +2,2 @@\n"
        " line two\n"
        "-line three\n"
        "+line beautiful three\n"
    )
    patch_files = parse_unified_diff(diff)
    apply_patch_files(tmp_path, patch_files)
    assert target.read_text(encoding="utf-8") == "line one\nline two\nline beautiful three\n"

def test_apply_offset_multi_hunk(tmp_path: Path):
    target = tmp_path / "hello.txt"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")
    diff = (
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -1,2 +1,3 @@\n"
        " one\n"
        "+inserted\n"
        " two\n"
        "@@ -3 +4 @@\n"
        "-three\n"
        "+four\n"
    )
    patch_files = parse_unified_diff(diff)
    apply_patch_files(tmp_path, patch_files)
    assert target.read_text(encoding="utf-8") == "one\ninserted\ntwo\nfour\n"

def test_apply_hunk_mismatch_raises_application_error(tmp_path: Path):
    target = tmp_path / "hello.txt"
    target.write_text("one\ndirty\nthree\n", encoding="utf-8")
    diff = (
        "--- a/hello.txt\n"
        "+++ b/hello.txt\n"
        "@@ -1,2 +1,2 @@\n"
        " one\n"
        "-two\n"
        "+inserted\n"
    )
    patch_files = parse_unified_diff(diff)
    with pytest.raises(PatchApplicationError, match="mismatch at line 2"):
        apply_patch_files(tmp_path, patch_files)

def test_symlink_rejection(tmp_path: Path):
    outside = tmp_path / "outside.txt"
    outside.write_text("unmodified outside\n", encoding="utf-8")
    
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sym = workspace / "link.txt"
    sym.symlink_to(outside)
    
    diff = (
        "--- a/link.txt\n"
        "+++ b/link.txt\n"
        "@@ -1 +1 @@\n"
        "-unmodified outside\n"
        "+hacked!\n"
    )
    patch_files = parse_unified_diff(diff)
    with pytest.raises(PatchApplicationError, match="escapes workspace boundary|symlinks are rejected"):
        apply_patch_files(workspace, patch_files)

    
    assert outside.read_text(encoding="utf-8") == "unmodified outside\n"

def test_atomic_partial_failure_prevention(tmp_path: Path):
    file1 = tmp_path / "file1.txt"
    file1.write_text("one\n", encoding="utf-8")
    file2 = tmp_path / "file2.txt"
    file2.write_text("two\n", encoding="utf-8")
    
    diff = (
        "--- a/file1.txt\n"
        "+++ b/file1.txt\n"
        "@@ -1 +1 @@\n"
        "-one\n"
        "+one modified\n"
        "--- a/file2.txt\n"
        "+++ b/file2.txt\n"
        "@@ -1 +1 @@\n"
        "-mismatch\n"
        "+two modified\n"
    )
    patch_files = parse_unified_diff(diff)
    with pytest.raises(PatchApplicationError, match="mismatch"):
        apply_patch_files(tmp_path, patch_files)
    
    assert file1.read_text(encoding="utf-8") == "one\n"
