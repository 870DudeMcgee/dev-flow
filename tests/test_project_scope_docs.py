import os
import unittest

class TestProjectScopeDocs(unittest.TestCase):
    def setUp(self):
        # Base directory of the repository
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_files_exist(self):
        expected_files = [
            os.path.join("docs", "devflow-operating-model.md"),
            os.path.join("docs", "read-only-control-room-agent.md"),
            os.path.join("docs", "devmode-devflow-boundary.md")
        ]
        for f in expected_files:
            full_path = os.path.join(self.base_dir, f)
            self.assertTrue(os.path.isfile(full_path), f"File {f} does not exist at {full_path}")

    def test_readme_links_to_new_docs(self):
        readme_path = os.path.join(self.base_dir, "README.md")
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("docs/devflow-operating-model.md", content, "README.md does not link to docs/devflow-operating-model.md")
        self.assertIn("docs/read-only-control-room-agent.md", content, "README.md does not link to docs/read-only-control-room-agent.md")
        self.assertIn("docs/devmode-devflow-boundary.md", content, "README.md does not link to docs/devmode-devflow-boundary.md")

    def test_north_star_links_to_new_docs(self):
        north_star_path = os.path.join(self.base_dir, "PRODUCT_NORTH_STAR.md")
        with open(north_star_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("docs/devflow-operating-model.md", content, "PRODUCT_NORTH_STAR.md does not link to docs/devflow-operating-model.md")
        self.assertIn("docs/read-only-control-room-agent.md", content, "PRODUCT_NORTH_STAR.md does not link to docs/read-only-control-room-agent.md")
        self.assertIn("docs/devmode-devflow-boundary.md", content, "PRODUCT_NORTH_STAR.md does not link to docs/devmode-devflow-boundary.md")

    def test_operating_model_content(self):
        model_path = os.path.join(self.base_dir, "docs", "devflow-operating-model.md")
        with open(model_path, "r", encoding="utf-8") as f:
            content = f.read().lower()
        
        required_mentions = [
            "main chat",
            "read-only",
            "worker",
            "isolated workspace",
            "verification",
            "human-controlled promotion"
        ]
        for term in required_mentions:
            self.assertIn(term, content, f"docs/devflow-operating-model.md does not mention: '{term}'")

    def test_control_room_agent_forbidden_responsibilities(self):
        agent_path = os.path.join(self.base_dir, "docs", "read-only-control-room-agent.md")
        with open(agent_path, "r", encoding="utf-8") as f:
            content = f.read().lower()

        forbidden_responsibilities = [
            "editing",
            "staging",
            "committing",
            "pushing",
            "merging"
        ]
        for resp in forbidden_responsibilities:
            self.assertIn(resp, content, f"docs/read-only-control-room-agent.md does not mention forbidden responsibility: '{resp}'")

    def test_devmode_devflow_boundary_ownership(self):
        boundary_path = os.path.join(self.base_dir, "docs", "devmode-devflow-boundary.md")
        with open(boundary_path, "r", encoding="utf-8") as f:
            content = f.read().lower()

        # DevMode owns discipline, Dev-Flow owns state/orchestration
        self.assertIn("discipline", content, "docs/devmode-devflow-boundary.md does not mention DevMode owning discipline")
        self.assertTrue(
            "state" in content or "orchestration" in content,
            "docs/devmode-devflow-boundary.md does not mention Dev-Flow owning state or orchestration"
        )
        self.assertIn(
            "devmode tells agents how to behave",
            content,
            "docs/devmode-devflow-boundary.md is missing the core boundary sentence"
        )
        self.assertIn(
            "dev-flow gives agents safe places to work and records what happened",
            content,
            "docs/devmode-devflow-boundary.md is missing the core boundary sentence"
        )

if __name__ == "__main__":
    unittest.main()
