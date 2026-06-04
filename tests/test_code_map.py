"""Tests for devflow.control_room.code_map — Milestone 11B.

Scope: map_init service function only.
No CLI runner tests (those live in test_cli_map_init.py).
No provider calls, routing, database, or external services.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from devflow.control_room.code_map import CodeMapError, _DEFAULT_TEMPLATE, map_init


class TestMapInitCreatesFile:
    def test_creates_code_map_md(self, tmp_path: Path) -> None:
        result = map_init(tmp_path)
        assert result == tmp_path / "CODE_MAP.md"
        assert result.exists()

    def test_file_content_is_template(self, tmp_path: Path) -> None:
        result = map_init(tmp_path)
        assert result.read_text(encoding="utf-8") == _DEFAULT_TEMPLATE

    def test_template_has_required_sections(self, tmp_path: Path) -> None:
        result = map_init(tmp_path)
        text = result.read_text(encoding="utf-8")
        assert "## What this repo does" in text
        assert "## Layout" in text
        assert "## Entry points" in text
        assert "## What to read first" in text
        assert "## What to skip" in text
        assert "## Last reviewed" in text

    def test_returns_path_object(self, tmp_path: Path) -> None:
        result = map_init(tmp_path)
        assert isinstance(result, Path)

    def test_file_is_utf8(self, tmp_path: Path) -> None:
        result = map_init(tmp_path)
        # Should be decodable without error
        result.read_text(encoding="utf-8")


class TestMapInitGuardsExistingFile:
    def test_raises_when_file_exists(self, tmp_path: Path) -> None:
        (tmp_path / "CODE_MAP.md").write_text("existing", encoding="utf-8")
        with pytest.raises(CodeMapError, match="already exists"):
            map_init(tmp_path)

    def test_existing_file_not_overwritten_by_default(self, tmp_path: Path) -> None:
        target = tmp_path / "CODE_MAP.md"
        target.write_text("keep-me", encoding="utf-8")
        with pytest.raises(CodeMapError):
            map_init(tmp_path)
        assert target.read_text(encoding="utf-8") == "keep-me"

    def test_force_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "CODE_MAP.md"
        target.write_text("old-content", encoding="utf-8")
        result = map_init(tmp_path, force=True)
        assert result.read_text(encoding="utf-8") == _DEFAULT_TEMPLATE

    def test_force_flag_false_is_default(self, tmp_path: Path) -> None:
        (tmp_path / "CODE_MAP.md").write_text("x", encoding="utf-8")
        with pytest.raises(CodeMapError):
            map_init(tmp_path, force=False)


class TestMapInitErrorMessage:
    def test_error_mentions_force(self, tmp_path: Path) -> None:
        (tmp_path / "CODE_MAP.md").write_text("x", encoding="utf-8")
        with pytest.raises(CodeMapError, match="--force"):
            map_init(tmp_path)

    def test_error_is_code_map_error_subclass(self, tmp_path: Path) -> None:
        (tmp_path / "CODE_MAP.md").write_text("x", encoding="utf-8")
        with pytest.raises(CodeMapError) as exc_info:
            map_init(tmp_path)
        assert isinstance(exc_info.value, CodeMapError)
