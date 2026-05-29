import os
import unittest
from typing import get_args

from devflow.control_room.models import ALLOWED_PERMISSION_MODES, WorkerPermissionMode

class TestWorkerPermissionModes(unittest.TestCase):
    def setUp(self):
        # Base directory of the repository
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_constants_defined(self):
        expected_modes = ["read_only", "workspace_write", "verify_only", "promotion_candidate"]
        
        # Verify ALLOWED_PERMISSION_MODES list has all expected items
        for mode in expected_modes:
            self.assertIn(mode, ALLOWED_PERMISSION_MODES)
            
        self.assertEqual(len(ALLOWED_PERMISSION_MODES), len(expected_modes))

    def test_type_literal_values(self):
        # Extract values defined in the Literal definition of WorkerPermissionMode
        literal_values = get_args(WorkerPermissionMode)
        expected_modes = ["read_only", "workspace_write", "verify_only", "promotion_candidate"]
        
        for mode in expected_modes:
            self.assertIn(mode, literal_values)
            
        self.assertEqual(len(literal_values), len(expected_modes))

    def test_matches_worker_permission_modes_doc(self):
        doc_path = os.path.join(self.base_dir, "docs", "worker-permission-modes.md")
        self.assertTrue(os.path.isfile(doc_path), f"File {doc_path} does not exist")
        
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read().lower()
            
        # Ensure the exact constant names are documented in the worker permission modes doc
        for mode in ALLOWED_PERMISSION_MODES:
            self.assertIn(mode.lower(), content, f"Permission mode '{mode}' is not documented in docs/worker-permission-modes.md")

if __name__ == "__main__":
    unittest.main()
