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


class TestDiagnostics(unittest.TestCase):
    def test_pytest_adapter_extracts_details(self):
        from devflow.diagnostics import PytestAdapter
        output = (
            "================================== FAILURES ==================================\n"
            "___________________________ test_claim_task_clean ____________________________\n"
            "tests/test_manager.py:290: in test_claim_task_clean\n"
            "    self.assertEqual(status, 'PENDING')\n"
            "E   AssertionError: 'CLAIMED' != 'PENDING'\n"
        )
        adapter = PytestAdapter()
        self.assertTrue(adapter.can_handle(output))
        packet = adapter.parse(output)
        self.assertEqual(packet.classification, "TEST_FAILURE")
        self.assertEqual(packet.file, "tests/test_manager.py")
        self.assertEqual(packet.line, 290)
        self.assertIn("AssertionError", packet.message)

