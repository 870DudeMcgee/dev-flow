import os
import unittest


class TestWorkflowOrchestrationDocs(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.source_path = os.path.join(self.base_dir, "docs", "DEVFLOW_SOURCE_OF_TRUTH.md")

    def test_active_design_docs_exist(self):
        expected_files = [
            os.path.join("docs", "DEVFLOW_SOURCE_OF_TRUTH.md"),
            os.path.join("docs", "README.md"),
            os.path.join("docs", "_quarantine_2026-07-07", "README.md"),
        ]
        for f in expected_files:
            full_path = os.path.join(self.base_dir, f)
            self.assertTrue(os.path.isfile(full_path), f"File {f} does not exist at {full_path}")

    def test_old_design_docs_are_quarantined(self):
        quarantined = [
            os.path.join("docs", "_quarantine_2026-07-07", "workflow-preview.md"),
            os.path.join(
                "docs",
                "_quarantine_2026-07-07",
                "architecture",
                "agent-registry-and-" + "adapter-runtime.md",
            ),
            os.path.join("docs", "_quarantine_2026-07-07", "dynamic-worker-orchestration.md"),
        ]
        for f in quarantined:
            full_path = os.path.join(self.base_dir, f)
            self.assertTrue(os.path.isfile(full_path), f"Quarantined file {f} does not exist at {full_path}")

    def test_source_of_truth_contains_workflow_contract(self):
        with open(self.source_path, "r", encoding="utf-8") as f:
            content = f.read().lower()

        required_mentions = [
            "brainstorm",
            "spec loop",
            "planning loop",
            "planning judge",
            "orchestrator",
            "builder/judge execution",
            "evidence-backed next action",
            "human approval points",
        ]
        for term in required_mentions:
            self.assertIn(term, content, f"source of truth does not mention: '{term}'")

    def test_no_claims_of_current_runtime_implementation(self):
        with open(self.source_path, "r", encoding="utf-8") as file_obj:
            content = file_obj.read().lower()
        forbidden_phrases = [
            "currently implements dynamic orchestration",
            "automatically creates workers today",
            "automatically promotes",
            "workers merge directly to main",
        ]
        for phrase in forbidden_phrases:
            self.assertNotIn(phrase, content, f"Forbidden phrase '{phrase}' found in source of truth")


if __name__ == "__main__":
    unittest.main()
