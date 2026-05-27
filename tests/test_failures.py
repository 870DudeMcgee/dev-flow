import unittest
from devflow.failures import classify_failure, serialize_failure

class TestFailures(unittest.TestCase):
    def test_classify_patch_failure(self):
        self.assertEqual(classify_failure("patch", "some error"), "PATCH_APPLY_FAILURE")

    def test_classify_syntax_error(self):
        self.assertEqual(classify_failure("verification", "SyntaxError: invalid syntax"), "SYNTAX_ERROR")

    def test_classify_import_error(self):
        self.assertEqual(classify_failure("verification", "ModuleNotFoundError: No module named 'foo'"), "IMPORT_ERROR")
        self.assertEqual(classify_failure("verification", "ImportError: cannot import name 'bar'"), "IMPORT_ERROR")

    def test_classify_lint_failure(self):
        self.assertEqual(classify_failure("verification", "ruff failed"), "LINT_FAILURE")

    def test_classify_type_error(self):
        self.assertEqual(classify_failure("verification", "TypeError: list indices must be integers"), "TYPE_ERROR")

    def test_classify_test_failure(self):
        self.assertEqual(classify_failure("verification", "FAILED (failures=1)"), "TEST_FAILURE")

    def test_classify_unknown(self):
        self.assertEqual(classify_failure("verification", "something completely random"), "UNKNOWN_FAILURE")

    def test_serialize_failure(self):
        serialized = serialize_failure("verification", "SyntaxError: invalid syntax", "pytest")
        self.assertEqual(serialized["stage"], "verification")
        self.assertEqual(serialized["classification"], "SYNTAX_ERROR")
        self.assertEqual(serialized["command"], "pytest")
        self.assertEqual(serialized["output"], "SyntaxError: invalid syntax")
