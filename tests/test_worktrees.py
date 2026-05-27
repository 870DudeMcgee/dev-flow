import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from devflow.cli import init_workspace, main
from devflow.worktrees import create_worktree, list_worktrees, remove_worktree


class TestWorktrees(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)
        os.system("git init > /dev/null 2>&1")
        os.system("git config user.email 'tests@example.com'")
        os.system("git config user.name 'Devflow Tests'")
        with open("sample.txt", "w", encoding="utf-8") as handle:
            handle.write("hello\n")
        os.system("git add sample.txt")
        os.system("git commit -m 'init' > /dev/null 2>&1")
        init_workspace()
        os.system("git add .devflow sample.txt > /dev/null 2>&1")
        os.system("git commit -m 'devflow init' > /dev/null 2>&1")

        self.task_path = ".devflow/tasks/090_worktree.md"
        with open(self.task_path, "w", encoding="utf-8") as handle:
            handle.write("""# Task: 090 - Worktree Task
Status: CLAIMED
Assigned Agent: antigravity
Owner Lock: antigravity-session
Branch: devflow/task-090-antigravity
Touched Files:
- sample.txt

## 1. Objective
Work in isolation.

## 2. Allowed Files
- sample.txt
""")
        os.system("git add .devflow/tasks/090_worktree.md > /dev/null 2>&1")
        os.system("git commit -m 'add task' > /dev/null 2>&1")

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    def test_create_worktree_records_metadata_and_adds_git_worktree(self):
        record = create_worktree(self.task_path, agent="antigravity")

        self.assertEqual(record["task_id"], "090")
        self.assertEqual(record["owner"], "antigravity")
        self.assertEqual(record["branch"], "devflow/task-090-antigravity")
        self.assertTrue(os.path.isdir(record["path"]))
        self.assertTrue(os.path.exists(os.path.join(record["path"], "sample.txt")))
        self.assertEqual(record["status"], "active")
        self.assertEqual(len(record["base_sha"]), 40)

        with open(".devflow/worktrees/index.json", "r", encoding="utf-8") as handle:
            index = json.load(handle)
        self.assertEqual(index["worktrees"][0]["task_file"], self.task_path)

    def test_list_worktrees_returns_active_records(self):
        create_worktree(self.task_path, agent="antigravity")

        records = list_worktrees()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["task_id"], "090")
        self.assertEqual(records[0]["status"], "active")

    def test_remove_worktree_marks_record_removed_and_preserves_artifacts(self):
        record = create_worktree(self.task_path, agent="antigravity")
        artifact_dir = os.path.join(".devflow", "artifacts", "090")
        os.makedirs(artifact_dir, exist_ok=True)
        with open(os.path.join(artifact_dir, "kept.txt"), "w", encoding="utf-8") as handle:
            handle.write("artifact\n")

        removed = remove_worktree(self.task_path, keep_artifacts=True)

        self.assertEqual(removed["status"], "removed")
        self.assertFalse(os.path.exists(record["path"]))
        self.assertTrue(os.path.exists(os.path.join(artifact_dir, "kept.txt")))
        self.assertTrue(removed["removed_at"])

    def test_create_cli_command_prints_metadata(self):
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "worktree", "create", self.task_path, "--agent", "antigravity"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
        finally:
            sys.argv = old_argv

        output = buffer.getvalue()
        self.assertIn("Worktree created", output)
        self.assertIn("task_id: 090", output)
        self.assertIn("branch: devflow/task-090-antigravity", output)

    def test_status_cli_command_lists_worktrees(self):
        create_worktree(self.task_path, agent="antigravity")

        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "worktree", "status"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
        finally:
            sys.argv = old_argv

        output = buffer.getvalue()
        self.assertIn("090", output)
        self.assertIn("antigravity", output)
        self.assertIn("active", output)


if __name__ == "__main__":
    unittest.main()