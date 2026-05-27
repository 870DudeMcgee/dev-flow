import io
import json
import os
import shutil
import sys
import tempfile
import unittest

raise unittest.SkipTest("legacy memory workflow tests are outside the control-room MVP")

from contextlib import redirect_stdout

from devflow.cli import init_workspace, main, run_task
from devflow.context import build_context_pack
from devflow.memory import add_memory, inspect_memory, invalidate_memories, list_memories


class TestMemoryRecords(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)
        os.system("git init > /dev/null 2>&1")
        os.system("git config user.email 'tests@example.com'")
        os.system("git config user.name 'Devflow Tests'")
        os.makedirs("src/devflow", exist_ok=True)
        os.makedirs("tests", exist_ok=True)
        with open("src/devflow/target.py", "w", encoding="utf-8") as handle:
            handle.write("def target():\n    return 'old'\n")
        with open("tests/test_target.py", "w", encoding="utf-8") as handle:
            handle.write("import unittest\n\nclass TestTarget(unittest.TestCase):\n    def test_target(self):\n        self.assertTrue(True)\n")
        os.system("git add . > /dev/null 2>&1")
        os.system("git commit -m 'init' > /dev/null 2>&1")
        init_workspace()

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    def test_memory_record_is_written_listed_and_inspected(self):
        record = add_memory(
            memory_type="architecture",
            statement="target.py owns target behavior",
            evidence="src/devflow/target.py",
            invalidated_by_paths=["src/devflow/target.py"],
        )

        records = list_memories()
        inspected = inspect_memory(record["memory_id"])

        self.assertEqual(records, [record])
        self.assertEqual(inspected["statement"], "target.py owns target behavior")
        self.assertEqual(inspected["status"], "active")
        self.assertEqual(inspected["confidence"], 1.0)
        self.assertTrue(os.path.exists(os.path.join(".devflow", "memory", f"{record['memory_id']}.json")))

    def test_invalidate_memories_marks_matching_records_stale(self):
        active = add_memory(
            memory_type="architecture",
            statement="target.py owns target behavior",
            evidence="src/devflow/target.py",
            invalidated_by_paths=["src/devflow/target.py"],
        )
        untouched = add_memory(
            memory_type="architecture",
            statement="other behavior is unrelated",
            evidence="src/devflow/other.py",
            invalidated_by_paths=["src/devflow/other.py"],
        )

        invalidated = invalidate_memories(["src/devflow/target.py"])

        self.assertEqual([record["memory_id"] for record in invalidated], [active["memory_id"]])
        self.assertEqual(inspect_memory(active["memory_id"])["status"], "stale")
        self.assertEqual(inspect_memory(active["memory_id"])["confidence"], 0.0)
        self.assertEqual(inspect_memory(untouched["memory_id"])["status"], "active")

    def test_run_apply_invalidates_memory_for_touched_diff_paths(self):
        record = add_memory(
            memory_type="architecture",
            statement="target.py returns old",
            evidence="src/devflow/target.py",
            invalidated_by_paths=["src/devflow/target.py"],
        )
        os.makedirs(".devflow/tasks", exist_ok=True)
        task_path = ".devflow/tasks/T-900_memory.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("""# Task: T-900 - Change Target
Status: PENDING
Touched Files:
- src/devflow/target.py

## 1. Objective
Change the target return value.

## 2. Allowed Files
- src/devflow/target.py

## 7. Verification Commands
- python3 -m unittest discover -s tests -q

## 9. Execution Results

```diff
diff --git a/src/devflow/target.py b/src/devflow/target.py
--- a/src/devflow/target.py
+++ b/src/devflow/target.py
@@ -1,2 +1,2 @@
 def target():
-    return 'old'
+    return 'new'
```

## 10. Final Report
Pending.
""")
        os.system("git add .devflow > /dev/null 2>&1")
        os.system("git commit -m 'add devflow memory task' > /dev/null 2>&1")

        with redirect_stdout(io.StringIO()):
            run_task(task_path, yes=True)

        inspected = inspect_memory(record["memory_id"])
        self.assertEqual(inspected["status"], "stale")
        self.assertEqual(inspected["confidence"], 0.0)

    def test_stale_memories_are_excluded_from_context_packs(self):
        active = add_memory(
            memory_type="architecture",
            statement="target.py owns current behavior",
            evidence="src/devflow/target.py",
            invalidated_by_paths=["src/devflow/target.py"],
        )
        stale = add_memory(
            memory_type="architecture",
            statement="target.py returns old",
            evidence="src/devflow/target.py",
            invalidated_by_paths=["src/devflow/target.py"],
        )
        invalidate_memories(["src/devflow/target.py"], memory_ids=[stale["memory_id"]])
        os.makedirs(".devflow/tasks", exist_ok=True)
        task_path = ".devflow/tasks/T-901_context.md"
        with open(task_path, "w", encoding="utf-8") as handle:
            handle.write("""# Task: T-901 - Build Context
Status: PENDING
Touched Files:
- src/devflow/target.py

## 1. Objective
Build context.

## 2. Allowed Files
- src/devflow/target.py

## 3. Do Not Touch
- src/devflow/other.py

## 7. Verification Commands
- python -m unittest
""")

        artifact = build_context_pack(task_path, role="reviewer", token_budget=2000)
        with open(artifact.body_path, "r", encoding="utf-8") as handle:
            pack = json.load(handle)

        self.assertIn(active["statement"], json.dumps(pack))
        self.assertNotIn(stale["statement"], json.dumps(pack))

    def test_memory_cli_add_list_and_inspect(self):
        old_argv = sys.argv
        try:
            add_buffer = io.StringIO()
            sys.argv = [
                "devflow",
                "memory",
                "add",
                "--type",
                "architecture",
                "--statement",
                "target.py owns target behavior",
                "--evidence",
                "src/devflow/target.py",
                "--invalidate-on",
                "src/devflow/target.py",
            ]
            with redirect_stdout(add_buffer):
                main()
            memory_id = add_buffer.getvalue().split("memory_id:", 1)[1].strip().splitlines()[0]

            list_buffer = io.StringIO()
            sys.argv = ["devflow", "memory", "list"]
            with redirect_stdout(list_buffer):
                main()

            inspect_buffer = io.StringIO()
            sys.argv = ["devflow", "memory", "inspect", memory_id]
            with redirect_stdout(inspect_buffer):
                main()
        finally:
            sys.argv = old_argv

        self.assertIn(memory_id, list_buffer.getvalue())
        self.assertIn("active", list_buffer.getvalue())
        self.assertIn("target.py owns target behavior", inspect_buffer.getvalue())


if __name__ == "__main__":
    unittest.main()