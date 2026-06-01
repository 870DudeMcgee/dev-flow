from __future__ import annotations

import os
from pathlib import Path

import pytest

from devflow.control_room import persistence


def test_atomic_write_text_preserves_existing_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "task.yaml"
    target.write_text("original\n", encoding="utf-8")

    def fail_replace(source: str | os.PathLike[str], destination: str | os.PathLike[str]) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(persistence.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        persistence.atomic_write_text(target, "updated\n")

    assert target.read_text(encoding="utf-8") == "original\n"
    assert not any(tmp_path.glob(".task.yaml.*.tmp"))