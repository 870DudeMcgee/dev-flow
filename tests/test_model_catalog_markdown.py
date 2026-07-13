"""Tests for the generated read-only Obsidian catalog section."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from devflow.control_room.model_catalog import model_catalog_snapshot
from devflow.loop.model_catalog import load_free_cloud_catalog, refresh_free_cloud_catalog
from devflow.loop.model_catalog_markdown import (
    render_model_catalog_markdown,
    update_model_dashboard,
)


def _payload() -> dict:
    return {
        "data": [
            {
                "id": "example/code:free",
                "name": "Example Code",
                "description": "Coding and reasoning agent.",
                "context_length": 262_144,
                "architecture": {
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
                "pricing": {"prompt": "0", "completion": "0"},
                "supported_parameters": ["tools", "reasoning", "structured_outputs"],
            }
        ]
    }


def _seed(root: Path) -> None:
    refresh_free_cloud_catalog(
        root,
        fetch_catalog=_payload,
        fetched_at=datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc),
    )


def test_markdown_contains_read_only_inventory_history_and_rankings(tmp_path: Path) -> None:
    _seed(tmp_path)

    rendered = render_model_catalog_markdown(
        load_free_cloud_catalog(tmp_path),
        model_catalog_snapshot(tmp_path),
    )

    assert "Generated read-only inventory" in rendered
    assert "Last checked: 2026-07-13T10:00:00+00:00" in rendered
    assert "Free text-chat models: **1**" in rendered
    assert "## Free-Cloud Role Rankings" in rendered
    assert "example/code:free" in rendered
    assert "95/100" in rendered
    assert "## Free-Cloud Inventory" in rendered
    assert "2026-07-13T10:00:00+00:00" in rendered
    assert "Restore" not in rendered
    assert "Quarantine" not in rendered


def test_dashboard_update_replaces_only_generated_block_and_is_idempotent(tmp_path: Path) -> None:
    dashboard = tmp_path / "dashboard.md"
    dashboard.write_text("# Dashboard\n\nHuman notes stay here.\n", encoding="utf-8")
    generated = "Generated model inventory\n"

    first = update_model_dashboard(dashboard, generated)
    second = update_model_dashboard(dashboard, generated)
    content = dashboard.read_text(encoding="utf-8")

    assert first is True
    assert second is False
    assert content.startswith("# Dashboard\n\nHuman notes stay here.\n")
    assert content.count("<!-- DEVFLOW-MODEL-CATALOG:START -->") == 1
    assert content.count("<!-- DEVFLOW-MODEL-CATALOG:END -->") == 1
    assert "Generated model inventory" in content
