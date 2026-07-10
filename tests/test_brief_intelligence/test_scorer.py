"""Tests for brief_intelligence.scorer (no live model — inject fake scorer)."""
from __future__ import annotations

import unittest

from brief_intelligence.models import Item
from brief_intelligence.scorer import score_item, score_items


def fake_scorer(prompt: str) -> str:
    # Deterministic fake Hermes: always returns High with a fixed reason.
    return '{"score": 0.9, "tier": "High", "reason": "fake-reason"}'


class TestScorer(unittest.TestCase):
    def test_score_item_uses_injected_scorer(self):
        item = Item(id="1", title="T", wikilink="Foo", snippet="x", source_file="a.md")
        result = score_item(item, scorer=fake_scorer)
        self.assertEqual(result["tier"], "High")
        self.assertEqual(result["reason"], "fake-reason")

    def test_score_items_mutates_tier(self):
        items = [
            Item(id="1", title="T", wikilink="Foo", snippet="x", source_file="a.md"),
            Item(id="2", title="T", wikilink="Bar", snippet="x", source_file="b.md"),
        ]
        score_items(items, scorer=fake_scorer)
        self.assertTrue(all(i.tier == "High" for i in items))

    def test_parse_handles_surrounding_text(self):
        item = Item(id="1", title="T", wikilink="Foo", snippet="x", source_file="a.md")
        # model wrapped JSON in prose
        out = score_item(item, scorer=lambda p: 'Here:\n{"score": 0.2, "tier": "Low", "reason": "r"}\nDone')
        self.assertEqual(out["tier"], "Low")


if __name__ == "__main__":
    unittest.main()
