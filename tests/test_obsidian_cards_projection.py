from __future__ import annotations

import json
import urllib.error

import pytest

from devflow.control_room import obsidian_cards


class _MockResponse:
    def __init__(self, payload: object, *, status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_MockResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def test_fetch_obsidian_cards_payload_normalizes_command_center_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: object, timeout: float | None = None) -> _MockResponse:
        assert timeout == obsidian_cards.OBSIDIAN_CARDS_TIMEOUT_SECONDS
        return _MockResponse(
            {
                "scannedAt": "2026-07-01T12:00:00Z",
                "cards": [
                    {
                        "id": "card-1",
                        "title": "Tighten route test",
                        "lane": "Now",
                        "status": "open",
                        "path": "Projects/Dev-Flow/route.md",
                        "projectLink": "[[Dev-Flow]]",
                        "summary": "Backend slice",
                        "why": "Needed for integration",
                        "evidence": "Plan says proxy first",
                        "decision": "Keep scope narrow",
                        "nextAction": "Write route test",
                        "confidence": 91,
                        "impact": 4,
                        "qualityFlags": ["missing-link"],
                        "sourceBadge": {"label": "Projects"},
                        "link": "obsidian://open?vault=Test&file=Projects%2FDev-Flow%2Froute.md",
                        "updatedAt": "2026-07-01T11:59:00Z",
                    },
                    {
                        "name": "Fallback card",
                        "bucket": "Signals",
                        "state": "queued",
                        "filePath": "Signals/fallback.md",
                        "program": "Operator Kit",
                        "next_action": "Review",
                        "confidenceScore": 77,
                        "impactLevel": 3,
                        "qualityFlags": ["stale"],
                    },
                ],
                "lanes": {
                    "now": [],
                    "projects": [
                        {
                            "id": "card-1",
                            "title": "Tighten route test",
                            "lane": "Now",
                            "status": "open",
                            "path": "Projects/Dev-Flow/route.md",
                            "projectLink": "[[Dev-Flow]]",
                            "summary": "Backend slice",
                            "why": "Needed for integration",
                            "evidence": "Plan says proxy first",
                            "decision": "Keep scope narrow",
                            "nextAction": "Write route test",
                            "confidence": 91,
                            "impact": 4,
                            "qualityFlags": ["missing-link"],
                            "sourceBadge": {"label": "Projects"},
                            "link": "obsidian://open?vault=Test&file=Projects%2FDev-Flow%2Froute.md",
                            "updatedAt": "2026-07-01T11:59:00Z",
                        }
                    ],
                    "opportunities": [],
                    "inbox": [],
                    "handoffs": [],
                    "signals": [
                        {
                            "name": "Fallback card",
                            "bucket": "Signals",
                            "state": "queued",
                            "filePath": "Signals/fallback.md",
                            "program": "Operator Kit",
                            "next_action": "Review",
                            "confidenceScore": 77,
                            "impactLevel": 3,
                            "qualityFlags": ["stale"],
                        }
                    ],
                },
            }
        )

    monkeypatch.setattr(obsidian_cards.urllib.request, "urlopen", fake_urlopen)

    payload = obsidian_cards.fetch_obsidian_cards_payload()

    assert payload["ok"] is True
    assert payload["available"] is True
    assert payload["source"] == "command-center"
    assert payload["scannedAt"] == "2026-07-01T12:00:00Z"
    assert payload["lane_counts"] == {
        "now": 0,
        "projects": 1,
        "opportunities": 0,
        "inbox": 0,
        "handoffs": 0,
        "signals": 1,
    }
    assert list(payload["lanes"]) == ["now", "projects", "opportunities", "inbox", "handoffs", "signals"]
    assert payload["lanes"]["now"] == []
    assert payload["lanes"]["opportunities"] == []
    assert payload["lanes"]["inbox"] == []
    assert payload["lanes"]["handoffs"] == []

    assert payload["cards"][0] == {
        "id": "card-1",
        "title": "Tighten route test",
        "lane": "now",
        "status": "open",
        "source": "Projects",
        "path": "Projects/Dev-Flow/route.md",
        "project": "[[Dev-Flow]]",
        "summary": "Backend slice",
        "why": "Needed for integration",
        "evidence": "Plan says proxy first",
        "decision": "Keep scope narrow",
        "next_action": "Write route test",
        "confidence": 91,
        "impact": 4,
        "quality_flags": ["missing-link"],
        "link": "obsidian://open?vault=Test&file=Projects%2FDev-Flow%2Froute.md",
        "updated_at": "2026-07-01T11:59:00Z",
    }
    assert payload["cards"][1]["id"] == "signals-1"
    assert payload["cards"][1]["title"] == "Fallback card"
    assert payload["cards"][1]["lane"] == "signals"
    assert payload["cards"][1]["status"] == "queued"
    assert payload["cards"][1]["source"] == "Signals/fallback.md"
    assert payload["cards"][1]["path"] == "Signals/fallback.md"
    assert payload["cards"][1]["project"] == "Operator Kit"
    assert payload["cards"][1]["next_action"] == "Review"
    assert payload["cards"][1]["confidence"] == 77
    assert payload["cards"][1]["impact"] == 3
    assert payload["cards"][1]["quality_flags"] == ["stale"]
    assert payload["lanes"]["projects"][0]["id"] == "card-1"
    assert payload["lanes"]["projects"][0]["lane"] == "now"
    assert payload["lanes"]["signals"][0]["id"] == "signals-0"
    assert payload["lanes"]["signals"][0]["lane"] == "signals"


