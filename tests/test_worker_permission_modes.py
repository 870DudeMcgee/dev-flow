import unittest
from typing import get_args

from devflow.control_room.models import ALLOWED_PERMISSION_MODES, WorkerPermissionMode


class TestWorkerPermissionModes(unittest.TestCase):
    def test_constants_defined(self):
        expected_modes = ["read_only", "workspace_write", "verify_only", "promotion_candidate"]

        for mode in expected_modes:
            self.assertIn(mode, ALLOWED_PERMISSION_MODES)

        self.assertEqual(len(ALLOWED_PERMISSION_MODES), len(expected_modes))

    def test_type_literal_values(self):
        literal_values = get_args(WorkerPermissionMode)
        expected_modes = ["read_only", "workspace_write", "verify_only", "promotion_candidate"]

        for mode in expected_modes:
            self.assertIn(mode, literal_values)

        self.assertEqual(len(literal_values), len(expected_modes))


if __name__ == "__main__":
    unittest.main()
