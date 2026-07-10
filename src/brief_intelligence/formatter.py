"""Render scored items as a clean Obsidian markdown note."""
from __future__ import annotations

from .models import Item


def format_obsidian(items: list[Item], *, title: str = "AI Brief Intelligence") -> str:
    """Render items grouped by tier into an Obsidian note.

    Each item line: `- [[wikilink]] — reason (source: source_file)`.
    Items whose tier is not High/Medium/Low fall under Low.
    """
    high: list[Item] = []
    medium: list[Item] = []
    low: list[Item] = []
    for item in items:
        tier = getattr(item, "tier", "Low")
        if tier == "High":
            high.append(item)
        elif tier == "Medium":
            medium.append(item)
        else:
            low.append(item)

    lines: list[str] = [f"# {title}", "", "## High", ""]
    for item in high:
        lines.append(f"- [[{item.wikilink}]] — {item.reason} (source: {item.source_file})")
    lines.append("")
    lines.append("## Medium")
    lines.append("")
    for item in medium:
        lines.append(f"- [[{item.wikilink}]] — {item.reason} (source: {item.source_file})")
    lines.append("")
    lines.append("## Low")
    lines.append("")
    for item in low:
        lines.append(f"- [[{item.wikilink}]] — {item.reason} (source: {item.source_file})")
    lines.append("")
    return "\n".join(lines)
