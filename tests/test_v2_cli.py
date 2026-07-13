"""Regression coverage for the V2-only command surface."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from typer.testing import CliRunner


def _create_fixture_target(root: Path, target_file: str = "src/main.py") -> str:
    target = root / target_file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def main() -> str:\n    return 'ok'\n", encoding="utf-8")
    return target_file


def test_cli_import_does_not_load_legacy_namespace() -> None:
    retired_namespace = "devflow." + "legacy"
    sys.modules.pop("devflow.cli", None)
    for module_name in list(sys.modules):
        if module_name == retired_namespace or module_name.startswith(f"{retired_namespace}."):
            sys.modules.pop(module_name)

    importlib.import_module("devflow.cli")

    assert not any(
        module_name == retired_namespace or module_name.startswith(f"{retired_namespace}.")
        for module_name in sys.modules
    )


def test_v2_cli_exposes_status_and_deterministic_loop_fixture(tmp_path: Path, monkeypatch) -> None:
    from devflow.cli import app

    target_file = _create_fixture_target(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    help_result = runner.invoke(app, ["--help"])
    result = runner.invoke(app, ["loop", "spine-fixture", "--target-file", target_file, "--json"])

    assert help_result.exit_code == 0, help_result.output
    assert "status" in help_result.output
    assert "operating-layer" not in help_result.output
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["final_stage"] == "complete"


def test_model_catalog_refresh_is_silent_when_unchanged(tmp_path: Path, monkeypatch) -> None:
    from devflow.cli import app
    from devflow.loop.model_catalog import CatalogRefreshResult

    current_path = tmp_path / ".devflow" / "model-catalog" / "current.json"
    monkeypatch.setattr(
        "devflow.cli.refresh_free_cloud_catalog",
        lambda root: CatalogRefreshResult(
            changed=False,
            added=(),
            removed=(),
            modified=(),
            current_path=current_path,
            history_path=None,
            model_count=12,
        ),
    )

    result = CliRunner().invoke(app, ["models", "refresh", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert result.output == ""


def test_model_catalog_refresh_reports_changes_as_json(tmp_path: Path, monkeypatch) -> None:
    from devflow.cli import app
    from devflow.loop.model_catalog import CatalogRefreshResult

    current_path = tmp_path / ".devflow" / "model-catalog" / "current.json"
    history_path = tmp_path / ".devflow" / "model-catalog" / "history" / "2026-07-13.json"
    monkeypatch.setattr(
        "devflow.cli.refresh_free_cloud_catalog",
        lambda root: CatalogRefreshResult(
            changed=True,
            added=("example/new:free",),
            removed=("example/old:free",),
            modified=("example/changed:free",),
            current_path=current_path,
            history_path=history_path,
            model_count=12,
        ),
    )

    result = CliRunner().invoke(
        app,
        ["models", "refresh", "--root", str(tmp_path), "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "added": ["example/new:free"],
        "changed": True,
        "current_path": str(current_path),
        "dashboard_changed": False,
        "history_path": str(history_path),
        "model_count": 12,
        "modified": ["example/changed:free"],
        "removed": ["example/old:free"],
    }


def test_model_refresh_updates_requested_obsidian_dashboard(tmp_path: Path, monkeypatch) -> None:
    from devflow.cli import app
    from devflow.loop.model_catalog import CatalogRefreshResult

    current_path = tmp_path / ".devflow" / "model-catalog" / "current.json"
    dashboard = tmp_path / "Model Dashboard.md"
    calls: list[tuple[Path, str]] = []
    monkeypatch.setattr(
        "devflow.cli.refresh_free_cloud_catalog",
        lambda root: CatalogRefreshResult(
            changed=False,
            added=(),
            removed=(),
            modified=(),
            current_path=current_path,
            history_path=None,
            model_count=12,
        ),
    )
    monkeypatch.setattr("devflow.cli.load_free_cloud_catalog", lambda root: {"models": []})
    monkeypatch.setattr("devflow.cli.model_catalog_snapshot", lambda root: {"model_count": 12})
    monkeypatch.setattr("devflow.cli.render_model_catalog_markdown", lambda catalog, snapshot: "generated\n")
    monkeypatch.setattr(
        "devflow.cli.update_model_dashboard",
        lambda path, content: calls.append((path, content)) is None or True,
    )

    result = CliRunner().invoke(
        app,
        [
            "models",
            "refresh",
            "--root",
            str(tmp_path),
            "--obsidian-dashboard",
            str(dashboard),
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [(dashboard, "generated\n")]
    assert result.output == ""
