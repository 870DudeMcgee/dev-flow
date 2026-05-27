import unittest
import tempfile
import os
import shutil
from devflow.dag import TaskDAG

class TestDAG(unittest.TestCase):
    def test_cycle_detection(self):
        # A simple cycle: 001 -> 002 -> 001
        tasks_with_cycle = [
            {"id": "001", "title": "Task 1", "depends_on": ["002"]},
            {"id": "002", "title": "Task 2", "depends_on": ["001"]},
        ]
        with self.assertRaises(ValueError) as cm:
            TaskDAG(tasks_with_cycle, root_dir="/non_existent_dir")
        self.assertIn("Dependency cycle detected", str(cm.exception))

    def test_valid_dag(self):
        tasks = [
            {"id": "001", "title": "Task 1", "depends_on": []},
            {"id": "002", "title": "Task 2", "depends_on": ["001"]},
            {"id": "003", "title": "Task 3", "depends_on": ["001"]},
            {"id": "004", "title": "Task 4", "depends_on": ["002", "003"]},
        ]
        dag = TaskDAG(tasks, root_dir="/non_existent_dir")
        self.assertEqual(len(dag.tasks), 4)

    def test_ready_blocked_and_next_queries(self):
        tasks = [
            {"id": "001", "title": "Task 1", "depends_on": [], "status": "PENDING", "assigned_agent": "antigravity"},
            {"id": "002", "title": "Task 2", "depends_on": ["001"], "status": "PENDING", "assigned_agent": "codex"},
            {"id": "003", "title": "Task 3", "depends_on": ["001"], "status": "PENDING"},
            {"id": "004", "title": "Task 4", "depends_on": ["002", "003"], "status": "PENDING"},
        ]
        dag = TaskDAG(tasks, root_dir="/non_existent_dir")

        # Initially, only 001 is ready
        ready = dag.get_ready_tasks()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["id"], "001")

        # Get next task for antigravity -> should be 001
        next_task = dag.get_next_task(agent="antigravity")
        self.assertEqual(next_task["id"], "001")

        # Get next task for codex -> should be None (since 002 is blocked/waiting on 001)
        self.assertIsNone(dag.get_next_task(agent="codex"))

        # Transition 001 to COMPLETED
        dag.update_task_status("001", "COMPLETED")
        
        # Now 002 and 003 are ready
        ready_tasks = [t["id"] for t in dag.get_ready_tasks()]
        self.assertIn("002", ready_tasks)
        self.assertIn("003", ready_tasks)

        # Get next task for codex -> should be 002
        next_task_codex = dag.get_next_task(agent="codex")
        self.assertEqual(next_task_codex["id"], "002")

        # Transition 002 to FAILED
        dag.update_task_status("002", "FAILED")

        # Task 004 depends on 002, so it should be blocked
        blocked = dag.get_blocked_tasks()
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["id"], "004")

    def test_live_filesystem_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # We mock the devflow tasks directory by creating .devflow/tasks structure
            tasks_dir = os.path.join(tmpdir, ".devflow", "tasks")
            os.makedirs(tasks_dir)

            # Write task md files
            task_001_content = """# Task: 001 - Init Project
Status: COMPLETED
Goal: goal_1
"""
            task_002_content = """# Task: 002 - Build Feature
Status: PENDING
Goal: goal_1
"""
            with open(os.path.join(tasks_dir, "001_init.md"), "w", encoding="utf-8") as f:
                f.write(task_001_content)
            with open(os.path.join(tasks_dir, "002_feature.md"), "w", encoding="utf-8") as f:
                f.write(task_002_content)

            tasks = [
                {"id": "001", "title": "Init Project", "depends_on": [], "status": "PENDING"},
                {"id": "002", "title": "Build Feature", "depends_on": ["001"], "status": "PENDING"},
            ]
            
            # Initialize DAG with root cwd set to tmpdir
            dag = TaskDAG(tasks, root_dir=tmpdir)

            # Check that 001 is COMPLETED and 002 is PENDING dynamically loaded from files
            self.assertEqual(dag.get_status("001"), "COMPLETED")
            self.assertEqual(dag.get_status("002"), "PENDING")

            # Check that 002 is ready since 001 is COMPLETED
            ready = dag.get_ready_tasks()
            self.assertEqual(len(ready), 1)
            self.assertEqual(ready[0]["id"], "002")

    def test_graph_structure(self):
        tasks = [
            {"id": "001", "title": "Task 1", "depends_on": []},
            {"id": "002", "title": "Task 2", "depends_on": ["001"]},
        ]
        dag = TaskDAG(tasks, root_dir="/non_existent_dir")
        structure = dag.get_graph_structure()
        self.assertEqual(structure["001"], [])
        self.assertEqual(structure["002"], ["001"])

if __name__ == "__main__":
    unittest.main()
