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
