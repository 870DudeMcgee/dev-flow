import unittest
from devflow.manager import extract_unified_diff, parse_task_file

class TestManager(unittest.TestCase):
    def test_parse_task_file_canonical_schema(self):
        raw_markdown = """# Task: 001 - Update Greeting
Status: PENDING
Goal: 001_devflow_mvp
Plan: 001_devflow_mvp.plan.json
Assigned Agent: local_ollama
Owner Lock: vscode-copilot
Risk: LOW
Branch: devflow/task-001
Touched Files:
- src/example.txt
- tests/test_example.py

## 1. Objective
Update greeting text.

## 2. Allowed Files
- src/example.txt

## 3. Do Not Touch
- .env

## 4. Required Context
Existing greeting file under src.

## 5. Implementation Instructions
Apply the diff and keep newline.

## 6. Patch Protocol
Unified diff only.

## 7. Verification Commands
- true

## 8. Failure Handling
Retry once for patch and verification failures.

## 9. Execution Results
```diff
diff --git a/src/example.txt b/src/example.txt
index 0000000..1111111 100644
--- a/src/example.txt
+++ b/src/example.txt
@@ -1 +1 @@
-hello
+hello world
```

## 10. Final Report
Pending.
"""
        task = parse_task_file(raw_markdown)
        self.assertEqual(task["task_id"], "001")
        self.assertEqual(task["title"], "Update Greeting")
        self.assertEqual(task["status"], "PENDING")
        self.assertEqual(task["goal"], "001_devflow_mvp")
        self.assertEqual(task["plan"], "001_devflow_mvp.plan.json")
        self.assertEqual(task["assigned_agent"], "local_ollama")
        self.assertEqual(task["owner_lock"], "vscode-copilot")
        self.assertEqual(task["touched_files"], ["src/example.txt", "tests/test_example.py"])
        self.assertEqual(task["branch"], "devflow/task-001")
        self.assertEqual(task["allowed_files"], ["src/example.txt"])
        self.assertEqual(task["do_not_touch"], [".env"])
        self.assertIn("Update greeting text", task["objective"])
        self.assertIn("Unified diff", task["patch_protocol"])
        self.assertEqual(task["verification_commands"], ["true"])

    def test_extract_unified_diff(self):
        task_content = """# Task: 001 - Example
Status: PENDING

## 9. Execution Results
```diff
diff --git a/a.txt b/a.txt
--- a/a.txt
+++ b/a.txt
@@ -1 +1 @@
-a
+b
```
"""
        diff_text = extract_unified_diff(task_content)
        self.assertIn("diff --git a/a.txt b/a.txt", diff_text)
        self.assertIn("+b", diff_text)

    def test_extract_unified_diff_with_trailing_space_on_fence(self):
        """Bug: regex fails when the opening ```diff fence has trailing whitespace."""
        task_content = "## 9. Execution Results\n```diff \ndiff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-a\n+b\n```\n"
        diff_text = extract_unified_diff(task_content)
        self.assertIn("diff --git a/a.txt b/a.txt", diff_text)

    def test_extract_unified_diff_with_crlf_line_endings(self):
        """Bug: regex fails when file contains CRLF line endings (Windows editors)."""
        task_content = "## 9. Execution Results\r\n```diff\r\ndiff --git a/a.txt b/a.txt\r\n--- a/a.txt\r\n+++ b/a.txt\r\n@@ -1 +1 @@\r\n-a\r\n+b\r\n```\r\n"
        diff_text = extract_unified_diff(task_content)
        self.assertIn("diff --git", diff_text)

if __name__ == "__main__":
    unittest.main()
