import unittest
from devflow.safety import scan_diff_for_hazards

class TestSafetyScanner(unittest.TestCase):
    def test_scan_diff_clean(self):
        clean_diff = "+++ b/src/example.py\n+def foo():\n+    return 1\n"
        ok, findings = scan_diff_for_hazards(clean_diff)
        self.assertTrue(ok)
        self.assertEqual(len(findings), 0)

    def test_scan_diff_secrets_violation(self):
        bad_diff = "+++ b/src/config.py\n+API_KEY = 'secret-token-123'\n"
        ok, findings = scan_diff_for_hazards(bad_diff)
        self.assertFalse(ok)
        self.assertTrue(any("secret" in f.lower() for f in findings))

    def test_scan_diff_subprocess_shell_violation(self):
        bad_diff = "+++ b/src/run.py\n+subprocess.Popen(cmd, shell=True)\n"
        ok, findings = scan_diff_for_hazards(bad_diff)
        self.assertFalse(ok)
        self.assertTrue(any("shell" in f.lower() for f in findings))

    def test_scan_diff_exec_violation(self):
        bad_diff = "+++ b/src/runner.py\n+eval('os.system(cmd)')\n"
        ok, findings = scan_diff_for_hazards(bad_diff)
        self.assertFalse(ok)
        self.assertTrue(any("eval" in f.lower() for f in findings))

    def test_scan_diff_socket_violation(self):
        bad_diff = "+++ b/src/network.py\n+s = socket.socket()\n+s.connect(('127.0.0.1', 80))\n"
        ok, findings = scan_diff_for_hazards(bad_diff)
        self.assertFalse(ok)
        self.assertTrue(any("socket" in f.lower() for f in findings))
