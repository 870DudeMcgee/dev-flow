import unittest
from devflow.manager import parse_task_file

class TestManager(unittest.TestCase):
    def test_parse_task_file(self):
        raw_markdown = """# Task: 001 - Create Auth Schema
Status: PENDING
Assigned To: LOCAL_AGENT_CODING
Target Files: 
- `backend/app/schemas/auth.py`

## [1. ORCHESTRATOR INSTRUCTIONS]
Create a basic schema.

## [2. REQUIRED CONTEXT FILES]
<!-- file: test.py -->
```python
print('hello')
```

## [3. LOCAL AGENT WORK AREA]
Work goes here

## [4. EXECUTION RESULTS]
Results here
"""
        task = parse_task_file(raw_markdown)
        self.assertEqual(task["task_id"], "001")
        self.assertEqual(task["title"], "Create Auth Schema")
        self.assertEqual(task["status"], "PENDING")
        self.assertEqual(task["assigned_to"], "LOCAL_AGENT_CODING")
        self.assertEqual(task["target_files"], ["backend/app/schemas/auth.py"])
        self.assertIn("Create a basic schema.", task["instructions"])
        self.assertIn("print('hello')", task["context_files"])
        self.assertIn("Work goes here", task["work_area"])
        self.assertIn("Results here", task["execution_results"])

if __name__ == "__main__":
    unittest.main()
