import json
import os
import shutil
import tempfile
import unittest

from devflow.cli import init_workspace
from devflow.repo_map import (
    build_repo_map_deps,
    build_repo_map_short,
    build_repo_map_symbols,
    refresh_repo_maps,
)
from tests.helpers import git_commit, git_init


class TestRepoMap(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)
        git_init(os.getcwd())
        os.makedirs("src/devflow", exist_ok=True)
        os.makedirs("tests", exist_ok=True)
        with open("src/devflow/example.py", "w", encoding="utf-8") as handle:
            handle.write(
                '"""Example module."""\n'
                "import json\n"
                "from pathlib import Path\n\n"
                "CONSTANT = 1\n\n"
                "class Example:\n"
                "    \"\"\"Example class.\"\"\"\n"
                "    def method(self):\n"
                "        return Path('.')\n\n"
                "def helper():\n"
                "    \"\"\"Return helper value.\"\"\"\n"
                "    return json.dumps({'ok': True})\n"
            )
        with open("tests/test_example.py", "w", encoding="utf-8") as handle:
            handle.write("from devflow.example import helper\n\ndef test_helper():\n    assert helper()\n")
        os.makedirs(".venv", exist_ok=True)
        with open(".venv/ignored.py", "w", encoding="utf-8") as handle:
            handle.write("def ignored():\n    pass\n")
        with open("bad.py", "w", encoding="utf-8") as handle:
            handle.write("def broken(:\n")
        git_commit(os.getcwd(), message="init")
        init_workspace()

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    def test_build_repo_map_short_outputs_markdown(self):
        markdown = build_repo_map_short()

        self.assertIn("# Repository Map", markdown)
        self.assertIn("src/devflow/example.py", markdown)
        self.assertIn("tests/test_example.py", markdown)
        self.assertNotIn(".venv/ignored.py", markdown)

    def test_build_repo_map_symbols_extracts_python_symbols(self):
        symbols = build_repo_map_symbols()
        names = {symbol["name"] for symbol in symbols["symbols"]}

        self.assertIn("Example", names)
        self.assertIn("Example.method", names)
        self.assertIn("helper", names)
        self.assertIn("CONSTANT", names)
        helper = next(symbol for symbol in symbols["symbols"] if symbol["name"] == "helper")
        self.assertEqual(helper["docstring"], "Return helper value.")

    def test_build_repo_map_deps_identifies_imports_and_tests(self):
        deps = build_repo_map_deps()

        self.assertIn("json", deps["files"]["src/devflow/example.py"]["imports"])
        self.assertIn("pathlib", deps["files"]["src/devflow/example.py"]["imports"])
        self.assertIn("tests/test_example.py", deps["files"]["src/devflow/example.py"]["tested_by"])

    def test_refresh_repo_maps_writes_three_files(self):
        refresh_repo_maps()

        self.assertTrue(os.path.exists(".devflow/context/repo-map.short.md"))
        self.assertTrue(os.path.exists(".devflow/context/repo-map.symbols.json"))
        self.assertTrue(os.path.exists(".devflow/context/repo-map.deps.json"))
        with open(".devflow/context/repo-map.symbols.json", "r", encoding="utf-8") as handle:
            self.assertIn("symbols", json.load(handle))

    def test_repo_maps_are_deterministic(self):
        first_symbols = build_repo_map_symbols()
        second_symbols = build_repo_map_symbols()
        first_deps = build_repo_map_deps()
        second_deps = build_repo_map_deps()

        self.assertEqual(first_symbols, second_symbols)
        self.assertEqual(first_deps, second_deps)


if __name__ == "__main__":
    unittest.main()
