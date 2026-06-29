import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from devflow.artifacts import list_artifacts, read_artifact
from devflow.cli import init_workspace, main
from devflow.context import build_context_pack, estimate_tokens, inspect_context_pack, list_context_packs
from devflow.repo_map import refresh_repo_maps
from tests.helpers import git_commit, git_init


class TestContextPacks(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)
        git_init(os.getcwd())
        os.makedirs("src/devflow", exist_ok=True)
        os.makedirs("tests", exist_ok=True)
        with open("src/devflow/target.py", "w", encoding="utf-8") as handle:
            handle.write("def target():\n    return 'target'\n")
        with open("src/devflow/other.py", "w", encoding="utf-8") as handle:
            handle.write("def other():\n    return 'other'\n")
        with open("tests/test_target.py", "w", encoding="utf-8") as handle:
            handle.write("from devflow.target import target\n")
        git_commit(os.getcwd(), message="init")
        init_workspace()
        os.makedirs(".devflow/tasks", exist_ok=True)
        self.task_path = ".devflow/tasks/T-042_context.md"
        with open(self.task_path, "w", encoding="utf-8") as handle:
            handle.write("""# Task: T-042 - Build Context
Status: PENDING
Touched Files:
- src/devflow/target.py

## 1. Objective
Build a context pack.

## 2. Allowed Files
- src/devflow/target.py

## 3. Do Not Touch
- src/devflow/other.py

## 4. Required Context
Use the target module.

## 7. Verification Commands
- python -m unittest
""")
        refresh_repo_maps()

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    def test_estimate_tokens_is_reasonable(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("a" * 100), 25)

    def test_build_context_pack_includes_task_contract(self):
        record = build_context_pack(self.task_path, role="reviewer", token_budget=1200)
        metadata, body = read_artifact(record.metadata_path)
        pack = json.loads(body)

        self.assertEqual(metadata["artifact_type"], "context-pack.json")
        self.assertEqual(metadata["role"], "cartographer")
        self.assertEqual(pack["task_id"], "T-042")
        self.assertEqual(pack["role"], "reviewer")
        self.assertIn("Build a context pack", pack["task_contract"]["raw_markdown"])
        self.assertLessEqual(pack["token_estimate"], pack["token_budget"])

    def test_context_pack_respects_allowed_files(self):
        record = build_context_pack(self.task_path, role="implementer", token_budget=1200)
        _, body = read_artifact(record.metadata_path)
        pack = json.loads(body)

        self.assertIn("src/devflow/target.py", pack["relevant_files"])
        self.assertNotIn("src/devflow/other.py", pack["relevant_files"])
        snippet_sources = [section["source"] for section in pack["sections"] if section["name"] == "file_snippet"]
        self.assertEqual(snippet_sources, ["src/devflow/target.py"])

    def test_context_pack_includes_repo_map_and_test_mapping_sections(self):
        record = build_context_pack(self.task_path, role="reviewer", token_budget=2000)
        _, body = read_artifact(record.metadata_path)
        pack = json.loads(body)
        section_names = [section["name"] for section in pack["sections"]]

        self.assertIn("repo_map", section_names)
        self.assertIn("test_mapping", section_names)
        self.assertIn("tests/test_target.py", json.dumps(pack))

    def test_context_pack_is_listed_and_inspectable(self):
        record = build_context_pack(self.task_path, role="reviewer", token_budget=1200)

        packs = list_context_packs("T-042")
        summary = inspect_context_pack(record.artifact_id)

        self.assertEqual(len(packs), 1)
        self.assertEqual(packs[0].artifact_id, record.artifact_id)
        self.assertEqual(summary["context_pack_id"], json.loads(read_artifact(record.metadata_path)[1])["context_pack_id"])
        self.assertEqual(summary["artifact_id"], record.artifact_id)

    @unittest.skip("legacy context CLI is outside the control-room MVP")
    def test_context_cli_refresh_build_inspect_and_list(self):
        old_argv = sys.argv
        try:
            refresh_buffer = io.StringIO()
            sys.argv = ["devflow", "context", "refresh"]
            with redirect_stdout(refresh_buffer):
                main()
            self.assertIn("repo maps refreshed", refresh_buffer.getvalue())

            build_buffer = io.StringIO()
            sys.argv = ["devflow", "context", "build", self.task_path, "--role", "reviewer", "--budget", "1200"]
            with redirect_stdout(build_buffer):
                main()
            build_output = build_buffer.getvalue()
            artifact_id = build_output.split("artifact_id:", 1)[1].strip().splitlines()[0]

            inspect_buffer = io.StringIO()
            sys.argv = ["devflow", "context", "inspect", artifact_id]
            with redirect_stdout(inspect_buffer):
                main()

            list_buffer = io.StringIO()
            sys.argv = ["devflow", "context", "list", "T-042"]
            with redirect_stdout(list_buffer):
                main()
        finally:
            sys.argv = old_argv

        self.assertTrue(os.path.exists(".devflow/context/repo-map.short.md"))
        self.assertIn("context_pack_id", inspect_buffer.getvalue())
        self.assertIn(artifact_id, list_buffer.getvalue())
        self.assertEqual(len(list_artifacts("T-042")), 1)

    def test_build_context_pack_reports_invalid_repo_map_json(self):
        with open(".devflow/context/repo-map.deps.json", "w", encoding="utf-8") as handle:
            handle.write("not json")

        with self.assertRaisesRegex(ValueError, "Context map is invalid JSON"):
            build_context_pack(self.task_path, role="reviewer", token_budget=1200)


if __name__ == "__main__":
    unittest.main()
