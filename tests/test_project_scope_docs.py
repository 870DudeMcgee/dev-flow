import os
import unittest


class TestProjectScopeDocs(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.source_path = os.path.join(self.base_dir, "docs", "DEVFLOW_SOURCE_OF_TRUTH.md")

    def test_active_source_of_truth_exists(self):
        expected_files = [
            os.path.join("docs", "DEVFLOW_SOURCE_OF_TRUTH.md"),
            os.path.join("docs", "README.md"),
            os.path.join("docs", "_quarantine_2026-07-07", "README.md"),
        ]
        for f in expected_files:
            full_path = os.path.join(self.base_dir, f)
            self.assertTrue(os.path.isfile(full_path), f"File {f} does not exist at {full_path}")

    def test_readme_links_to_source_of_truth(self):
        readme_path = os.path.join(self.base_dir, "README.md")
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("docs/DEVFLOW_SOURCE_OF_TRUTH.md", content)
        self.assertIn("docs/_quarantine_2026-07-07/", content)

    def test_source_of_truth_defines_current_loop(self):
        with open(self.source_path, "r", encoding="utf-8") as f:
            content = f.read().lower()

        required_mentions = [
            "idea -> brainstorm -> spec -> plan -> judge -> build -> judge -> verify -> next human decision",
            "obsidian owns the broad data and knowledge layer",
            "devflow owns the active product-building loop",
            "orchestrator is a traffic controller",
            "builders execute small implementation tasks",
            "judges verify",
            "evidence-backed next action",
        ]
        for term in required_mentions:
            self.assertIn(term, content, f"source of truth does not mention: '{term}'")

    def test_source_of_truth_declares_old_docs_non_authoritative(self):
        with open(self.source_path, "r", encoding="utf-8") as f:
            content = f.read().lower()

        self.assertIn("non-authoritative", content)
        self.assertIn("must not be loaded as active context by default", content)
        self.assertIn("historical docs should be quarantined or deleted", content)

    def test_quarantine_readme_blocks_active_context_use(self):
        quarantine_path = os.path.join(self.base_dir, "docs", "_quarantine_2026-07-07", "README.md")
        with open(quarantine_path, "r", encoding="utf-8") as f:
            content = f.read().lower()

        self.assertIn("non-authoritative historical material", content)
        self.assertIn("do not load or follow anything in this folder", content)
        self.assertIn("recovery material only", content)


if __name__ == "__main__":
    unittest.main()
