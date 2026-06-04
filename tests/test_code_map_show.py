"""Tests for devflow.control_room.code_map.map_show — Milestone 11C.

Scope: map_show service function only.
No CLI runner tests, no provider calls, no routing, no database.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from devflow.control_room.code_map import CodeMapError, _DEFAULT_TEMPLATE, map_init, map_show


class TestMapShowReturnsContent:
    def test_returns_string(self, tmp_path: Path) -> None:
        (tmp_path / "CODE_MAP.md").write_text("# My Map\n", encoding="utf-8")
        result = map_show(tmp_path)
        assert isinstance(result, str)

    def test_returns_exact_file_content(self, tmp_path: Path) -> None:
        content = "# My Map\n\nSome content.\n"
        (tmp_path / "CODE_MAP.md").write_text(content, encoding="utf-8")
        assert map_show(tmp_path) == content

    def test_returns_template_after_map_init(self, tmp_path: Path) -> None:
        map_init(tmp_path)
        assert map_show(tmp_path) == _DEFAULT_TEMPLATE

    def test_returns_utf8_content(self, tmp_path: Path) -> None:
        content = "# Código\n\n— em dash and accents: résumé\n"
        (tmp_path / "CODE_MAP.md").write_text(content, encoding="utf-8")
        assert map_show(tmp_path) == content

    def test_round_trip_after_overwrite(self, tmp_path: Path) -> None:
        map_init(tmp_path)
        new_content = "# Updated Map\n"
        (tmp_path / "CODE_MAP.md").write_text(new_content, encoding="utf-8")
        assert map_show(tmp_path) == new_content


class TestMapShowMissingFile:
    def test_raises_when_no_code_map_md(self, tmp_path: Path) -> None:
        with pytest.raises(CodeMapError):
            map_show(tmp_path)

    def test_error_message_mentions_map_init(self, tmp_path: Path) -> None:
        with pytest.raises(CodeMapError, match="devflow map init"):
            map_show(tmp_path)

    def test_error_message_mentions_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(CodeMapError, match="not found"):
            map_show(tmp_path)

    def test_raises_code_map_error_type(self, tmp_path: Path) -> None:
        with pytest.raises(CodeMapError) as exc_info:
            map_show(tmp_path)
        assert isinstance(exc_info.value, CodeMapError)

    def test_does_not_raise_after_init(self, tmp_path: Path) -> None:
        map_init(tmp_path)
        # Should not raise
        map_show(tmp_path)
