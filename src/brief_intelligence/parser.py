"""Parse markdown briefs into structured Item objects."""
from __future__ import annotations

import re

from .models import Item

_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


def parse_markdown(content: str, source_file: str = "") -> list[Item]:
    """Extract [[wikilinks]] from markdown into Items.

    Each wikilink becomes one Item. For aliases ([[target|alias]]) the
    wikilink is the TARGET (before the pipe), not the display text.
    The title is the most recent heading seen before the wikilink.
    """
    items: list[Item] = []
    current_title = ""
    for idx, line in enumerate(content.splitlines(), start=1):
        heading = _HEADING_RE.match(line)
        if heading:
            current_title = heading.group(1).strip()
            continue
        for match in _WIKILINK_RE.finditer(line):
            raw = match.group(1).strip()
            target = raw.split("|", 1)[0].strip()  # target before pipe
            snippet = line.strip()[:200]
            items.append(
                Item(
                    id=f"{source_file or 'line'}-{idx}",
                    title=current_title or target,
                    wikilink=target,
                    snippet=snippet,
                    source_file=source_file,
                )
            )
    return items
