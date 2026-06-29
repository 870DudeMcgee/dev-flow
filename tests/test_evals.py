import unittest
import tempfile
import os
import shutil
import json
from unittest.mock import patch
from devflow.evals import run_role_eval, compare_prompts
from tests.helpers import git_commit, git_init

class TestEvals(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmpdir)

        # Create .devflow tree
        os.makedirs(".devflow/evals/fixtures")
        os.makedirs(".devflow/logs/traces")

        # Create mock source/test workspace files
        os.makedirs("src")
        with open("src/greeting.txt", "w", encoding="utf-8") as f:
            f.write("hello\n")
        
        git_init(os.getcwd())
        git_commit(os.getcwd(), message="init")

        # Create a mock implementer fixture
        self.fixture_data = {
            "name": "mock_implementer_test",
            "role": "implementer",
            "task_markdown": "# Task: 001 - Update Greeting\nStatus: PENDING\nGoal: goal-1\nPlan: plan-1.json\nAssigned Agent: local_ollama\nOwner Lock: vscode-copilot\nRisk: LOW\nBranch: devflow/task-001\nTouched Files:\n- src/greeting.txt\n\n## 2. Allowed Files\n- src/greeting.txt\n\n## 7. Verification Commands\n- true\n\n## 9. Execution Results\nPending.\n",
            "mock_model_response": "{\n  \"status\": \"ready\",\n  \"diff\": \"```diff\\ndiff --git a/src/greeting.txt b/src/greeting.txt\\n--- a/src/greeting.txt\\n+++ b/src/greeting.txt\\n@@ -1 +1 @@\\n-hello\\n+hello world\\n```\",\n  \"touched_paths\": [\"src/greeting.txt\"],\n  \"risk\": \"low\",\n  \"confidence\": 1.0\n}",
            "assertions": {
                "expected_status": "ready",
                "must_touch_files": ["src/greeting.txt"]
            }
        }
        with open(".devflow/evals/fixtures/mock_impl.json", "w", encoding="utf-8") as f:
            json.dump(self.fixture_data, f)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmpdir)

    @patch("devflow.agents.runner.ollama.invoke_local_model")
    @patch("devflow._legacy.agents.runner.ollama.invoke_local_model")
    @patch("devflow.agents.ollama.invoke_local_model")
    def test_run_role_eval_success(self, mock_invoke, mock_legacy_runner_invoke, mock_runner_invoke):
        # Mock LLM to return the fixture's pre-seeded output
        mock_invoke.return_value = self.fixture_data["mock_model_response"]
        mock_legacy_runner_invoke.return_value = self.fixture_data["mock_model_response"]
        mock_runner_invoke.return_value = self.fixture_data["mock_model_response"]

        # Run implementer evaluations
        results = run_role_eval("implementer", root_dir=self.tmpdir)

        self.assertEqual(results["total"], 1)
        self.assertEqual(results["passed"], 1)
        self.assertEqual(len(results["failures"]), 0)

        from devflow.artifacts import list_artifacts
        artifacts = list_artifacts("001", root=os.path.join(self.tmpdir, ".devflow", "artifacts"))
        self.assertTrue(len(artifacts) > 0)
        self.assertEqual(artifacts[-1].metadata.get("artifact_type"), "diff_result.json")

    @patch("devflow.agents.runner.ollama.invoke_local_model")
    @patch("devflow._legacy.agents.runner.ollama.invoke_local_model")
    @patch("devflow.agents.ollama.invoke_local_model")
    def test_run_role_eval_failure_assertion(self, mock_invoke, mock_legacy_runner_invoke, mock_runner_invoke):
        # Change assertion to expect COMPLETED instead of PREVIEWED (which will fail because it's a dry-run)
        self.fixture_data["assertions"]["expected_status"] = "COMPLETED"
        with open(".devflow/evals/fixtures/mock_impl.json", "w", encoding="utf-8") as f:
            json.dump(self.fixture_data, f)

        mock_invoke.return_value = self.fixture_data["mock_model_response"]
        mock_legacy_runner_invoke.return_value = self.fixture_data["mock_model_response"]
        mock_runner_invoke.return_value = self.fixture_data["mock_model_response"]

        results = run_role_eval("implementer", root_dir=self.tmpdir)

        self.assertEqual(results["total"], 1)
        self.assertEqual(results["passed"], 0)
        self.assertEqual(len(results["failures"]), 1)
        self.assertIn("expected status 'COMPLETED' but got 'ready'", results["failures"][0]["message"])

    def test_compare_prompts(self):
        res = compare_prompts("Prompt Version A", "Prompt Version B")
        self.assertIn("Prompt Version A", res["prompt_a"])
        self.assertIn("Prompt Version B", res["prompt_b"])
        self.assertGreater(res["metrics"]["prompt_a"]["tokens"], 0)
        self.assertGreater(res["metrics"]["prompt_b"]["tokens"], 0)

if __name__ == "__main__":
    unittest.main()
