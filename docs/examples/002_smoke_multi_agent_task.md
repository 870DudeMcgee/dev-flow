# Task: 002 - Add add-item command to smoke todo CLI
Status: PENDING
Goal: 002_smoke_multi_agent_integration
Plan: 002_smoke_multi_agent.plan.json
Assigned Agent: codex
Owner Lock:
Risk: LOW
Branch: devflow/task-002-codex
Touched Files:
- smoke_todo_cli/todo_cli.py
- smoke_todo_cli/tests/test_todo_cli.py

## 1. Objective

Add an `add-item` command to a smoke-test TODO CLI and verify it via `unittest` in a clean temporary repo.

## 2. Allowed Files

- smoke_todo_cli/todo_cli.py
- smoke_todo_cli/tests/test_todo_cli.py

## 3. Do Not Touch

- .env
- production secrets
- files outside Allowed Files

## 4. Required Context

Setup in a temporary clean git repo before running this task:

```bash
mkdir smoke_todo_cli
mkdir -p smoke_todo_cli/tests
cat > smoke_todo_cli/todo_cli.py <<'PY'
import sys


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        return "usage: todo <list|add-item>"
    if argv[0] == "list":
        return "[]"
    return "unknown command"


if __name__ == "__main__":
    print(main())
PY

cat > smoke_todo_cli/tests/test_todo_cli.py <<'PY'
import unittest
from smoke_todo_cli.todo_cli import main


class TodoCliTests(unittest.TestCase):
    def test_list_command(self):
        self.assertEqual(main(["list"]), "[]")

    def test_unknown_command(self):
        self.assertEqual(main(["x"]), "unknown command")


if __name__ == "__main__":
    unittest.main()
PY

git add smoke_todo_cli
git commit -m "seed smoke todo cli"
```

Worker preflight should be recorded before claiming task:
- endpoint reachable
- baseline model available
- generation probe result

## 5. Implementation Instructions

1. Claim task before editing task metadata or touched files.
2. Use local worker output to draft the diff below if needed.
3. Run preview first:
   - `PYTHONPATH=src python3 -m devflow run .devflow/tasks/002_smoke_multi_agent_task.md`
4. Make worktree clean again (commit preview metadata or reset).
5. Run apply:
   - `PYTHONPATH=src python3 -m devflow run .devflow/tasks/002_smoke_multi_agent_task.md --yes`
6. Confirm status, report, and test output.

## 6. Patch Protocol

Unified diff only.

## 7. Verification Commands

- python3 -m unittest discover -s smoke_todo_cli/tests -q

## 8. Failure Handling

- Patch apply failure: stop and report
- Protected file touched: stop immediately
- Verification failure: rollback and report

## 9. Execution Results

```diff
diff --git a/smoke_todo_cli/tests/test_todo_cli.py b/smoke_todo_cli/tests/test_todo_cli.py
index 64db81c..79e5bbb 100644
--- a/smoke_todo_cli/tests/test_todo_cli.py
+++ b/smoke_todo_cli/tests/test_todo_cli.py
@@ -9,6 +9,12 @@ class TodoCliTests(unittest.TestCase):
     def test_unknown_command(self):
         self.assertEqual(main(["x"]), "unknown command")

+    def test_add_item_command(self):
+        self.assertEqual(main(["add-item", "milk"]), "added:milk")
+
+    def test_add_item_missing_value(self):
+        self.assertEqual(main(["add-item"]), "missing item")
+
 
 if __name__ == "__main__":
     unittest.main()
diff --git a/smoke_todo_cli/todo_cli.py b/smoke_todo_cli/todo_cli.py
index e29f57d..7d634ea 100644
--- a/smoke_todo_cli/todo_cli.py
+++ b/smoke_todo_cli/todo_cli.py
@@ -7,8 +7,12 @@ def main(argv=None):
         return "usage: todo <list|add-item>"
     if argv[0] == "list":
         return "[]"
+    if argv[0] == "add-item":
+        if len(argv) < 2 or not argv[1].strip():
+            return "missing item"
+        return f"added:{argv[1]}"
     return "unknown command"


 if __name__ == "__main__":
     print(main())
```

## 10. Final Report

Pending.
