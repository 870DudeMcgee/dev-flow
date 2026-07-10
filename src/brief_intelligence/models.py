"""Data models for the brief intelligence pipeline."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Item:
    """A single extracted brief item, with optional scoring metadata."""

    id: str
    title: str
    wikilink: str
    snippet: str
    source_file: str
    tier: str = "Low"
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "wikilink": self.wikilink,
            "snippet": self.snippet,
            "source_file": self.source_file,
            "tier": self.tier,
            "reason": self.reason,
        }
