import unittest
import os
import shutil
import tempfile
import io
import json
import sys
from contextlib import redirect_stdout
from unittest.mock import patch, MagicMock

from devflow.repo_map import refresh_repo_maps
from devflow.cli import (
    claim_task,
    init_workspace,
    main,
    new_task,
    release_task,
    run_task,
    status_task,
    status_workspace,
)


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
        self.assertTrue(os.path.exists(".devflow/artifacts"))
        self.assertTrue(os.path.exists(".devflow/orchestrators"))

    def test_cli_init_creates_peer_orchestrator_templates(self):
        init_workspace()

        expected_files = [
            ".devflow/orchestrators/codex.md",
            ".devflow/orchestrators/vscode-copilot.md",
            ".devflow/orchestrators/antigravity.md",
            ".devflow/orchestrators/local-model-worker-policy.md",
        ]
        for path in expected_files:
            self.assertTrue(os.path.exists(path), path)

        with open(".devflow/orchestrators/codex.md", "r", encoding="utf-8") as handle:
            codex_template = handle.read()
        self.assertIn("Peer Orchestrator", codex_template)
        self.assertIn("Product/Spec Analyst", codex_template)
        self.assertIn("Diff Implementer", codex_template)
        self.assertIn("Do not assume permanent global role ownership", codex_template)

        with open(".devflow/orchestrators/local-model-worker-policy.md", "r", encoding="utf-8") as handle:
            worker_policy = handle.read()
        self.assertIn("Local models are worker subagents", worker_policy)
        self.assertIn("must not mutate repo state directly", worker_policy)

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

    def test_task_claim_updates_ownership_headers(self):
        init_workspace()
        task_path = ".devflow/tasks/010_claim.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("""# Task: 010 - Claim Me
Status: PENDING

## 1. Objective
Claim task.
""")

        claim_task(
            task_path,
            agent="codex",
            owner_lock="codex-desktop",
            touched_files=["src/devflow/cli.py", "tests/test_cli.py"],
        )

        with open(task_path, "r", encoding="utf-8") as handle:
            updated = handle.read()
        self.assertIn("Status: CLAIMED", updated)
        self.assertIn("Assigned Agent: codex", updated)
        self.assertIn("Owner Lock: codex-desktop", updated)
        self.assertIn("Branch: devflow/task-010-codex", updated)
        self.assertIn("Touched Files:\n- src/devflow/cli.py\n- tests/test_cli.py", updated)

    def test_task_claim_refuses_already_claimed_without_force(self):
        init_workspace()
        task_path = ".devflow/tasks/011_claimed.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("""# Task: 011 - Claimed
Status: CLAIMED
Assigned Agent: vscode
Owner Lock: vscode-copilot

## 1. Objective
Already claimed.
""")

        claimed = claim_task(task_path, agent="codex", owner_lock="codex-desktop")

        self.assertFalse(claimed)
        with open(task_path, "r", encoding="utf-8") as handle:
            unchanged = handle.read()
        self.assertIn("Assigned Agent: vscode", unchanged)
        self.assertIn("Owner Lock: vscode-copilot", unchanged)

    def test_task_claim_force_overrides_existing_claim(self):
        init_workspace()
        task_path = ".devflow/tasks/012_force.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("""# Task: 012 - Force Claim
Status: CLAIMED
Assigned Agent: vscode
Owner Lock: vscode-copilot

## 1. Objective
Override claim.
""")

        claimed = claim_task(task_path, agent="codex", owner_lock="codex-desktop", force=True)

        self.assertTrue(claimed)
        with open(task_path, "r", encoding="utf-8") as handle:
            updated = handle.read()
        self.assertIn("Assigned Agent: codex", updated)
        self.assertIn("Owner Lock: codex-desktop", updated)

    def test_task_release_clears_ownership_and_returns_to_pending(self):
        init_workspace()
        task_path = ".devflow/tasks/013_release.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("""# Task: 013 - Release
Status: CLAIMED
Assigned Agent: codex
Owner Lock: codex-desktop
Branch: devflow/task-013-codex

