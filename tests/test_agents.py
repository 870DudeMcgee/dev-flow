import unittest
import os
import tempfile
import shutil
from devflow.agents.profiles import AgentProfile, load_agent_profile

class TestAgentProfiles(unittest.TestCase):
    def test_load_agent_profile_defaults(self):
        profile = load_agent_profile("reviewer")
        self.assertEqual(profile.role, "reviewer")
        self.assertTrue(profile.max_input_tokens > 0)
        self.assertIn("qwen2.5-coder", profile.preferred_model)
