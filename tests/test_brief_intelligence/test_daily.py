"""Tests for brief_intelligence.main.run_daily."""
from __future__ import annotations

import datetime
import tempfile
import unittest
from pathlib import Path

from brief_intelligence.main import run_daily


class TestDaily(unittest.TestCase):
    def test_daily_processes_only_todays_brief(self):
        today = datetime.date.today()
        date_str = today.strftime("%Y-%m-%d")
        md_today = (
            f"# Brief {date_str}\n\n## AI/LLMs\n"
            "- [[AI/LLMs]] — Today's item\n"
            "- [[Today Unique]] — Unique to today\n"
        )
        md_other = (
            "# Brief 2024-01-01\n\n## AI/LLMs\n"
            "- [[AI/LLMs]] — Old item\n"
            "- [[Old Unique]] — Unique to old\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = Path(tmpdir)
            (ref / f"brief_{date_str}.md").write_text(md_today, encoding="utf-8")
            (ref / "brief_2024-01-01.md").write_text(md_other, encoding="utf-8")
            out_note = ref / "output.md"
            queue_path = ref / "queue.md"
            result = run_daily(ref, out_note, queue_path, offline=True, today=today)
            # Should only process today's brief
            self.assertEqual(result["total"], 2)  # AI/LLMs and Today Unique
            content = out_note.read_text(encoding="utf-8")
            self.assertIn("[[Today Unique]]", content)
            self.assertNotIn("[[Old Unique]]", content)

    def test_daily_raises_if_no_todays_brief(self):
        today = datetime.date.today()
        with tempfile.TemporaryDirectory() as tmpdir:
            ref = Path(tmpdir)
            (ref / "brief_2024-01-01.md").write_text("# Old\n- [[Old]]\n", encoding="utf-8")
            out_note = ref / "output.md"
            queue_path = ref / "queue.md"
            with self.assertRaises(FileNotFoundError):
                run_daily(ref, out_note, queue_path, offline=True, today=today)


if __name__ == "__main__":
    unittest.main()
