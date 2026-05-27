import unittest
import tempfile
import os
from devflow.states import validate_transition, execute_recipe

class TestStates(unittest.TestCase):
    def test_validate_transition(self):
        # Allowed transitions
        self.assertTrue(validate_transition("PENDING", "RED"))
        self.assertTrue(validate_transition("PENDING", "GREEN"))
        self.assertTrue(validate_transition("PENDING", "BLOCKED"))
        self.assertTrue(validate_transition("PENDING", "FAILED"))

        self.assertTrue(validate_transition("RED", "GREEN"))
        self.assertTrue(validate_transition("RED", "BLOCKED"))

        self.assertTrue(validate_transition("GREEN", "REFACTOR"))
        self.assertTrue(validate_transition("GREEN", "REPORT"))

        self.assertTrue(validate_transition("REFACTOR", "REPORT"))
        
        self.assertTrue(validate_transition("BLOCKED", "PENDING"))
        self.assertTrue(validate_transition("FAILED", "PENDING"))

        # Case insensitivity
        self.assertTrue(validate_transition("pending", "red"))
        self.assertTrue(validate_transition("Pending", "Green"))

        # Invalid transitions
        self.assertFalse(validate_transition("PENDING", "REFACTOR"))
        self.assertFalse(validate_transition("PENDING", "REPORT"))
        self.assertFalse(validate_transition("RED", "REFACTOR"))
        self.assertFalse(validate_transition("RED", "REPORT"))
        self.assertFalse(validate_transition("GREEN", "PENDING"))
        self.assertFalse(validate_transition("REPORT", "PENDING"))
        self.assertFalse(validate_transition("REPORT", "RED"))

    def test_execute_recipe_expected_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Expected pass, exits 0
            recipe = {"command": "echo 'hello'", "expected": "pass"}
            res = execute_recipe(recipe, tmpdir)
            self.assertTrue(res["success"])
            self.assertEqual(res["exit_code"], 0)
            self.assertIn("hello", res["stdout"])

            # Expected pass, exits non-0
            recipe_fail = {"command": "false", "expected": "pass"}
            res_fail = execute_recipe(recipe_fail, tmpdir)
            self.assertFalse(res_fail["success"])
            self.assertNotEqual(res_fail["exit_code"], 0)
            self.assertIn("failed unexpectedly", res_fail["message"])

    def test_execute_recipe_expected_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Expected fail, exits non-0
            recipe = {"command": "false", "expected": "fail"}
            res = execute_recipe(recipe, tmpdir)
            self.assertTrue(res["success"])
            self.assertNotEqual(res["exit_code"], 0)

            # Expected fail, exits 0 (should report failure)
            recipe_pass = {"command": "true", "expected": "fail"}
            res_pass = execute_recipe(recipe_pass, tmpdir)
            self.assertFalse(res_pass["success"])
            self.assertEqual(res_pass["exit_code"], 0)
            self.assertIn("Expected command to fail", res_pass["message"])

    def test_execute_recipe_expected_fail_regex(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Expected fail, exits non-0, regex matches
            recipe = {
                "command": "echo 'error: NameError occurred' >&2; exit 1",
                "expected": "fail",
                "failure_must_contain": "NameError"
            }
            res = execute_recipe(recipe, tmpdir)
            self.assertTrue(res["success"])
            self.assertNotEqual(res["exit_code"], 0)

            # Expected fail, exits non-0, regex does NOT match
            recipe_wrong = {
                "command": "echo 'error: TypeError occurred' >&2; exit 1",
                "expected": "fail",
                "failure_must_contain": "NameError"
            }
            res_wrong = execute_recipe(recipe_wrong, tmpdir)
            self.assertFalse(res_wrong["success"])
            self.assertNotEqual(res_wrong["exit_code"], 0)
            self.assertIn("Expected failure message regex", res_wrong["message"])

    def test_execute_recipe_optional_if_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Optional command that is missing (non_existent_command_xyz)
            recipe = {
                "command": "non_existent_command_xyz --version",
                "expected": "pass",
                "optional_if_missing": True
            }
            res = execute_recipe(recipe, tmpdir)
            self.assertTrue(res["success"])
            self.assertEqual(res["exit_code"], 0)
            self.assertIn("skipped (optional and missing)", res["message"])

            # Optional command that is present (e.g. echo)
            recipe_present = {
                "command": "echo 'hello'",
                "expected": "pass",
                "optional_if_missing": True
            }
            res_present = execute_recipe(recipe_present, tmpdir)
            self.assertTrue(res_present["success"])
            self.assertEqual(res_present["exit_code"], 0)
            self.assertIn("hello", res_present["stdout"])

if __name__ == "__main__":
    unittest.main()
