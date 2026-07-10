"""Tests for brief_intelligence.loader.load_briefs."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from brief_intelligence.loader import load_briefs


class TestLoadBriefs(unittest.TestCase):
    def test_overlapping_wikilinks_deduplicated(self):
        md_a = (
            "# Brief A\n\n## AI/LLMs\n"
            "- [[AI/LLMs]] — Shared item from A\n"
            "- [[Unique A]] — Unique to A\n"
        )
        md_b = (
            "# Brief B\n\n## AI/LLMs\n"
            "- [[AI/LLMs]] — Shared item from B\n"
            "- [[Unique B]] — Unique to B\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = Path(tmpdir)
            (ref / "brief_a.md").write_text(md_a, encoding="utf-8")
            (ref / "brief_b.md").write_text(md_b, encoding="utf-8")
            items = load_briefs(ref)
            wikilinks = [i.wikilink for i in items]
            self.assertEqual(len(wikilinks), 3)
            self.assertEqual(wikilinks.count("AI/LLMs"), 1)
            self.assertIn("Unique A", wikilinks)
            self.assertIn("Unique B", wikilinks)


if __name__ == "__main__":
    unittest.main()
