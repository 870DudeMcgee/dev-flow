import unittest
from devflow.runner import (
    classify_failure,
    detect_files_from_unified_diff,
    protected_paths_touched,
    retry_budget_for,
    paths_outside_allowed,
    write_task_report,
)
import os
import shutil
import tempfile

class TestRunner(unittest.TestCase):
    def test_detect_files_from_unified_diff(self):
        diff_text = """diff --git a/src/a.py b/src/a.py
--- a/src/a.py
+++ b/src/a.py
@@ -1 +1 @@
-a
+b
diff --git a/tests/t.py b/tests/t.py
--- a/tests/t.py
+++ b/tests/t.py
@@ -1 +1 @@
-x
+y
"""
        files = detect_files_from_unified_diff(diff_text)
        self.assertEqual(files, ["src/a.py", "tests/t.py"])

    def test_protected_paths_touched(self):
        paths = ["src/app.py", ".env", "infra/migrations/001.sql"]
        protected = [".env", "**/migrations/**"]
        touched = protected_paths_touched(paths, protected)
        self.assertIn(".env", touched)
        self.assertIn("infra/migrations/001.sql", touched)
        self.assertNotIn("src/app.py", touched)

    def test_paths_outside_allowed_supports_globs_and_ellipsis(self):
        paths = ["src/devflow/cli.py", "tests/test_cli.py", "docs/readme.md"]
        allowed = ["src/devflow/**", "tests/..."]
        self.assertEqual(paths_outside_allowed(paths, allowed), ["docs/readme.md"])

    def test_paths_outside_allowed_supports_exact_paths(self):
        paths = ["sample.txt", "other.txt"]
        allowed = ["sample.txt"]
        self.assertEqual(paths_outside_allowed(paths, allowed), ["other.txt"])

    def test_classify_failure(self):
        self.assertEqual(classify_failure("patch", "error"), "PATCH_APPLY_FAILURE")
        self.assertEqual(classify_failure("verification", "SyntaxError: bad"), "SYNTAX_ERROR")
        self.assertEqual(classify_failure("verification", "ImportError: bad"), "IMPORT_ERROR")
        self.assertEqual(classify_failure("verification", "ruff check ."), "LINT_FAILURE")
        self.assertEqual(classify_failure("verification", "mypy type error"), "TYPE_ERROR")
        self.assertEqual(classify_failure("verification", "FAILED tests"), "TEST_FAILURE")

    def test_retry_budget_defaults(self):
        self.assertEqual(retry_budget_for("TEST_FAILURE"), 1)
        self.assertEqual(retry_budget_for("UNKNOWN_FAILURE"), 0)

    def test_report_includes_ownership_metadata(self):
        temp_dir = tempfile.mkdtemp()
        try:
            report_path = os.path.join(temp_dir, "001.report.md")
            write_task_report(
                report_path,
                {
                    "task_id": "001",
                    "status": "COMPLETED",
                    "assigned_agent": "codex",
                    "owner_lock": "codex-desktop",
                    "touched_files": ["src/devflow/cli.py"],
                    "files_changed": ["src/devflow/cli.py"],
                    "protected_files": [],
                    "verification": [],
                },
            )
            with open(report_path, "r", encoding="utf-8") as handle:
                report = handle.read()
            self.assertIn("Assigned Agent: codex", report)
            self.assertIn("Owner Lock: codex-desktop", report)
            self.assertIn("Touched Files: src/devflow/cli.py", report)
        finally:
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    unittest.main()
