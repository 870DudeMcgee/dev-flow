from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any


DEFAULT_OBSIDIAN_CARDS_URL = "http://127.0.0.1:5173/api/cards"
OBSIDIAN_CARDS_TIMEOUT_SECONDS = 2.0


def fetch_obsidian_cards_payload() -> dict[str, Any]:
    url = os.environ.get("DEVFLOW_OBSIDIAN_CARDS_URL") or DEFAULT_OBSIDIAN_CARDS_URL
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=OBSIDIAN_CARDS_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return _empty_payload(error=f"command-center returned HTTP {exc.code}")
    except json.JSONDecodeError as exc:
        return _empty_payload(error=f"command-center returned invalid JSON: {exc}")
    except ValueError as exc:
        return _empty_payload(error=f"command-center unavailable: {exc}")
    except (urllib.error.URLError, OSError) as exc:
        return _empty_payload(error=f"command-center unavailable: {exc}")

    if isinstance(payload, list):
        raw_cards = payload
        scanned_at = None
        raw_lanes = None
    elif isinstance(payload, dict):
        raw_cards = payload.get("cards")
        scanned_at = _string_or_none(payload.get("scannedAt"))
        raw_lanes = payload.get("lanes")
    else:
        return _empty_payload(error="command-center returned an unsupported payload")

    if not isinstance(raw_cards, list):
        return _empty_payload(error="command-center payload is missing a cards list")

    cards = [_normalize_card(card, index=index) for index, card in enumerate(raw_cards) if isinstance(card, dict)]
    lanes = _normalize_upstream_lanes(raw_lanes)
    if lanes is None:
        lanes = _group_cards_by_lane(cards)
    lane_counts = {lane: len(items) for lane, items in lanes.items()}
    return {
        "ok": True,
        "available": True,
        "source": "command-center",
        "scannedAt": scanned_at,
        "cards": cards,
        "lanes": dict(lanes),
        "lane_counts": lane_counts,
        "error": None,
    }


def _empty_payload(*, error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "available": False,
        "source": "command-center",
        "scannedAt": None,
        "cards": [],
        "lanes": {},
        "lane_counts": {},
        "error": error,
    }


def _normalize_card(card: dict[str, Any], *, index: int) -> dict[str, Any]:
    lane = _normalize_lane(card.get("lane") or card.get("bucket") or card.get("group") or card.get("column"))
    quality_flags = card.get("qualityFlags")
    if not isinstance(quality_flags, list):
        quality_flags = []
    path = _string_or_none(card.get("path") or card.get("filePath"))
    source_badge = card.get("sourceBadge")
    source = None
    if isinstance(source_badge, dict):
        source = _string_or_none(source_badge.get("label") or source_badge.get("notePath"))
    if source is None:
        source = _string_or_none(card.get("source"))
    if source is None:
        source = path
    return {
        "id": _string_or_none(card.get("id")) or f"{lane}-{index}",
        "title": _string_or_none(card.get("title") or card.get("name") or card.get("summary")) or "Untitled",
        "lane": lane,
        "status": _string_or_none(card.get("status") or card.get("state")) or "open",
        "source": source,
        "path": path,
        "project": _string_or_none(card.get("projectLink") or card.get("project") or card.get("program") or card.get("area")),
        "summary": _string_or_none(card.get("summary") or card.get("subtitle") or card.get("description")),
        "why": _string_or_none(card.get("why") or card.get("localImpact") or card.get("impactText")),
        "evidence": _string_or_none(card.get("evidence")),
        "decision": _string_or_none(card.get("decision")),
        "next_action": _string_or_none(card.get("next_action") or card.get("nextAction") or card.get("next") or card.get("followUp")),
        "confidence": _number_or_none(
            card.get("confidence"),
            card.get("confidenceScore"),
            card.get("score"),
        ),
        "impact": _number_or_none(
            card.get("impact"),
            card.get("impactScore"),
            card.get("impactLevel"),
            card.get("priority"),
        ),
        "quality_flags": [str(value) for value in quality_flags if value is not None],
        "link": _string_or_none(card.get("link") or card.get("url") or card.get("href")),
        "updated_at": _string_or_none(card.get("updatedAt") or card.get("updated_at") or card.get("createdAt")),
    }


def _normalize_upstream_lanes(value: Any) -> dict[str, list[dict[str, Any]]] | None:
    if not isinstance(value, dict):
        return None
    lanes: dict[str, list[dict[str, Any]]] = {}
    for raw_lane, raw_cards in value.items():
        lane = _normalize_lane(raw_lane)
        if not isinstance(raw_cards, list):
            lanes[lane] = []
            continue
        lanes[lane] = [
            _normalize_card(card, index=index)
            for index, card in enumerate(raw_cards)
            if isinstance(card, dict)
        ]
    return lanes


def _group_cards_by_lane(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    lanes: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        lanes[card["lane"]].append(card)
    return dict(lanes)


def _normalize_lane(value: Any) -> str:
    lane = _string_or_none(value)
    if lane is None:
        return "now"
    return lane.strip().lower() or "now"


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number_or_none(*values: Any) -> int | float | None:
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None
