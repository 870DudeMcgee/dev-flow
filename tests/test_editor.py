import unittest
from devflow.manager import extract_unified_diff

class TestEditor(unittest.TestCase):
    def test_extract_unified_diff_from_task(self):
        task = """# Task: 002 - Demo
Status: PENDING

## 9. Execution Results
```diff
diff --git a/demo.txt b/demo.txt
--- a/demo.txt
+++ b/demo.txt
@@ -1 +1 @@
-old
+new
```
"""
        diff_text = extract_unified_diff(task)
        self.assertTrue(diff_text.startswith("diff --git"))
        self.assertIn("+new", diff_text)

    def test_extract_unified_diff_missing_block(self):
        task = "# Task: 003 - Missing Diff\nStatus: PENDING\n"
        diff_text = extract_unified_diff(task)
        self.assertEqual(diff_text, "")

if __name__ == "__main__":
    unittest.main()
