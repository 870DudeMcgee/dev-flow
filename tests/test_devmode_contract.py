import os
import unittest


class TestDevFlowSourceOfTruth(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.source_path = os.path.join(self.base_dir, "docs", "DEVFLOW_SOURCE_OF_TRUTH.md")

    def test_files_exist(self):
        expected_files = [
            os.path.join("docs", "DEVFLOW_SOURCE_OF_TRUTH.md"),
            os.path.join("docs", "README.md"),
            "README.md",
            "AGENTS.md",
            os.path.join("skills", "using-devmode", "SKILL.md"),
        ]
        for f in expected_files:
            full_path = os.path.join(self.base_dir, f)
            self.assertTrue(os.path.isfile(full_path), f"File {f} does not exist at {full_path}")

    def test_readme_links_to_source_of_truth(self):
        readme_path = os.path.join(self.base_dir, "README.md")
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("docs/DEVFLOW_SOURCE_OF_TRUTH.md", content)

    def test_agents_mentions_source_of_truth_or_devflow_docs(self):
        agents_path = os.path.join(self.base_dir, "AGENTS.md")
        with open(agents_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertTrue(
            "docs/DEVFLOW_SOURCE_OF_TRUTH.md" in content
            or "DevFlow" in content
            or "Dev-Flow" in content
        )

    def test_source_of_truth_mentions_stage_gates(self):
        with open(self.source_path, "r", encoding="utf-8") as f:
            content = f.read()
        stages = [
            "Brainstorm",
            "Spec Loop",
            "Planning Loop",
            "Planning Judge",
            "Orchestrator",
            "Builder/Judge Execution",
            "Verification",
        ]
        for stage in stages:
            self.assertIn(stage, content, f"source of truth does not mention stage: {stage}")

    def test_source_of_truth_contains_judge_decisions(self):
        with open(self.source_path, "r", encoding="utf-8") as f:
            content = f.read()
        decisions = ["APPROVE", "REVISE", "BLOCK", "ESCALATE_TO_USER"]
        for decision in decisions:
            self.assertIn(decision, content, f"source of truth missing judge decision: {decision}")

    def test_unsafe_phrases_absent(self):
        unsafe_phrases = [
            "delete the non-compliant work",
            "override default system prompt",
            "override system prompt",
            "you do not have a choice",
        ]
        authority_files = [
            "README.md",
            "AGENTS.md",
            os.path.join("docs", "DEVFLOW_SOURCE_OF_TRUTH.md"),
            os.path.join("docs", "README.md"),
            os.path.join("skills", "using-devmode", "SKILL.md"),
        ]
        for f in authority_files:
            full_path = os.path.join(self.base_dir, f)
            with open(full_path, "r", encoding="utf-8") as file_obj:
                content = file_obj.read().lower()
            for phrase in unsafe_phrases:
                self.assertNotIn(phrase, content, f"Forbidden phrase '{phrase}' found in {f}")

    def test_source_of_truth_mentions_instruction_priority_boundary(self):
        with open(self.source_path, "r", encoding="utf-8") as f:
            content = f.read().lower()
        self.assertIn("source of truth", content)
        self.assertIn("non-authoritative", content)
        self.assertTrue("hermes" in content or "runtime" in content)


if __name__ == "__main__":
    unittest.main()
