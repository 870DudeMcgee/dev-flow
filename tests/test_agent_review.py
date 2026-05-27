import unittest
import os
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from devflow.cli import init_workspace
from devflow.repo_map import refresh_repo_maps
from devflow.agents.runner import run_review_agent
from devflow.artifacts import list_artifacts, read_artifact

class TestAgentReviewRunner(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)
        os.system("git init > /dev/null 2>&1")
        os.system("git config user.email 'tests@example.com'")
        os.system("git config user.name 'Devflow Tests'")
        init_workspace()
        os.makedirs("src/devflow", exist_ok=True)
        with open("src/devflow/target.py", "w", encoding="utf-8") as f:
            f.write("def foo(): pass")
        os.system("git add . > /dev/null 2>&1")
        os.system("git commit -m 'init' > /dev/null 2>&1")
        refresh_repo_maps()
        
        self.task_path = ".devflow/tasks/001_review.md"
        with open(self.task_path, "w", encoding="utf-8") as f:
            f.write("# Task: 001 - Review\nStatus: PENDING\nTouched Files:\n- src/devflow/target.py\n## 1. Objective\nReview task.")

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    @patch("devflow.agents.ollama.urllib.request.urlopen")
    def test_run_review_agent_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.__iter__.return_value = [b'{"response": "{\\"status\\": \\"approved\\", \\"summary\\": \\"Code looks good\\", \\"findings\\": [], \\"required_actions\\": [], \\"confidence\\": 0.9}"}']
        mock_urlopen.return_value.__enter__.return_value = mock_response

        record = run_review_agent(self.task_path, profile_name="reviewer")
        self.assertIsNotNone(record)
        metadata, body = read_artifact(record.metadata_path)
        self.assertEqual(metadata["artifact_type"], "review.json")
        self.assertEqual(metadata["role"], "reviewer")
        
        review = json.loads(body)
        self.assertEqual(review["status"], "approved")
