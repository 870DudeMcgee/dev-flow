"""Append High-tier items to a BrainstormQueue.md backlog."""
from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Union

from .models import Item


def _dedup_key(item: Item) -> str:
    """Stable deduplication key: normalized wikilink + source_file.

    Normalization lowercases, strips whitespace, and collapses internal
    whitespace so trivial variations don't produce duplicates.
    Timestamps and reasons are intentionally excluded.
    """
    wikilink = re.sub(r"\s+", "", (item.wikilink or "").lower().strip())
    source = (item.source_file or "").lower().strip()
    return f"{wikilink}|{source}"


def append_to_queue(
    high_items: list[Item],
    queue_path: Union[str, Path],
    *,
    now: datetime.datetime | None = None,
) -> int:
    """Append High-tier items to the queue file. Returns count appended.

    Each line: `- [timestamp] [[wikilink]] (source: source_file) — reason`.
    Creates the file (and parent dirs) if missing.
    Idempotent: items already present (by normalized wikilink + source) are
    skipped, so repeated runs with the same input produce zero new entries.
    """
    qpath = Path(queue_path)
    qpath.parent.mkdir(parents=True, exist_ok=True)
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    ts = now.strftime("%Y-%m-%d %H:%M UTC")

    # Read existing queue to build the dedup set
    existing_keys: set[str] = set()
    existing_text = ""
    if qpath.exists():
        existing_text = qpath.read_text(encoding="utf-8")
        # Extract [[wikilink]] and (source: ...) from each existing line
        for line in existing_text.splitlines():
            wl_match = re.search(r"\[\[(.+?)\]\]", line)
            src_match = re.search(r"\(source:\s*(.+?)\)", line)
            if wl_match and src_match:
                wl = re.sub(r"\s+", "", wl_match.group(1).lower().strip())
                src = src_match.group(1).lower().strip()
                existing_keys.add(f"{wl}|{src}")

    # Filter to High-tier items not already in the queue
    new_lines: list[str] = []
    for item in high_items:
        if getattr(item, "tier", "Low") != "High":
            continue
        key = _dedup_key(item)
        if key in existing_keys:
            continue
        existing_keys.add(key)  # prevent intra-run duplicates too
        new_lines.append(
            f"- [{ts}] [[{item.wikilink}]] (source: {item.source_file}) — {item.reason}"
        )
    if new_lines:
        if existing_text and not existing_text.endswith("\n"):
            existing_text += "\n"
        qpath.write_text(existing_text + "\n".join(new_lines) + "\n", encoding="utf-8")
    return len(new_lines)
