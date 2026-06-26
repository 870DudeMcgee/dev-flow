import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import os
from scripts.local_agent_runner import generate_text, get_selected_model

class TestLocalAgentRunner(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_generate_text_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"response": "hello mock world"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = generate_text("test prompt")
        self.assertEqual(res, "hello mock world")

    @patch("urllib.request.urlopen")
    def test_generate_text_failure(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        with self.assertRaises(SystemExit):
            generate_text("test prompt")

    def test_get_selected_model_defaults(self):
        # When sysconf fails or is not available, it should fallback to baseline
        with patch.dict(os.environ, {}, clear=True):
            with patch("os.sysconf", side_effect=Exception("not supported")):
                model, profile = get_selected_model()
                self.assertEqual(profile, "baseline (auto-detected)")
                self.assertEqual(model, "qwen2.5-coder:1.5b")

    def test_get_selected_model_auto_detection(self):
        # Clear env var to trigger auto-detection
        with patch.dict(os.environ, {}, clear=True):
            # Mock os.sysconf to simulate 64 GB RAM -> studio
            with patch("os.sysconf", side_effect=lambda name: 64 * 1024 * 1024 * 1024 if name == "SC_PHYS_PAGES" else (1 if name == "SC_PAGE_SIZE" else 0)):
                model, profile = get_selected_model()
                self.assertEqual(profile, "studio (auto-detected)")
                self.assertEqual(model, "qwen2.5-coder:32b-instruct")

            # Mock os.sysconf to simulate 16 GB RAM -> mini
            with patch("os.sysconf", side_effect=lambda name: 16 * 1024 * 1024 * 1024 if name == "SC_PHYS_PAGES" else (1 if name == "SC_PAGE_SIZE" else 0)):
                model, profile = get_selected_model()
                self.assertEqual(profile, "mini (auto-detected)")
                self.assertEqual(model, "qwen2.5-coder:14b")

            # Mock os.sysconf to simulate 4 GB RAM -> baseline
            with patch("os.sysconf", side_effect=lambda name: 4 * 1024 * 1024 * 1024 if name == "SC_PHYS_PAGES" else (1 if name == "SC_PAGE_SIZE" else 0)):
                model, profile = get_selected_model()
                self.assertEqual(profile, "baseline (auto-detected)")
                self.assertEqual(model, "qwen2.5-coder:1.5b")


    def test_get_selected_model_env_override(self):
        # Using environment variables to select profile
        with patch.dict(os.environ, {"LOCAL_AI_PROFILE": "studio"}):
            model, profile = get_selected_model()
            self.assertEqual(profile, "studio")
            self.assertEqual(model, "qwen2.5-coder:32b-instruct")

        with patch.dict(os.environ, {"LOCAL_AI_PROFILE": "mini"}):
            model, profile = get_selected_model()
            self.assertEqual(profile, "mini")
            self.assertEqual(model, "qwen2.5-coder:14b")

        with patch.dict(os.environ, {"LOCAL_AI_PROFILE": "mini-fast"}):
            model, profile = get_selected_model()
            self.assertEqual(profile, "mini-fast")
            self.assertEqual(model, "qwen2.5-coder:7b-instruct")

    def test_get_selected_model_explicit_profile(self):
        # Passing an explicit profile argument overrides the environment variable
        with patch.dict(os.environ, {"LOCAL_AI_PROFILE": "baseline"}):
            model, profile = get_selected_model("studio")
            self.assertEqual(profile, "studio")
            self.assertEqual(model, "qwen2.5-coder:32b-instruct")

    def test_get_selected_model_custom(self):
        # Specifying a custom model name should return it directly
        model, profile = get_selected_model("llama3:70b")
        self.assertEqual(profile, "custom")
        self.assertEqual(model, "llama3:70b")

    @patch("urllib.request.urlopen")
    def test_generate_text_payload_contains_resolved_model(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"response": "ok"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Test that studio profile sends qwen2.5-coder:32b-instruct
        generate_text("test", profile_name="studio")
        called_args, called_kwargs = mock_urlopen.call_args
        req = called_args[0]
        # Inspect request data
        self.assertIn(b'"model": "qwen2.5-coder:32b-instruct"', req.data)
