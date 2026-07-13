"""Control-room projection and operator controls for the model catalog."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

from devflow.control_room.model_catalog import (
    change_model_role_health,
    model_catalog_snapshot,
)
from devflow.loop.model_catalog import refresh_free_cloud_catalog


def _payload() -> dict:
    return {
        "data": [
            {
                "id": "example/code:free",
                "name": "Example Code",
                "description": "Agentic coding model for software engineering and repository work.",
                "context_length": 262_144,
                "architecture": {
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
                "pricing": {"prompt": "0", "completion": "0"},
                "supported_parameters": [
                    "tools",
                    "reasoning",
                    "structured_outputs",
                ],
            },
            {
                "id": "example/reasoner:free",
                "name": "Example Reasoner",
                "description": "Long-context reasoning and planning model.",
                "context_length": 131_072,
                "architecture": {
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
                "pricing": {"prompt": "0", "completion": "0"},
                "supported_parameters": ["reasoning", "structured_outputs"],
            },
        ]
    }


def _seed_catalog(root: Path) -> None:
    refresh_free_cloud_catalog(
        root,
        fetch_catalog=_payload,
        fetched_at=datetime(2026, 7, 13, 10, 0, tzinfo=timezone.utc),
    )


def test_snapshot_projects_counts_and_ranked_profiles(tmp_path: Path) -> None:
    _seed_catalog(tmp_path)

    snapshot = model_catalog_snapshot(tmp_path)

    assert snapshot["status"] == "ready"
    assert snapshot["model_count"] == 2
    assert snapshot["capability_counts"] == {
        "coding": 1,
        "image_input": 0,
        "reasoning": 2,
        "structured_output": 2,
        "tool_calling": 1,
    }
    assert snapshot["limits"] == {
        "local_heavy": 3,
        "total": 8,
        "writers": 4,
    }
    assert snapshot["profiles"]["builder"][0]["model_id"] == "example/code:free"
    assert snapshot["profiles"]["builder"][0]["confidence"] == "advertised"
    assert snapshot["profiles"]["builder"][0]["sample_count"] == 0
    assert len(snapshot["profiles"]["research-scout"]) == 2


def test_quarantine_is_role_specific_and_restore_requires_human(tmp_path: Path) -> None:
    _seed_catalog(tmp_path)

    quarantined = change_model_role_health(
        tmp_path,
        model_id="example/code:free",
        profile="builder",
        action="quarantine",
        reason="malformed tool calls",
        human_approved=True,
    )

    assert quarantined["health"] == "quarantined"
    snapshot = model_catalog_snapshot(tmp_path)
    assert snapshot["profiles"]["builder"] == []
    assert "example/code:free" in {
        candidate["model_id"]
        for candidate in snapshot["profiles"]["research-scout"]
    }
    assert snapshot["quarantined_roles"] == [
        {
            "model_id": "example/code:free",
            "profile": "builder",
            "reason": "malformed tool calls",
        }
    ]

    with pytest.raises(ValueError, match="human approval"):
        change_model_role_health(
            tmp_path,
            model_id="example/code:free",
            profile="builder",
            action="restore",
            human_approved=False,
        )

    restored = change_model_role_health(
        tmp_path,
        model_id="example/code:free",
        profile="builder",
        action="restore",
        human_approved=True,
    )
    assert restored["health"] == "healthy"
    assert model_catalog_snapshot(tmp_path)["profiles"]["builder"]


def test_control_room_serves_catalog_and_requires_confirmed_restore(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from devflow.control_room.server import StatusServer

    _seed_catalog(tmp_path)
    monkeypatch.setattr(
        "devflow.control_room.server.workspace_api.get_active_workspace",
        lambda: None,
    )
    server = StatusServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(f"{base_url}/api/model-catalog", timeout=5) as response:
            snapshot = json.load(response)
        assert snapshot["model_count"] == 2

        quarantine_request = urllib.request.Request(
            f"{base_url}/api/model-catalog/health",
            data=json.dumps({
                "model_id": "example/code:free",
                "profile": "builder",
                "action": "quarantine",
                "reason": "tool failures",
                "human_approved": True,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(quarantine_request, timeout=5) as response:
            changed = json.load(response)
        assert changed["score"]["health"] == "quarantined"

        restore_request = urllib.request.Request(
            f"{base_url}/api/model-catalog/health",
            data=json.dumps({
                "model_id": "example/code:free",
                "profile": "builder",
                "action": "restore",
                "human_approved": False,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(restore_request, timeout=5)
        assert exc_info.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
