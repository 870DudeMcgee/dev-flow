"""Tests for brief_intelligence.dedup.deduplicate_items."""
from __future__ import annotations

import unittest

from brief_intelligence.dedup import deduplicate_items
from brief_intelligence.models import Item


class TestDeduplicateItems(unittest.TestCase):
    def test_duplicate_wikilink_removed_and_order_preserved(self):
        a = Item(id="1", title="LLMs", wikilink="AI/LLMs", snippet="x", source_file="a.md")
        b = Item(id="2", title="Vision", wikilink="AI/Vision", snippet="x", source_file="a.md")
        a_dup = Item(id="3", title="LLMs dup", wikilink="AI/LLMs", snippet="x", source_file="b.md")
        result = deduplicate_items([a, b, a_dup])
        self.assertEqual(len(result), 2)
        self.assertEqual([i.wikilink for i in result], ["AI/LLMs", "AI/Vision"])
        # first occurrence kept
        self.assertEqual(result[0].source_file, "a.md")

    def test_exact_match_only(self):
        # different case / different link is NOT a duplicate
        items = [
            Item(id="1", title="t", wikilink="Foo", snippet="x", source_file="a.md"),
            Item(id="2", title="t", wikilink="foo", snippet="x", source_file="b.md"),
        ]
        self.assertEqual(len(deduplicate_items(items)), 2)


if __name__ == "__main__":
    unittest.main()
