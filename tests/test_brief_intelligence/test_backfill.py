"""Tests for brief_intelligence.main.run_backfill."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from brief_intelligence.main import run_backfill


class TestBackfill(unittest.TestCase):
    def test_backfill_processes_all_briefs(self):
        md_a = (
            "# Brief A\n\n## AI/LLMs\n"
            "- [[AI/LLMs]] — Item from A\n"
            "- [[Unique A]] — Unique to A\n"
        )
        md_b = (
            "# Brief B\n\n## AI/LLMs\n"
            "- [[AI/LLMs]] — Item from B\n"
            "- [[Unique B]] — Unique to B\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = Path(tmpdir)
            (ref / "brief_a.md").write_text(md_a, encoding="utf-8")
            (ref / "brief_b.md").write_text(md_b, encoding="utf-8")
            out_note = ref / "output.md"
            queue_path = ref / "queue.md"
            result = run_backfill(ref, out_note, queue_path, offline=True)
            # Should process both briefs
            self.assertEqual(result["total"], 3)  # AI/LLMs deduplicated, Unique A, Unique B
            self.assertTrue(out_note.exists())
            self.assertTrue(queue_path.exists())

    def test_backfill_creates_output_files(self):
        md = "# Brief\n\n## Test\n- [[Test Item]] — Test\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = Path(tmpdir)
            (ref / "brief.md").write_text(md, encoding="utf-8")
            out_note = ref / "output.md"
            queue_path = ref / "queue.md"
            result = run_backfill(ref, out_note, queue_path, offline=True)
            self.assertTrue(out_note.exists())
            self.assertTrue(queue_path.exists())
            # Check output contains wikilink
            content = out_note.read_text(encoding="utf-8")
            self.assertIn("[[Test Item]]", content)


if __name__ == "__main__":
    unittest.main()
