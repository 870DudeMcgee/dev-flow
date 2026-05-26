import unittest
import os
import shutil
import tempfile
import sys
from devflow.cli import main

class TestCLI(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for isolation
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    def test_cli_init_creates_devflow_folder(self):
        # Call the CLI init logic
        from devflow.cli import init_workspace
        init_workspace()
        
        self.assertTrue(os.path.exists(".devflow"))
        self.assertTrue(os.path.exists(".devflow/config.json"))
        self.assertTrue(os.path.exists(".devflow/tasks"))

if __name__ == "__main__":
    unittest.main()
