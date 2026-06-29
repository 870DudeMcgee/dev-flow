import unittest
import os
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from devflow.cli import init_workspace
from devflow.repo_map import refresh_repo_maps
from devflow.agents.runner import run_implement_agent
from devflow.artifacts import read_artifact
from tests.helpers import git_commit, git_init

class TestAgentImplementRunner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)
        git_init(os.getcwd())
        init_workspace()
        os.makedirs("src/devflow", exist_ok=True)
        with open("src/devflow/target.py", "w", encoding="utf-8") as f:
            f.write("def foo(): pass")
        git_commit(os.getcwd(), message="init")
        refresh_repo_maps()
        
        self.task_path = ".devflow/tasks/002_implement.md"
        with open(self.task_path, "w", encoding="utf-8") as f:
            f.write("# Task: 002 - Implement\nStatus: PENDING\nTouched Files:\n- src/devflow/target.py\n## 1. Objective\nCode.")

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    @patch("devflow.agents.ollama.urllib.request.urlopen")
    def test_run_implement_agent_success(self, mock_urlopen):
        mock_response = MagicMock()
        response_dict = {
            "response": json.dumps({
                "status": "ready",
                "diff": "diff --git a/src/devflow/target.py b/src/devflow/target.py\n--- a/src/devflow/target.py\n+++ b/src/devflow/target.py\n@@ -1 +1 @@\n-def foo(): pass\n+def foo():\n+    print(1)",
                "touched_paths": ["src/devflow/target.py"],
                "risk": "low",
                "confidence": 0.9
            })
        }
        mock_response.__iter__.return_value = [json.dumps(response_dict).encode("utf-8")]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        record = run_implement_agent(self.task_path)
        self.assertIsNotNone(record)
        _, body = read_artifact(record.metadata_path)
        result = json.loads(body)
        self.assertEqual(result["status"], "ready")
        self.assertIn("print(1)", result["diff"])

    @patch("devflow.agents.ollama.urllib.request.urlopen")
    def test_run_implement_agent_safety_blocked(self, mock_urlopen):
        mock_response = MagicMock()
        response_dict = {
            "response": json.dumps({
                "status": "ready",
                "diff": "diff --git a/src/devflow/target.py b/src/devflow/target.py\n--- a/src/devflow/target.py\n+++ b/src/devflow/target.py\n@@ -1 +1 @@\n+SECRET_KEY = 'secret_token_123'",
                "touched_paths": ["src/devflow/target.py"],
                "risk": "low",
                "confidence": 0.9
            })
        }
        mock_response.read.return_value = json.dumps(response_dict).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        record = run_implement_agent(self.task_path)
        self.assertIsNotNone(record)
        _, body = read_artifact(record.metadata_path)
        result = json.loads(body)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("blocked", result["status"])

    @patch("devflow.agents.ollama.urllib.request.urlopen")
    def test_run_implement_agent_with_fallback(self, mock_urlopen):
        import urllib.error
        mock_response_fail = urllib.error.URLError("Connection refused")
        
        mock_response_ok = MagicMock()
        mock_response_ok.__enter__.return_value = mock_response_ok
        response_dict = {
            "response": json.dumps({
                "status": "ready",
                "diff": "diff --git a/src/devflow/target.py b/src/devflow/target.py\n--- a/src/devflow/target.py\n+++ b/src/devflow/target.py\n@@ -1 +1 @@\n-def foo(): pass\n+def foo():\n+    print(1)",
                "touched_paths": ["src/devflow/target.py"],
                "risk": "low",
                "confidence": 0.9
            })
        }
        mock_response_ok.__iter__.return_value = [json.dumps(response_dict).encode("utf-8")]
        
        mock_urlopen.side_effect = [mock_response_fail, mock_response_ok]
        
        record = run_implement_agent(self.task_path)
        self.assertIsNotNone(record)
        _, body = read_artifact(record.metadata_path)
        result = json.loads(body)
        self.assertEqual(result["status"], "ready")
        self.assertIn("print(1)", result["diff"])

    def test_implement_agent_system_instruction_contains_protocols(self):
        with patch("devflow.agents.runner.ollama.invoke_local_model") as mock_invoke:
            mock_invoke.return_value = json.dumps({
                "status": "ready",
                "diff": "",
                "touched_paths": [],
                "risk": "low",
                "confidence": 1.0
            })
            run_implement_agent(self.task_path)
            self.assertTrue(mock_invoke.called)
            system_instruction = mock_invoke.call_args[1]["system_instruction"]
            self.assertIn("=== WEB APP AESTHETICS & QUALITY PROTOCOLS ===", system_instruction)
            self.assertIn("=== CRITICAL UNIFIED DIFF PROTOCOLS ===", system_instruction)
            self.assertIn("DESIGN TOKENS", system_instruction)
            self.assertIn("STRUCTURAL INTEGRITY & TAG CLEANLINESS", system_instruction)

