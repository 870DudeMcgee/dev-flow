import unittest
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from devflow.agents.profiles import AgentProfile, load_agent_profile

class TestAgentProfiles(unittest.TestCase):
    def test_load_agent_profile_defaults(self):
        profile = load_agent_profile("reviewer")
        self.assertEqual(profile.role, "reviewer")
        self.assertTrue(profile.max_input_tokens > 0)
        self.assertIn("qwen2.5-coder", profile.preferred_model)

class TestOllamaAdapter(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_invoke_local_model_mock_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"response": "{\\"status\\": \\"approved\\"}"}'
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

