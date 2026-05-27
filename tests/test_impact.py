import unittest
import tempfile
import os
import shutil
from unittest.mock import patch, MagicMock
from devflow.impact import analyze_impact, get_imports_for_file, get_co_mutations, calculate_risk

class TestImpact(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.tmpdir)

        # Create mock source code files to test imports and references
        os.makedirs("src/devflow")
        os.makedirs("tests")

        with open("src/devflow/states.py", "w", encoding="utf-8") as f:
            f.write("def validate_transition():\n    return True\n")

        with open("src/devflow/cli.py", "w", encoding="utf-8") as f:
            f.write("from devflow.states import validate_transition\n")

        with open("src/devflow/runner.py", "w", encoding="utf-8") as f:
            f.write("import devflow.states\n")

        with open("tests/test_states.py", "w", encoding="utf-8") as f:
            f.write("import unittest\nfrom devflow.states import validate_transition\n")

        # Mock a task file
        self.task_content = """# Task: 042 - Test Impact
Status: PENDING

## 2. Allowed Files
- src/devflow/states.py

## 7. Verification Commands
- PYTHONPATH=src .venv/bin/python -m unittest tests.test_states
"""
        with open("task_042.md", "w", encoding="utf-8") as f:
            f.write(self.task_content)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmpdir)

    def test_get_imports_for_file(self):
        # Scan who imports states.py
        imported_by = get_imports_for_file("src/devflow/states.py", "src")
        # cli.py and runner.py should import states.py
        basenames = [os.path.basename(p) for p in imported_by]
        self.assertIn("cli.py", basenames)
        self.assertIn("runner.py", basenames)

    @patch("subprocess.run")
    def test_get_co_mutations(self, mock_run):
        # Mock git log output showing that cli.py and states.py committed together
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "src/devflow/states.py\nsrc/devflow/cli.py\n\nsrc/devflow/states.py\nsrc/devflow/runner.py\n"
        mock_run.return_value = mock_proc

        co_mutated = get_co_mutations("src/devflow/states.py", cwd=self.tmpdir)
        self.assertIn("src/devflow/cli.py", co_mutated)
        self.assertIn("src/devflow/runner.py", co_mutated)

    def test_calculate_risk(self):
        # Low risk: 1 file, no imports, low file count
        risk_low, score_low = calculate_risk(["src/devflow/states.py"], import_count=0, protected_paths=[])
        self.assertEqual(risk_low, "LOW")

        # Medium risk: multiple files, several imports
        risk_med, score_med = calculate_risk(["src/devflow/states.py", "src/devflow/cli.py"], import_count=3, protected_paths=[])
        self.assertEqual(risk_med, "MEDIUM")

        # High risk: protected path affected (e.g. config/setup)
        risk_high, score_high = calculate_risk(["src/config.py"], import_count=1, protected_paths=["src/config.py"])
        self.assertEqual(risk_high, "HIGH")

    @patch("subprocess.run")
    def test_analyze_impact_full_report(self, mock_run):
        # Mock git log output
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "src/devflow/states.py\nsrc/devflow/cli.py\n"
        mock_run.return_value = mock_proc

        report = analyze_impact("task_042.md", cwd=self.tmpdir)
        
        self.assertEqual(report["task_id"], "042")
        self.assertEqual(report["risk_level"], "LOW")
        self.assertIn("src/devflow/states.py", report["allowed_files"])
        self.assertIn("tests/test_states.py", report["verification_targets"])
        self.assertIn("src/devflow/cli.py", report["public_interface_usages"])

        # Splits check: since count of allowed files is 1, split should not be recommended
        self.assertFalse(report["suggests_split"])

if __name__ == "__main__":
    unittest.main()