def test_fetch_obsidian_cards_payload_returns_unavailable_when_source_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: object, timeout: float | None = None) -> object:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(obsidian_cards.urllib.request, "urlopen", fake_urlopen)

    payload = obsidian_cards.fetch_obsidian_cards_payload()

    assert payload == {
        "ok": False,
        "available": False,
        "source": "command-center",
        "scannedAt": None,
        "cards": [],
        "lanes": {},
        "lane_counts": {},
        "error": "command-center unavailable: <urlopen error connection refused>",
    }


def test_fetch_obsidian_cards_payload_returns_unavailable_for_bad_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BadJsonResponse:
        status = 200

        def read(self) -> bytes:
            return b"{bad json"

        def __enter__(self) -> "_BadJsonResponse":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    monkeypatch.setattr(obsidian_cards.urllib.request, "urlopen", lambda request, timeout=None: _BadJsonResponse())

    payload = obsidian_cards.fetch_obsidian_cards_payload()

    assert payload["ok"] is False
    assert payload["available"] is False
    assert payload["cards"] == []
    assert payload["lanes"] == {}
    assert payload["lane_counts"] == {}
    assert payload["error"].startswith("command-center returned invalid JSON:")


def test_fetch_obsidian_cards_payload_groups_cards_when_upstream_lanes_are_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        obsidian_cards.urllib.request,
        "urlopen",
        lambda request, timeout=None: _MockResponse(
            {
                "scannedAt": "2026-07-01T12:00:00Z",
                "cards": [
                    {"id": "a", "title": "A", "lane": "Now"},
                    {"id": "b", "title": "B", "lane": "Inbox"},
                ],
                "lanes": ["bad"],
            }
        ),
    )

    payload = obsidian_cards.fetch_obsidian_cards_payload()

    assert payload["cards"][0]["id"] == "a"
    assert payload["cards"][1]["id"] == "b"
    assert list(payload["lanes"]) == ["now", "inbox"]
    assert payload["lane_counts"] == {"now": 1, "inbox": 1}


def test_fetch_obsidian_cards_payload_blank_or_malformed_override_uses_standard_unavailable_handling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_urlopen(request: object, timeout: float | None = None) -> _MockResponse:
        calls.append(request.full_url)
        return _MockResponse({"cards": [], "lanes": {}})

    monkeypatch.setenv("DEVFLOW_OBSIDIAN_CARDS_URL", "")
    monkeypatch.setattr(obsidian_cards.urllib.request, "urlopen", fake_urlopen)

    payload = obsidian_cards.fetch_obsidian_cards_payload()

    assert payload["ok"] is True
    assert calls == [obsidian_cards.DEFAULT_OBSIDIAN_CARDS_URL]

    monkeypatch.setenv("DEVFLOW_OBSIDIAN_CARDS_URL", "http://[bad")
    monkeypatch.setattr(
        obsidian_cards.urllib.request,
        "urlopen",
        lambda request, timeout=None: (_ for _ in ()).throw(ValueError("Invalid IPv6 URL")),
    )

    payload = obsidian_cards.fetch_obsidian_cards_payload()

    assert payload == {
        "ok": False,
        "available": False,
        "source": "command-center",
        "scannedAt": None,
        "cards": [],
        "lanes": {},
        "lane_counts": {},
        "error": "command-center unavailable: Invalid IPv6 URL",
    }
