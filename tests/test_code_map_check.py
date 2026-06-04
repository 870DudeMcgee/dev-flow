"""Tests for devflow.control_room.code_map.map_check — Milestone 11D."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.code_map import CodeMapError, map_check, map_init


runner = CliRunner()


def _write_valid_map(root: Path, *, cli_path: str = "src/devflow/cli.py") -> None:
    (root / "src/devflow/control_room").mkdir(parents=True, exist_ok=True)
    (root / cli_path).parent.mkdir(parents=True, exist_ok=True)
    (root / cli_path).write_text("# cli\n", encoding="utf-8")
    (root / "src/devflow/control_room/service.py").write_text("# service\n", encoding="utf-8")
    (root / "CODE_MAP.md").write_text(
        f"""# Code Map

## What this repo does

Dev-Flow coordinates local AI coding workers with visible task evidence.

## Layout

- `src/` - production source
- `tests/` - test suite

## Entry points

- CLI: `{cli_path}`
- Service: src/devflow/control_room/service.py

## What to read first (worker orientation)

1. `docs/roadmap.md`
2. `AGENTS.md`

## What to skip

- `build/`
- `src/devflow/_legacy/`

## Owners / contacts

- Primary: Josh

## Last reviewed

2026-06-04
""",
        encoding="utf-8",
    )


class TestMapCheckService:
    def test_missing_code_map_raises(self, tmp_path: Path) -> None:
        with pytest.raises(CodeMapError, match="devflow map init"):
            map_check(tmp_path)

    def test_fresh_template_fails_with_unfilled_sections(self, tmp_path: Path) -> None:
        map_init(tmp_path)
        result = map_check(tmp_path)
        assert result.ok is False
        assert "What this repo does" in result.unfilled_sections
        assert "Entry points" in result.unfilled_sections
        assert "Owners / contacts" in result.unfilled_sections
        assert "Last reviewed" in result.unfilled_sections

    def test_filled_code_map_passes_with_valid_entry_points(self, tmp_path: Path) -> None:
        _write_valid_map(tmp_path)
        result = map_check(tmp_path)
        assert result.ok is True
        assert result.missing_sections == ()
        assert result.unfilled_sections == ()
        assert result.broken_paths == ()
        assert "src/devflow/cli.py" in result.checked_paths
        assert "src/devflow/control_room/service.py" in result.checked_paths

    def test_broken_entry_point_path_fails(self, tmp_path: Path) -> None:
        _write_valid_map(tmp_path, cli_path="src/devflow/missing_cli.py")
        (tmp_path / "src/devflow/missing_cli.py").unlink()
        result = map_check(tmp_path)
        assert result.ok is False
        assert result.broken_paths == ("src/devflow/missing_cli.py",)

    def test_comments_are_stripped_before_placeholder_detection(self, tmp_path: Path) -> None:
        _write_valid_map(tmp_path)
        text = (tmp_path / "CODE_MAP.md").read_text(encoding="utf-8")
        text = text.replace(
            "Dev-Flow coordinates local AI coding workers with visible task evidence.",
            "<!-- A comment is not content. -->",
        )
        (tmp_path / "CODE_MAP.md").write_text(text, encoding="utf-8")
        result = map_check(tmp_path)
        assert result.ok is False
        assert "What this repo does" in result.unfilled_sections

    def test_todo_placeholder_marks_section_unfilled(self, tmp_path: Path) -> None:
        _write_valid_map(tmp_path)
        text = (tmp_path / "CODE_MAP.md").read_text(encoding="utf-8")
        text = text.replace("- Primary: Josh", "- Primary: TODO")
        (tmp_path / "CODE_MAP.md").write_text(text, encoding="utf-8")
        result = map_check(tmp_path)
        assert result.ok is False
        assert "Owners / contacts" in result.unfilled_sections


class TestMapCheckCli:
    def test_cli_missing_map_exits_with_clear_error(self, tmp_path: Path) -> None:
        old_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            result = runner.invoke(app, ["map", "check"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 1
        assert "CODE_MAP.md not found" in result.output
        assert "devflow map init" in result.output

    def test_cli_reports_unfilled_sections(self, tmp_path: Path) -> None:
        old_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            map_init(tmp_path)
            result = runner.invoke(app, ["map", "check"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 1
        assert "CODE_MAP.md check failed" in result.output
        assert "unfilled sections:" in result.output
        assert "Entry points" in result.output

    def test_cli_reports_success(self, tmp_path: Path) -> None:
        old_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            _write_valid_map(tmp_path)
            result = runner.invoke(app, ["map", "check"])
        finally:
            os.chdir(old_cwd)
        assert result.exit_code == 0
        assert "CODE_MAP.md check passed" in result.output
        assert "src/devflow/cli.py" in result.output
