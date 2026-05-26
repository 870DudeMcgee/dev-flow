import unittest
import os
from devflow.orchestrator import check_gemini_api, call_gemini

class TestOrchestrator(unittest.TestCase):
    def test_check_gemini_api_resolves_env_var(self):
        old_env = os.environ.get("GEMINI_API_KEY")
        try:
            os.environ["GEMINI_API_KEY"] = "mock-key-value"
            self.assertEqual(check_gemini_api(), "mock-key-value")
        finally:
            if old_env is not None:
                os.environ["GEMINI_API_KEY"] = old_env
            else:
                os.environ.pop("GEMINI_API_KEY", None)

    def test_call_gemini_handles_missing_api_key(self):
        result = call_gemini("System", "Prompt", "")
        self.assertIn("Orchestrator error: API key missing", result)

if __name__ == "__main__":
    unittest.main()
