import os
import unittest

class TestWorkflowOrchestrationDocs(unittest.TestCase):
    def setUp(self):
        # Base directory of the repository
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_design_docs_exist(self):
        expected_files = [
            os.path.join("docs", "workflow-preview.md"),
            os.path.join("docs", "worker-permission-modes.md"),
            os.path.join("docs", "dynamic-worker-orchestration.md")
        ]
        for f in expected_files:
            full_path = os.path.join(self.base_dir, f)
            self.assertTrue(os.path.isfile(full_path), f"File {f} does not exist at {full_path}")

    def test_active_source_docs_link_them(self):
        active_docs = [
            "README.md",
            "PRODUCT_NORTH_STAR.md",
            os.path.join("docs", "devflow-operating-model.md"),
            os.path.join("docs", "roadmap.md"),
            os.path.join("docs", "control-room-mvp.md")
        ]
        
        design_files = [
            "workflow-preview.md",
            "worker-permission-modes.md",
            "dynamic-worker-orchestration.md"
        ]
        
        # We need to find at least one active source doc linking each design doc.
        for df in design_files:
            linked = False
            for src in active_docs:
                full_src_path = os.path.join(self.base_dir, src)
                if os.path.isfile(full_src_path):
                    with open(full_src_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if df in content:
                        linked = True
                        break
            self.assertTrue(linked, f"Design doc {df} is not linked from any active source docs: {active_docs}")

    def test_workflow_preview_content(self):
        path = os.path.join(self.base_dir, "docs", "workflow-preview.md")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().lower()
        
        required_mentions = [
            "preview",
            "human approval",
            "verification",
            "workspace"
        ]
        for term in required_mentions:
            self.assertIn(term, content, f"docs/workflow-preview.md does not mention: '{term}'")

    def test_worker_permission_modes_content(self):
        path = os.path.join(self.base_dir, "docs", "worker-permission-modes.md")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().lower()

        required_mentions = [
            "read_only",
            "workspace_write",
            "verify_only",
            "promotion_candidate",
            "human approval"
        ]
        for term in required_mentions:
            self.assertIn(term, content, f"docs/worker-permission-modes.md does not mention: '{term}'")

    def test_dynamic_worker_orchestration_content(self):
        path = os.path.join(self.base_dir, "docs", "dynamic-worker-orchestration.md")
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().lower()

        required_mentions = [
            "local state",
            "replaceable workers",
            "human approval",
            "no automatic promotion"
        ]
        for term in required_mentions:
            self.assertIn(term, content, f"docs/dynamic-worker-orchestration.md does not mention: '{term}'")

    def test_no_claims_of_current_runtime_implementation(self):
        design_files = [
            os.path.join("docs", "workflow-preview.md"),
            os.path.join("docs", "worker-permission-modes.md"),
            os.path.join("docs", "dynamic-worker-orchestration.md")
        ]
        
        forbidden_phrases = [
            "currently implements dynamic orchestration",
            "automatically creates workers today",
            "automatically promotes",
            "workers merge directly to main"
        ]
        
        for f in design_files:
            full_path = os.path.join(self.base_dir, f)
            with open(full_path, "r", encoding="utf-8") as file_obj:
                content = file_obj.read().lower()
            for phrase in forbidden_phrases:
                self.assertNotIn(phrase, content, f"Forbidden phrase '{phrase}' found in {f}")

if __name__ == "__main__":
    unittest.main()
