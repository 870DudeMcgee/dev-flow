import unittest
import os
import shutil
import tempfile
import io
import json
from contextlib import redirect_stdout

from devflow.cli import init_workspace, run_task, status_workspace


class TestCLI(unittest.TestCase):
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

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    def commit_all(self, message="checkpoint"):
        os.system("git add . > /dev/null 2>&1")
        os.system(f"git commit -m '{message}' > /dev/null 2>&1")

    def test_cli_init_creates_full_devflow_tree(self):
        init_workspace()

        self.assertTrue(os.path.exists(".devflow"))
        self.assertTrue(os.path.exists(".devflow/config.json"))
        self.assertTrue(os.path.exists(".devflow/constitution.md"))
        self.assertTrue(os.path.exists(".devflow/goals"))
        self.assertTrue(os.path.exists(".devflow/plans"))
        self.assertTrue(os.path.exists(".devflow/tasks"))
        self.assertTrue(os.path.exists(".devflow/workflows"))
        self.assertTrue(os.path.exists(".devflow/reports"))

    def test_cli_init_writes_conservative_mvp_config_defaults(self):
        init_workspace()

        with open(".devflow/config.json", "r", encoding="utf-8") as handle:
            config = json.load(handle)

        self.assertNotIn("orchestrator", config)
        self.assertEqual(config["verification"]["test_command"], "auto")
        self.assertEqual(config["verification"]["lint_command"], "auto")
        self.assertEqual(config["verification"]["typecheck_command"], "auto")
        self.assertTrue(config["git"]["require_clean_worktree"])
        self.assertFalse(config["risk"]["auto_apply_low_risk"])

    def test_status_outputs_counts(self):
        init_workspace()
        task_path = ".devflow/tasks/001_example.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("# Task: 001 - Example\nStatus: PENDING\n")
        with open(".devflow/tasks/002_claimed.md", "w", encoding="utf-8") as handle:
            handle.write("# Task: 002 - Claimed\nStatus: CLAIMED\n")

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            status_workspace()
        output = buffer.getvalue()
        self.assertIn("devflow status", output)
        self.assertIn("pending: 1", output)
        self.assertIn("claimed: 1", output)

    def test_run_previews_unified_diff_without_yes(self):
        init_workspace()
        task_path = ".devflow/tasks/001_example.md"
        content = """# Task: 001 - Update Sample
Status: PENDING
Goal: 001_devflow_mvp
Plan: 001_devflow_mvp.plan.json
Assigned Agent: local_ollama
Risk: LOW
Branch: devflow/task-001

## 1. Objective
Update sample file.

## 2. Allowed Files
- sample.txt

## 3. Do Not Touch
- .env

## 4. Required Context
sample.txt currently contains hello.

## 5. Implementation Instructions
Apply patch.

## 6. Patch Protocol
Unified diff.

## 7. Verification Commands
- true

## 8. Failure Handling
Retry once.

## 9. Execution Results
```diff
diff --git a/sample.txt b/sample.txt
--- a/sample.txt
+++ b/sample.txt
@@ -1 +1 @@
-hello
+hello world
```

## 10. Final Report
Pending.
"""
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        self.commit_all("add task")

        run_task(task_path)

        with open("sample.txt", "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "hello\n")
        with open(task_path, "r", encoding="utf-8") as handle:
            updated = handle.read()
            self.assertIn("Status: PREVIEWED", updated)
        self.assertTrue(os.path.exists(".devflow/reports/001.report.md"))

    def test_run_applies_unified_diff_with_yes_and_writes_report(self):
        init_workspace()
        task_path = ".devflow/tasks/001_example.md"
        content = """# Task: 001 - Update Sample
Status: PENDING
Goal: 001_devflow_mvp
Plan: 001_devflow_mvp.plan.json
Assigned Agent: local_ollama
Risk: LOW
Branch: devflow/task-001

## 1. Objective
Update sample file.

## 2. Allowed Files
- sample.txt

## 3. Do Not Touch
- .env

## 4. Required Context
sample.txt currently contains hello.

## 5. Implementation Instructions
Apply patch.

## 6. Patch Protocol
Unified diff.

## 7. Verification Commands
- true

## 8. Failure Handling
Retry once.

## 9. Execution Results
```diff
diff --git a/sample.txt b/sample.txt
--- a/sample.txt
+++ b/sample.txt
@@ -1 +1 @@
-hello
+hello world
```

## 10. Final Report
Pending.
"""
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        self.commit_all("add task")

        run_task(task_path, yes=True)

        with open("sample.txt", "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "hello world\n")
        with open(task_path, "r", encoding="utf-8") as handle:
            updated = handle.read()
            self.assertIn("Status: COMPLETED", updated)
        self.assertTrue(os.path.exists(".devflow/reports/001.report.md"))

    def test_run_blocks_protected_file_diff(self):
        init_workspace()
        task_path = ".devflow/tasks/002_blocked.md"
        content = """# Task: 002 - Touch Env
Status: PENDING

## 1. Objective
Should block.

## 2. Allowed Files
- .env

## 3. Do Not Touch
- .env

## 4. Required Context
None.

## 5. Implementation Instructions
None.

## 6. Patch Protocol
Unified diff.

## 7. Verification Commands
- true

## 8. Failure Handling
None.

## 9. Execution Results
```diff
diff --git a/.env b/.env
--- a/.env
+++ b/.env
@@ -0,0 +1 @@
+SECRET=1
```

## 10. Final Report
Pending.
"""
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        self.commit_all("add protected task")

        run_task(task_path, yes=True)

        with open(task_path, "r", encoding="utf-8") as handle:
            updated = handle.read()
            self.assertIn("Status: BLOCKED", updated)
        self.assertTrue(os.path.exists(".devflow/reports/002.report.md"))

    def test_run_stops_without_mutation_when_worktree_is_dirty(self):
        init_workspace()
        task_path = ".devflow/tasks/003_dirty.md"
        content = """# Task: 003 - Dirty Guard
Status: PENDING

## 1. Objective
Should not run when dirty.

## 2. Allowed Files
- sample.txt

## 3. Do Not Touch
- .env

## 4. Required Context
None.

## 5. Implementation Instructions
None.

## 6. Patch Protocol
Unified diff.

## 7. Verification Commands
- true

## 8. Failure Handling
None.

## 9. Execution Results
```diff
diff --git a/sample.txt b/sample.txt
--- a/sample.txt
+++ b/sample.txt
@@ -1 +1 @@
-hello
+dirty should not apply
```

## 10. Final Report
Pending.
"""
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        self.commit_all("add dirty task")
        with open("sample.txt", "w", encoding="utf-8") as handle:
            handle.write("uncommitted change\n")

        run_task(task_path, yes=True)

        with open("sample.txt", "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "uncommitted change\n")
        with open(task_path, "r", encoding="utf-8") as handle:
            self.assertIn("Status: PENDING", handle.read())
        self.assertFalse(os.path.exists(".devflow/reports/003.report.md"))

    def test_allowed_files_accepts_glob_patterns(self):
        init_workspace()
        task_path = ".devflow/tasks/004_glob.md"
        content = """# Task: 004 - Glob Allowed
Status: PENDING

## 1. Objective
Preview a new file under an allowed glob.

## 2. Allowed Files
- src/devflow/**

## 3. Do Not Touch
- .env

## 4. Required Context
None.

## 5. Implementation Instructions
None.

## 6. Patch Protocol
Unified diff.

## 7. Verification Commands
- true

## 8. Failure Handling
None.

## 9. Execution Results
```diff
diff --git a/src/devflow/new_module.py b/src/devflow/new_module.py
new file mode 100644
--- /dev/null
+++ b/src/devflow/new_module.py
@@ -0,0 +1 @@
+VALUE = 1
```

## 10. Final Report
Pending.
"""
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        self.commit_all("add glob task")

        run_task(task_path)

        with open(task_path, "r", encoding="utf-8") as handle:
            self.assertIn("Status: PREVIEWED", handle.read())

    def test_verification_failure_rolls_back_to_checkpoint(self):
        init_workspace()
        task_path = ".devflow/tasks/005_rollback.md"
        content = """# Task: 005 - Rollback
Status: PENDING

## 1. Objective
Apply then fail verification.

## 2. Allowed Files
- sample.txt

## 3. Do Not Touch
- .env

## 4. Required Context
None.

## 5. Implementation Instructions
None.

## 6. Patch Protocol
Unified diff.

## 7. Verification Commands
- false

## 8. Failure Handling
None.

## 9. Execution Results
```diff
diff --git a/sample.txt b/sample.txt
--- a/sample.txt
+++ b/sample.txt
@@ -1 +1 @@
-hello
+should roll back
```

## 10. Final Report
Pending.
"""
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        self.commit_all("add rollback task")

        run_task(task_path, yes=True)

        with open("sample.txt", "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "hello\n")
        with open(task_path, "r", encoding="utf-8") as handle:
            self.assertIn("Status: FAILED", handle.read())
        with open(".devflow/reports/005.report.md", "r", encoding="utf-8") as handle:
            report = handle.read()
        self.assertIn("Rollback Status: checkpoint_reset", report)

    def test_run_mirrors_task_status_to_plan_json_when_present(self):
        init_workspace()
        plan_path = ".devflow/plans/001_devflow_mvp.plan.json"
        with open(plan_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "goal_id": "001_devflow_mvp",
                    "status": "ACTIVE",
                    "tasks": [{"id": "006", "title": "Mirror status", "status": "PENDING"}],
                },
                handle,
            )
        task_path = ".devflow/tasks/006_plan_mirror.md"
        content = """# Task: 006 - Plan Mirror
Status: PENDING
Plan: 001_devflow_mvp.plan.json

## 1. Objective
Preview and mirror status.

## 2. Allowed Files
- sample.txt

## 3. Do Not Touch
- .env

## 4. Required Context
None.

## 5. Implementation Instructions
None.

## 6. Patch Protocol
Unified diff.

## 7. Verification Commands
- true

## 8. Failure Handling
None.

## 9. Execution Results
```diff
diff --git a/sample.txt b/sample.txt
--- a/sample.txt
+++ b/sample.txt
@@ -1 +1 @@
-hello
+plan mirrored
```

## 10. Final Report
Pending.
"""
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        self.commit_all("add plan mirror task")

        run_task(task_path)

        with open(plan_path, "r", encoding="utf-8") as handle:
            plan = json.load(handle)
        self.assertEqual(plan["tasks"][0]["status"], "PREVIEWED")

if __name__ == "__main__":
    unittest.main()
