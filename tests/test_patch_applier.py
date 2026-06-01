from __future__ import annotations

import pytest
from pathlib import Path
from devflow.control_room.patch_applier import (
    PatchError,
    PatchParseError,
    PatchSelectionError,
    PatchApplicationError,
    parse_unified_diff,
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

