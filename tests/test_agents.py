import unittest
import os
from unittest.mock import patch, MagicMock
from devflow.agents.profiles import load_agent_profile

class TestAgentProfiles(unittest.TestCase):
    def test_load_agent_profile_defaults(self):
        profile = load_agent_profile("reviewer")
        self.assertEqual(profile.role, "reviewer")
        self.assertTrue(profile.max_input_tokens > 0)
        self.assertIn("qwen2.5-coder", profile.preferred_model)

    def test_load_agent_profile_env_override(self):
        with patch.dict(os.environ, {"LOCAL_AI_PROFILE": "mini-fast"}):
            profile = load_agent_profile("reviewer")
            self.assertEqual(profile.preferred_model, "qwen2.5-coder:7b-instruct")

        with patch.dict(os.environ, {"LOCAL_AI_PROFILE": "baseline"}):
            profile = load_agent_profile("reviewer")
            self.assertEqual(profile.preferred_model, "qwen2.5-coder:1.5b")

class TestOllamaAdapter(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_invoke_local_model_mock_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.__iter__.return_value = [b'{"response": "{\\"status\\": \\"approved\\"}"}']
        mock_urlopen.return_value.__enter__.return_value = mock_response

        from devflow.agents.ollama import invoke_local_model
        res = invoke_local_model(
            model="qwen2.5-coder:14b",
            system_instruction="You are a reviewer",
            prompt="Hello",
            temperature=0.2,
            json_mode=True
        )
        self.assertIn("approved", res)


class TestJSONRepair(unittest.TestCase):
    def test_repair_clean_json(self):
        from devflow.agents.schemas import repair_and_parse_json
        data = repair_and_parse_json('{"status": "ready"}')
        self.assertEqual(data["status"], "ready")

    def test_repair_markdown_wrapped_json(self):
        from devflow.agents.schemas import repair_and_parse_json
        raw = "```json\n{\n  \"status\": \"ready\"\n}\n```"
        data = repair_and_parse_json(raw)
        self.assertEqual(data["status"], "ready")

    def test_repair_truncated_json(self):
        from devflow.agents.schemas import repair_and_parse_json
        # Unterminated string inside diff, unclosed brackets/braces
        raw = '{"status": "ready", "diff": "diff --git a/a b/a\\n+added line'
        data = repair_and_parse_json(raw)
        self.assertEqual(data["status"], "ready")
        self.assertEqual(data["diff"], "diff --git a/a b/a\n+added line")

