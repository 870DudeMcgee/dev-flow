"""Deduplicate items by exact wikilink (stdlib only)."""
from __future__ import annotations

from .models import Item


def deduplicate_items(items: list[Item]) -> list[Item]:
    """Remove duplicate wikilinks, keep the FIRST occurrence, preserve order.

    Uses EXACT wikilink matching only — no semantic/ML similarity.
    """
    seen: set[str] = set()
    result: list[Item] = []
    for item in items:
        if item.wikilink in seen:
            continue
        seen.add(item.wikilink)
        result.append(item)
    return result