## 1. Objective
Release claim.
""")

        release_task(task_path)

        with open(task_path, "r", encoding="utf-8") as handle:
            released = handle.read()
        self.assertIn("Status: PENDING", released)
        self.assertIn("Assigned Agent: ", released)
        self.assertIn("Owner Lock: ", released)
        self.assertIn("Branch: ", released)

    def test_task_status_prints_metadata_report_and_plan_mirror(self):
        init_workspace()
        plan_path = ".devflow/plans/001.plan.json"
        with open(plan_path, "w", encoding="utf-8") as handle:
            json.dump({"tasks": [{"id": "014", "status": "CLAIMED"}]}, handle)
        task_path = ".devflow/tasks/014_status.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("""# Task: 014 - Status
Status: CLAIMED
Plan: 001.plan.json
Assigned Agent: codex
Owner Lock: codex-desktop
Branch: devflow/task-014-codex
Touched Files:
- src/devflow/cli.py

## 1. Objective
Print status.

## 2. Allowed Files
- src/devflow/**
""")
        os.makedirs(".devflow/reports", exist_ok=True)
        with open(".devflow/reports/014.report.md", "w", encoding="utf-8") as handle:
            handle.write("# report\n")

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            status_task(task_path)
        output = buffer.getvalue()

        self.assertIn("Task 014 - Status", output)
        self.assertIn("status: CLAIMED", output)
        self.assertIn("assigned_agent: codex", output)
        self.assertIn("owner_lock: codex-desktop", output)
        self.assertIn("latest_report: .devflow/reports/014.report.md", output)
        self.assertIn("plan_status: CLAIMED", output)

    def test_task_claim_cli_command(self):
        init_workspace()
        task_path = ".devflow/tasks/015_cli_claim.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("""# Task: 015 - CLI Claim
Status: PENDING

## 1. Objective
Claim from CLI.
""")

        old_argv = sys.argv
        try:
            sys.argv = [
                "devflow",
                "task",
                "claim",
                task_path,
                "--agent",
                "antigravity",
                "--lock",
                "antigravity-team",
                "--touch",
                "src/devflow/cli.py",
            ]
            main()
        finally:
            sys.argv = old_argv

        with open(task_path, "r", encoding="utf-8") as handle:
            updated = handle.read()
        self.assertIn("Status: CLAIMED", updated)
        self.assertIn("Assigned Agent: antigravity", updated)
        self.assertIn("Owner Lock: antigravity-team", updated)
        self.assertIn("- src/devflow/cli.py", updated)

    def test_task_new_creates_canonical_task_template(self):
        init_workspace()

        task_path = new_task(
            "020",
            "Add Task Template",
            goal="001_devflow_mvp",
            plan="001.plan.json",
            agent="codex",
            risk="LOW",
            allowed_files=["src/devflow/**", "tests/..."],
            touched_files=["src/devflow/cli.py"],
            verification_commands=["PYTHONPATH=src python3 -m unittest discover -s tests -q"],
        )

        self.assertEqual(task_path, ".devflow/tasks/020_add_task_template.md")
        with open(task_path, "r", encoding="utf-8") as handle:
            content = handle.read()

        for header in (
            "Status: PENDING",
            "Goal: 001_devflow_mvp",
            "Plan: 001.plan.json",
            "Assigned Agent: codex",
            "Owner Lock:",
            "Risk: LOW",
            "Branch: devflow/task-020-codex",
            "Touched Files:",
        ):
            self.assertIn(header, content)
        for heading in (
            "## 1. Objective",
            "## 2. Allowed Files",
            "## 3. Do Not Touch",
            "## 4. Required Context",
            "## 5. Implementation Instructions",
            "## 6. Patch Protocol",
            "## 7. Verification Commands",
            "## 8. Failure Handling",
            "## 9. Execution Results",
            "## 10. Final Report",
        ):
            self.assertIn(heading, content)
        self.assertIn("- src/devflow/**", content)
        self.assertIn("- tests/...", content)
        self.assertIn("- src/devflow/cli.py", content)
        self.assertIn("```diff", content)

    def test_task_new_refuses_to_overwrite_existing_task(self):
        init_workspace()
        new_task("021", "Existing Task")

        with self.assertRaises(FileExistsError):
            new_task("021", "Existing Task")

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

    def test_report_includes_audit_trail_and_verification_output(self):
        init_workspace()
        task_path = ".devflow/tasks/016_audit_report.md"
        content = """# Task: 016 - Audit Report
Status: PENDING

## 1. Objective
Generate a rich failed report.

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
- python3 -c "import sys; print('audit stdout'); sys.stderr.write('audit stderr\\\\n'); sys.exit(1)"

## 8. Failure Handling
None.

## 9. Execution Results
```diff
diff --git a/sample.txt b/sample.txt
--- a/sample.txt
+++ b/sample.txt
@@ -1 +1 @@
-hello
+audit report
```

## 10. Final Report
Pending.
"""
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        self.commit_all("add audit task")

        run_task(task_path, yes=True)

        with open(".devflow/reports/016.report.md", "r", encoding="utf-8") as handle:
            report = handle.read()
        self.assertIn("## Status Transitions", report)
        self.assertIn("- PENDING -> RUNNING", report)
        self.assertIn("- RUNNING -> FAILED", report)
        self.assertIn("## Safety Decisions", report)
        self.assertIn("- Dirty Worktree: clean", report)
        self.assertIn("- Protected Paths: none", report)
        self.assertIn("- Allowed Files: all changed files allowed", report)
        self.assertIn("## Verification Output", report)
        self.assertIn("audit stdout", report)
        self.assertIn("audit stderr", report)

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

    @patch("devflow.agents.ollama.urllib.request.urlopen")
    def test_agent_review_command(self, mock_urlopen):
        from devflow.artifacts import list_artifacts
        init_workspace()
        task_path = ".devflow/tasks/022_cli_review.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("# Task: 022 - CLI Review\nStatus: PENDING\nTouched Files:\n- sample.txt\n## 1. Objective\nReview.")

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"response": "{\\"status\\": \\"approved\\", \\"summary\\": \\"Code looks good\\", \\"findings\\": [], \\"required_actions\\": [], \\"confidence\\": 0.95}"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "agent", "review", task_path, "--profile", "reviewer"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv

        self.assertIn("Agent review completed", output)
        self.assertTrue(len(list_artifacts("022")) > 0)

    @patch("devflow.agents.ollama.urllib.request.urlopen")
    def test_agent_implement_command(self, mock_urlopen):
        from devflow.artifacts import list_artifacts
        init_workspace()
        task_path = ".devflow/tasks/023_cli_implement.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("# Task: 023 - CLI Implement\nStatus: PENDING\nTouched Files:\n- sample.txt\n## 1. Objective\nImplement.")

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"response": "{\\"status\\": \\"ready\\", \\"diff\\": \\"diff --git a/sample.txt b/sample.txt\\\\n--- a/sample.txt\\\\n+++ b/sample.txt\\\\n@@ -1 +1 @@\\\\n-hello\\\\n+hello world\\", \\"touched_paths\\": [\\"sample.txt\\"], \\"risk\\": \\"low\\", \\"confidence\\": 0.95}"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "agent", "implement", task_path, "--profile", "implementer", "--emit-diff"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv

        self.assertIn("Agent implementation completed", output)
        self.assertIn("--- PROPOSED DIFF ---", output)
        self.assertTrue(len(list_artifacts("023")) > 0)

    @patch("devflow.agents.ollama.urllib.request.urlopen")
    def test_agent_repair_command(self, mock_urlopen):
        from devflow.artifacts import list_artifacts
        init_workspace()
        
        # Write task file with verification command
        task_path = ".devflow/tasks/024_cli_repair.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("""# Task: 024 - CLI Repair
Status: PENDING
Touched Files:
- sample.txt
## 1. Objective
Repair sample.
## 2. Allowed Files
- sample.txt
## 7. Verification Commands
- true
## 9. Execution Results
```diff
diff --git a/sample.txt b/sample.txt
--- a/sample.txt
+++ b/sample.txt
@@ -1 +1 @@
-hello
+hello world
```
""")

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"response": "{\\"status\\": \\"ready\\", \\"diff\\": \\"diff --git a/sample.txt b/sample.txt\\\\n--- a/sample.txt\\\\n+++ b/sample.txt\\\\n@@ -1 +1 @@\\\\n-hello\\\\n+hello world\\\\n\\", \\"touched_paths\\": [\\"sample.txt\\"], \\"risk\\": \\"low\\", \\"confidence\\": 0.95}"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Commit task to make sure worktree is clean!
        os.system("git add . > /dev/null 2>&1")
        os.system("git commit -m 'commit repair task' > /dev/null 2>&1")
        refresh_repo_maps()
        os.system("git add . > /dev/null 2>&1")
        os.system("git commit -m 'commit maps' > /dev/null 2>&1")

        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "agent", "repair", task_path, "--profile", "repair", "--max-loops", "2"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv

        self.assertIn("Agent repair completed", output)
        self.assertTrue(len(list_artifacts("024")) > 0)


    def test_guard_scan_diff_clean_file(self):
        init_workspace()
        diff_path = "clean.diff"
        with open(diff_path, "w", encoding="utf-8") as f:
            f.write("+++ b/src/example.py\n+def foo():\n+    return 1\n")
            
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "guard", "scan-diff", diff_path]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as cm:
                    main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv
            
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("Safety scan completed", output)

    def test_guard_scan_diff_hazardous_file(self):
        init_workspace()
        diff_path = "hazardous.diff"
        with open(diff_path, "w", encoding="utf-8") as f:
            f.write("+++ b/src/config.py\n+API_KEY = 'secret-token-123'\n")
            
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "guard", "scan-diff", diff_path]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as cm:
                    main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv
            
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Adversarial hazards detected", output)

    def test_cli_transition_valid_tdd_states(self):
        init_workspace()
        new_task(
            "042",
            "TDD Task",
            goal="goal-1",
            plan="plan-1",
            agent="antigravity",
            risk="LOW",
            allowed_files=["sample.txt"],
            touched_files=["sample.txt"],
            verification_commands=["echo 'hello'"],
            output="task_042.md"
        )

        # Transition PENDING -> RED
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "task", "transition", "task_042.md", "--to", "RED", "--reason", "Ready to start", "--artifact", "art-1"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv

        self.assertIn("transitioned from PENDING to RED", output)
        
        # Verify status and Transitions header in file
        with open("task_042.md", "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("Status: RED", content)
        self.assertIn("Transitions:", content)
        self.assertIn("PENDING -> RED: Ready to start (artifact: art-1) at", content)

        # Transition RED -> GREEN
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "task", "transition", "task_042.md", "--to", "GREEN", "--reason", "Tests passing", "--artifact", "art-2"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv

        self.assertIn("transitioned from RED to GREEN", output)
        
        # Verify both transitions are present
        with open("task_042.md", "r", encoding="utf-8") as handle:
            content = handle.read()
        self.assertIn("Status: GREEN", content)
        self.assertIn("- PENDING -> RED: Ready to start (artifact: art-1) at", content)
        self.assertIn("- RED -> GREEN: Tests passing (artifact: art-2) at", content)

        # Print status and check output
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "task", "status", "task_042.md"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv

        self.assertIn("status: GREEN", output)
        self.assertIn("transitions:", output)
        self.assertIn("PENDING -> RED: Ready to start", output)

    def test_cli_transition_invalid_transition_fails(self):
        init_workspace()
        new_task(
            "043",
            "TDD Task 2",
            output="task_043.md"
        )

        # Invalid transition PENDING -> REFACTOR
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "task", "transition", "task_043.md", "--to", "REFACTOR"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with self.assertRaises(SystemExit) as cm:
                    main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Error: Transition from 'PENDING' to 'REFACTOR' is invalid", output)

    def test_cli_dag_and_impact(self):
        init_workspace()
        
        # Write a mock plan JSON
        mock_plan = {
            "goal_id": "cli_dag_test",
            "status": "ACTIVE",
            "tasks": [
                {
                    "id": "001",
                    "title": "First Task",
                    "status": "COMPLETED",
                    "depends_on": []
                },
                {
                    "id": "002",
                    "title": "Second Task",
                    "status": "PENDING",
                    "depends_on": ["001"],
                    "assigned_agent": "antigravity"
                }
            ]
        }
        with open(".devflow/plans/001_test.plan.json", "w", encoding="utf-8") as f:
            json.dump(mock_plan, f)

        # 1. Test ready command (non-JSON)
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "task", "ready"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv
        self.assertIn("Ready Tasks:", output)
        self.assertIn("Second Task", output)

        # 2. Test ready command with --json
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "task", "ready", "--json"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv
        parsed_ready = json.loads(output)
        self.assertEqual(len(parsed_ready), 1)
        self.assertEqual(parsed_ready[0]["id"], "002")

        # 3. Test next command
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "task", "next", "--agent", "antigravity"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv
        self.assertIn("Next Task: [002] Second Task", output)

        # 4. Test graph command
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "task", "graph"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv
        self.assertIn("Task Dependency Graph:", output)
        self.assertIn("[002] PENDING: Second Task (assigned: antigravity) [depends on: 001]", output)

        # 5. Create a task file to test impact command
        new_task(
            "002",
            "Second Task",
            goal="cli_dag_test",
            allowed_files=["sample.txt"],
            output="task_002.md"
        )
        
        # Test impact command
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "impact", "task_002.md"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv
        self.assertIn("Impact Analysis Report for Task 002 - Second Task", output)
        self.assertIn("Risk Level:", output)

    def test_cli_traces_and_evals(self):
        init_workspace()

        # 1. Test trace list
        # Create a mock trace file
        os.makedirs(".devflow/logs/traces", exist_ok=True)
        trace_id = "test_trace_123"
        trace_file = os.path.join(".devflow/logs/traces", f"{trace_id}.json")
        mock_trace_data = [
            {
                "span_id": "span-1",
                "name": "root_op",
                "start_time": "2026-05-27T08:00:00.000",
                "end_time": "2026-05-27T08:00:01.000",
                "duration_ms": 1000.0,
                "status": "SUCCESS",
                "parent_span_id": None,
                "attributes": {}
            },
            {
                "span_id": "span-2",
                "name": "child_op",
                "start_time": "2026-05-27T08:00:00.100",
                "end_time": "2026-05-27T08:00:00.500",
                "duration_ms": 400.0,
                "status": "SUCCESS",
                "parent_span_id": "span-1",
                "attributes": {}
            }
        ]
        with open(trace_file, "w", encoding="utf-8") as f:
            json.dump(mock_trace_data, f)

        # Run "devflow trace list"
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "trace", "list"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv
        self.assertIn("Trace ID", output)
        self.assertIn("test_trace_123", output)

        # Run "devflow trace inspect test_trace_123"
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "trace", "inspect", "test_trace_123"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv
        self.assertIn("Trace Execution Graph for ID: test_trace_123", output)
        self.assertIn("root_op (1000.00ms)", output)
        self.assertIn("child_op (400.00ms)", output)

        # 2. Test eval run
        # Create a mock evaluation fixture
        os.makedirs(".devflow/evals/fixtures", exist_ok=True)
        fixture_file = ".devflow/evals/fixtures/mock_cli_impl.json"
        mock_fixture = {
            "name": "cli_eval_test",
            "role": "implementer",
            "task_markdown": "# Task: 999 - CLI Task\nStatus: PENDING\nTouched Files:\n- sample.txt\n## 2. Allowed Files\n- sample.txt\n## 7. Verification Commands\n- true\n## 9. Execution Results\nPending.\n",
            "mock_model_response": "{\n  \"status\": \"ready\",\n  \"diff\": \"```diff\\ndiff --git a/sample.txt b/sample.txt\\n--- a/sample.txt\\n+++ b/sample.txt\\n@@ -1 +1 @@\\n-hello\\n+hello world\\n```\",\n  \"touched_paths\": [\"sample.txt\"],\n  \"risk\": \"low\",\n  \"confidence\": 1.0\n}",
            "assertions": {
                "expected_status": "ready",
                "must_touch_files": ["sample.txt"]
            }
        }
        with open(fixture_file, "w", encoding="utf-8") as f:
            json.dump(mock_fixture, f)

        # Run "devflow eval run --role implementer" with mocked invoke_local_model
        with patch("devflow.agents.ollama.invoke_local_model") as mock_invoke:
            mock_invoke.return_value = mock_fixture["mock_model_response"]
            
            old_argv = sys.argv
            try:
                sys.argv = ["devflow", "eval", "run", "--role", "implementer"]
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    with self.assertRaises(SystemExit) as cm:
                        main()
                output = buffer.getvalue()
            finally:
                sys.argv = old_argv

            self.assertEqual(cm.exception.code, 0)
            self.assertIn("Passed: 1/1", output)

        # 3. Test eval compare
        old_argv = sys.argv
        try:
            sys.argv = ["devflow", "eval", "compare", "Prompt A", "Prompt B"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                main()
            output = buffer.getvalue()
        finally:
            sys.argv = old_argv
        self.assertIn("Prompt Performance Comparison Report:", output)
        self.assertIn("Prompt A", output)
        self.assertIn("Prompt B", output)
        self.assertIn("Conclusion", output)

if __name__ == "__main__":
    unittest.main()


