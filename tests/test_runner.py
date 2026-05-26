import unittest
from devflow.runner import validate_syntax, call_ollama

class TestRunner(unittest.TestCase):
    def test_validate_syntax_catches_invalid_python(self):
        bad_python = "def fail_syntax(\n"
        self.assertFalse(validate_syntax(bad_python, "file.py"))

    def test_validate_syntax_passes_valid_python(self):
        good_python = "def success():\n    pass\n"
        self.assertTrue(validate_syntax(good_python, "file.py"))

    def test_validate_syntax_ignores_non_python(self):
        js_code = "const a = 1;"
        self.assertTrue(validate_syntax(js_code, "file.js"))

    def test_call_ollama_handles_connection_failure(self):
        # When Ollama is offline or invalid host is provided, it should return an error gracefully
        response = call_ollama("hello", "http://localhost:9999", "mock-model")
        self.assertIn("Error connecting to Ollama", response)

if __name__ == "__main__":
    unittest.main()
