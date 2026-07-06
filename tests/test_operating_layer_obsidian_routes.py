from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path

import pytest

import devflow.control_room.operating_layer_obsidian_handlers as obsidian_handlers
from devflow.control_room.operating_layer_server import OperatingLayerHTTPServer
from devflow.control_room.persistence import get_task
from tests.helpers import setup_temp_git_repo


def _serve_operating_layer(root: Path) -> tuple[OperatingLayerHTTPServer, threading.Thread, str, int]:
    server = OperatingLayerHTTPServer(("127.0.0.1", 0), root)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, host, port


def _post_json(host: str, port: int, path: str, payload: dict[str, object]) -> tuple[int, dict]:
    connection = HTTPConnection(host, port, timeout=5)
    connection.request(
        "POST",
        path,
        body=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    response = connection.getresponse()
    body = response.read().decode("utf-8")
    parsed = json.loads(body) if body else {}
    return response.status, parsed


def _get_raw(host: str, port: int, path: str) -> tuple[int, bytes, dict]:
    connection = HTTPConnection(host, port, timeout=5)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    headers = {k.lower(): v for k, v in response.getheaders()}
    return response.status, body, headers


def test_operating_layer_obsidian_cards_route_returns_helper_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    expected = {
        "ok": True,
        "available": True,
        "source": "command-center",
        "scannedAt": "2026-07-01T12:00:00Z",
        "cards": [
            {
                "id": "card-1",
                "title": "Check worker lane",
                "lane": "now",
                "status": "open",
                "source": "Inbox",
                "path": "Inbox/card.md",
                "project": "[[Dev-Flow]]",
                "summary": "Small summary",
                "why": "Useful context",
                "evidence": "Test evidence",
                "decision": "Keep",
                "next_action": "Review",
                "confidence": 88,
                "impact": 4,
                "quality_flags": ["missing-link"],
                "link": "obsidian://open?vault=Test&file=Inbox%2Fcard.md",
                "updated_at": "2026-07-01T11:59:00Z",
            }
        ],
        "lanes": {"now": []},
        "lane_counts": {"now": 1},
        "error": None,
    }
    monkeypatch.setattr(obsidian_handlers, "fetch_obsidian_cards_payload", lambda: expected)

    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/api/obsidian/cards")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        assert response.status == HTTPStatus.OK
        assert payload == expected
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_operating_layer_obsidian_task_preview_route_does_not_create_tasks(tmp_path: Path) -> None:
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(
            host,
            port,
            "/api/obsidian/task-preview",
            {
                "card": {
                    "id": "card-preview-1",
                    "title": "Preview intake card",
                    "path": "Inbox/preview.md",
                    "summary": "Only preview this card",
                    "next_action": "Review the preview",
                    "evidence": "Preview evidence",
                    "project": "[[Dev-Flow]]",
                }
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.OK
    assert payload["ok"] is True
    assert payload["source"] == "obsidian"
    assert payload["title"] == "Preview intake card"
    assert payload["source_path"] == "Inbox/preview.md"
    assert payload["source_card_id"] == "card-preview-1"
    assert payload["project"] == "[[Dev-Flow]]"
    assert not (tmp_path / ".devflow" / "tasks").exists()


def test_operating_layer_obsidian_task_create_route_creates_task_and_event(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(
            host,
            port,
            "/api/obsidian/task-create",
            {
                "card": {
                    "id": "card-create-1",
                    "summary": "Create the task from the card",
                    "path": "Inbox/create.md",
                    "nextAction": "Run the task bridge",
                    "evidence": "Create evidence",
                    "project": "[[Dev-Flow]]",
                }
            },
        )
        connection = HTTPConnection(host, port, timeout=5)
        connection.request("GET", "/api/snapshot")
        snapshot_response = connection.getresponse()
        snapshot_payload = json.loads(snapshot_response.read().decode("utf-8"))
        assert snapshot_response.status == HTTPStatus.OK
        assert snapshot_payload["tasks"][0]["detail"]["recent_events"][-1]["event"] == "obsidian_card_linked"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.OK
    assert payload["ok"] is True
    assert payload["task_id"] == "task-0001"
    assert payload["event"] == "obsidian_card_linked"
    assert payload["source_path"] == "Inbox/create.md"
    assert payload["source_card_id"] == "card-create-1"
    assert payload["status"] == "created"
    assert payload["events_path"] == ".devflow/tasks/task-0001/events.jsonl"
    assert get_task(tmp_path, "task-0001").title == "Create the task from the card"

    events = [
        json.loads(line)
        for line in (tmp_path / ".devflow" / "tasks" / "task-0001" / "events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert [event["event"] for event in events] == ["task_created", "obsidian_card_linked"]
    assert events[1]["source_path"] == "Inbox/create.md"
    assert events[1]["source_card_id"] == "card-create-1"


def test_operating_layer_obsidian_scout_pack_preview_route_does_not_create_tasks(tmp_path: Path) -> None:
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(
            host,
            port,
            "/api/obsidian/scout-pack-preview",
            {
                "card": {
                    "id": "card-scout-preview-1",
                    "title": "Preview scout pack",
                    "path": "Inbox/scout-preview.md",
                    "summary": "Only preview the scout pack",
                    "next_action": "Review the five scouts",
                    "evidence": "Preview evidence",
                    "project": "[[Dev-Flow]]",
                }
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.OK
    assert payload["ok"] is True
    assert payload["source"] == "obsidian"
    assert payload["source_path"] == "Inbox/scout-preview.md"
    assert payload["source_card_id"] == "card-scout-preview-1"
    assert payload["task_count"] == 5
    assert [task["title"] for task in payload["tasks"]] == [
        "Architecture Scout",
        "UX Scout",
        "Data Truth Scout",
        "Verification Scout",
        "Dead Code Scout",
    ]
    assert not (tmp_path / ".devflow" / "tasks").exists()


def test_operating_layer_obsidian_scout_pack_create_route_creates_visible_tasks_only(tmp_path: Path) -> None:
    setup_temp_git_repo(tmp_path)
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(
            host,
            port,
            "/api/obsidian/scout-pack-create",
            {
                "card": {
                    "id": "card-scout-create-1",
                    "summary": "Create the scout pack",
                    "path": "Inbox/scout-create.md",
                    "nextAction": "Create five visible scouts",
                    "evidence": "Scout evidence",
                    "project": "[[Dev-Flow]]",
                }
            },
        )
        snapshot_status, snapshot_body, _ = _get_raw(host, port, "/api/snapshot")
        snapshot_payload = json.loads(snapshot_body.decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.OK
    assert payload["ok"] is True
    assert payload["event"] == "obsidian_scout_pack_linked"
    assert payload["task_count"] == 5
    assert [task["task_id"] for task in payload["tasks"]] == [
        "task-0001",
        "task-0002",
        "task-0003",
        "task-0004",
        "task-0005",
    ]
    assert [task["title"] for task in payload["tasks"]] == [
        "Architecture Scout",
        "UX Scout",
        "Data Truth Scout",
        "Verification Scout",
        "Dead Code Scout",
    ]
    assert snapshot_status == HTTPStatus.OK
    assert len(snapshot_payload["tasks"]) == 5

    for item in payload["tasks"]:
        task = get_task(tmp_path, item["task_id"])
        assert task.title == item["title"]
        assert task.status == "created"
        assert not (tmp_path / ".devflow" / "tasks" / task.id / "agents").exists()
        events = [
            json.loads(line)
            for line in (tmp_path / ".devflow" / "tasks" / task.id / "events.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        assert [event["event"] for event in events] == ["task_created", "obsidian_scout_pack_linked"]
        assert events[1]["source_path"] == "Inbox/scout-create.md"
        assert events[1]["source_card_id"] == "card-scout-create-1"


def test_operating_layer_obsidian_task_routes_reject_bad_input(tmp_path: Path) -> None:
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(host, port, "/api/obsidian/task-preview", {"card": {"path": "Inbox/missing.md"}})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.BAD_REQUEST
    assert payload["error"] == "card title or summary is required"


@pytest.mark.parametrize(
    "path",
    [
        "/api/obsidian/scout-pack-preview",
        "/api/obsidian/scout-pack-create",
    ],
)
def test_operating_layer_obsidian_scout_pack_routes_reject_bad_input(tmp_path: Path, path: str) -> None:
    server, thread, host, port = _serve_operating_layer(tmp_path)
    try:
        status, payload = _post_json(host, port, path, {"card": {"path": "Inbox/missing.md"}})
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.BAD_REQUEST
    assert payload["error"] == "card title or summary is required"
    assert not (tmp_path / ".devflow" / "tasks").exists()
