import pathlib
import unittest


class TestMVPBoundaries(unittest.TestCase):
    def test_cli_does_not_call_model_provider_modules(self):
        cli_source = pathlib.Path("src/devflow/cli.py").read_text(encoding="utf-8")

        forbidden_fragments = [
            "call_gemini",
            "call_ollama",
            "devflow.orchestrator",
            "urllib.request",
            "GEMINI_API_KEY",
        ]
        for fragment in forbidden_fragments:
            self.assertNotIn(fragment, cli_source)


if __name__ == "__main__":
    unittest.main()
