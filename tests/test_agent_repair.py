import unittest
import os
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from devflow.cli import init_workspace
from devflow.repo_map import refresh_repo_maps
from devflow.agents.runner import run_repair_agent
from devflow.artifacts import read_artifact

class TestAgentRepairRunner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)
        os.system("git init > /dev/null 2>&1")
        os.system("git config user.email 'tests@example.com'")
        os.system("git config user.name 'Devflow Tests'")
        init_workspace()
        
        # Configure test task with verification command
        self.task_path = ".devflow/tasks/003_repair.md"
        with open(self.task_path, "w", encoding="utf-8") as f:
            f.write("""# Task: 003 - Repair Task
Status: PENDING
Touched Files:
- target.py
## 1. Objective
Repair target.
## 2. Allowed Files
- target.py
## 7. Verification Commands
- python3 test_target.py
## 9. Execution Results
```diff
diff --git a/target.py b/target.py
--- a/target.py
+++ b/target.py
@@ -1 +1 @@
-def foo(): pass
+def foo(): syntax_error_here
```
""")
        with open("target.py", "w", encoding="utf-8") as f:
             f.write("def foo(): pass\n")
        with open("test_target.py", "w", encoding="utf-8") as f:
             f.write("import target\ntarget.foo()\n")
             
        os.system("git add . > /dev/null 2>&1")
        os.system("git commit -m 'init' > /dev/null 2>&1")
        refresh_repo_maps()
        os.system("git add . > /dev/null 2>&1")
        os.system("git commit -m 'commit maps' > /dev/null 2>&1")


    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    @patch("devflow.agents.ollama.urllib.request.urlopen")
    def test_run_repair_agent_success_on_retry(self, mock_urlopen):
        # Loop 0 will fail with SyntaxError (since we wrote def foo(): syntax_error_here).
        # We mock Ollama returning a working diff for Loop 1.
        mock_response = MagicMock()
        response_dict = {
            "response": json.dumps({
                "status": "ready",
                "diff": "diff --git a/target.py b/target.py\n--- a/target.py\n+++ b/target.py\n@@ -1 +1,2 @@\n-def foo(): pass\n+def foo():\n+    return 1\n",
                "touched_paths": ["target.py"],
                "risk": "low",
                "confidence": 0.95
            })
        }
        mock_response.__iter__.return_value = [json.dumps(response_dict).encode("utf-8")]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        record = run_repair_agent(self.task_path, max_loops=2)
        self.assertIsNotNone(record)
        _, body = read_artifact(record.metadata_path)
        result = json.loads(body)
        self.assertEqual(result["status"], "ready")
        self.assertIn("return 1", result["diff"])

    @patch("devflow.agents.ollama.urllib.request.urlopen")
    def test_run_repair_agent_budget_exhausted(self, mock_urlopen):
        # We mock Ollama continuously returning a failing diff
        mock_response = MagicMock()
        response_dict = {
            "response": json.dumps({
                "status": "ready",
                "diff": "diff --git a/target.py b/target.py\n--- a/target.py\n+++ b/target.py\n@@ -1 +1 @@\n-def foo(): pass\n+def foo(): syntax_error_still\n",
                "touched_paths": ["target.py"],
                "risk": "low",
                "confidence": 0.95
            })
        }
        mock_response.__iter__.return_value = [json.dumps(response_dict).encode("utf-8")]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        record = run_repair_agent(self.task_path, max_loops=2)
        self.assertIsNotNone(record)
        _, body = read_artifact(record.metadata_path)
        result = json.loads(body)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("budget exhausted", result["blocked_reason"])

    @patch("devflow.agents.ollama.urllib.request.urlopen")
    def test_run_repair_agent_blocked_by_safety(self, mock_urlopen):
        # We mock Ollama returning a diff containing a secret hazard
        mock_response = MagicMock()
        response_dict = {
            "response": json.dumps({
                "status": "ready",
                "diff": "diff --git b/target.py a/target.py\n--- a/target.py\n+++ b/target.py\n@@ -1 +1 @@\n-def foo(): pass\n+SECRET_KEY = 'secret-token-123'\n",
                "touched_paths": ["target.py"],
                "risk": "low",
                "confidence": 0.95
            })
        }
        mock_response.__iter__.return_value = [json.dumps(response_dict).encode("utf-8")]
        mock_urlopen.return_value.__enter__.return_value = mock_response

        record = run_repair_agent(self.task_path, max_loops=2)
        self.assertIsNotNone(record)
        _, body = read_artifact(record.metadata_path)
        result = json.loads(body)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Safety hazards detected", result["blocked_reason"])


