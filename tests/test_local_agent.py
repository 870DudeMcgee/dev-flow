import unittest
from unittest.mock import patch, MagicMock
import urllib.error
from scripts.local_agent_runner import generate_text

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
