"""Tests for brief_intelligence.parser.parse_markdown."""
from __future__ import annotations

import unittest

from brief_intelligence.parser import parse_markdown


class TestParseMarkdown(unittest.TestCase):
    def test_extracts_wikilinks_with_heading_title(self):
        md = (
            "# Daily AI Brief\n\n"
            "## Models\n"
            "New release from [[DevFlow]] team.\n"
            "Also see [[Hermes Agent|Hermes]] for orchestration.\n"
        )
        items = parse_markdown(md, source_file="brief.md")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].wikilink, "DevFlow")
        self.assertEqual(items[0].title, "Models")
        # alias: wikilink is the TARGET (before the pipe), not display text
        self.assertEqual(items[1].wikilink, "Hermes Agent")
        self.assertEqual(items[1].title, "Models")

    def test_no_wikilinks_returns_empty(self):
        self.assertEqual(parse_markdown("Just prose, no links."), [])


if __name__ == "__main__":
    unittest.main()
