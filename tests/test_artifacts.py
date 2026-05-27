import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from devflow.artifacts import (
    artifact_body_path,
    find_artifact,
    generate_artifact_id,
    list_artifacts,
    read_artifact,
    sha256_text,
    touched_paths_from_diff,
    validate_artifact_metadata,
    write_artifact,
)
from devflow.cli import init_workspace, main


class TestArtifacts(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.test_dir)
        os.system("git init > /dev/null 2>&1")
        os.system("git config user.email 'tests@example.com'")
        os.system("git config user.name 'Devflow Tests'")
        with open("sample.txt", "w", encoding="utf-8") as handle:
            handle.write("hello\n")
        os.system("git add sample.txt")
        os.system("git commit -m 'init' > /dev/null 2>&1")
        init_workspace()

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.test_dir)

    def test_write_and_read_artifact_preserves_metadata_and_body(self):
        record = write_artifact(
            task_id="T-042",
            artifact_type="implementation.diff",
            body="diff --git a/sample.txt b/sample.txt\n",
            role="implementer",
            input_text="task packet",
            parent_artifacts=["task:T-042"],
            allowed_paths=["sample.txt"],
            touched_paths=["sample.txt"],
            risk="medium",
            confidence=0.72,
            metadata={"note": "first slice"},
        )

        metadata, body = read_artifact(record.metadata_path)

        self.assertEqual(body, "diff --git a/sample.txt b/sample.txt\n")
        self.assertEqual(metadata["task_id"], "T-042")
        self.assertEqual(metadata["artifact_type"], "implementation.diff")
        self.assertEqual(metadata["role"], "implementer")
        self.assertEqual(metadata["parent_artifacts"], ["task:T-042"])
        self.assertEqual(metadata["allowed_paths"], ["sample.txt"])
        self.assertEqual(metadata["touched_paths"], ["sample.txt"])
        self.assertEqual(metadata["metadata"], {"note": "first slice"})
        self.assertTrue(os.path.exists(record.body_path))
        self.assertTrue(os.path.exists(record.metadata_path))

    def test_output_hash_matches_artifact_body(self):
        body = "review body\n"
        record = write_artifact("T-001", "review.json", body, role="reviewer")

        metadata, _ = read_artifact(record.metadata_path)

        self.assertEqual(metadata["output_hash"], sha256_text(body))

    def test_artifact_metadata_contract_is_validated(self):
        record = write_artifact("T-001", "review.json", "body", role="reviewer")
        metadata = dict(record.metadata)
        metadata.pop("output_hash")

        with self.assertRaises(ValueError):
            validate_artifact_metadata(metadata)

    def test_read_artifact_detects_body_corruption(self):
        record = write_artifact("T-001", "review.json", "clean body", role="reviewer")
        with open(record.body_path, "w", encoding="utf-8") as handle:
            handle.write("corrupted body")

        with self.assertRaises(ValueError):
            read_artifact(record.metadata_path)

    def test_artifact_id_is_deterministic_for_same_timestamp_and_seed(self):
        first = generate_artifact_id("2026-05-27T15:30:12+00:00", "same seed")
        second = generate_artifact_id("2026-05-27T15:30:12+00:00", "same seed")
        third = generate_artifact_id("2026-05-27T15:30:12+00:00", "different seed")

        self.assertEqual(first, second)
        self.assertNotEqual(first, third)
        self.assertTrue(first.startswith("art_20260527153012_"))

    def test_list_artifacts_returns_sequence_order(self):
        third = write_artifact("T-100", "review.json", "third", role="reviewer")
        first = write_artifact("T-100", "task.snapshot.md", "first", role="planner")
        second = write_artifact("T-100", "context-pack.json", "second", role="cartographer")

        records = list_artifacts("T-100")

        self.assertEqual([record.sequence for record in records], [1, 2, 3])
        self.assertEqual([record.metadata["artifact_id"] for record in records], [third.artifact_id, first.artifact_id, second.artifact_id])

    def test_find_artifact_resolves_id_metadata_path_and_body_path(self):
        record = write_artifact("T-200", "review.json", "body", role="reviewer")

        self.assertEqual(find_artifact(record.artifact_id).metadata_path, record.metadata_path)
        self.assertEqual(find_artifact(record.metadata_path).metadata_path, record.metadata_path)
        self.assertEqual(find_artifact(record.body_path).metadata_path, record.metadata_path)

    def test_touched_paths_from_diff_headers(self):
        diff = """diff --git a/src/devflow/runner.py b/src/devflow/runner.py
--- a/src/devflow/runner.py
+++ b/src/devflow/runner.py
@@ -1 +1 @@
-old
+new
diff --git a/tests/test_runner.py b/tests/test_runner.py
--- a/tests/test_runner.py
+++ b/tests/test_runner.py
@@ -1 +1 @@
-old
+new
"""

        self.assertEqual(
            touched_paths_from_diff(diff),
            ["src/devflow/runner.py", "tests/test_runner.py"],
        )

    @unittest.skip("legacy artifact CLI is outside the control-room MVP")
    def test_cli_artifact_list_and_inspect(self):
        record = write_artifact("T-300", "review.json", '{"status":"approved"}', role="reviewer")
        old_argv = sys.argv
        try:
            list_buffer = io.StringIO()
            sys.argv = ["devflow", "artifact", "list", "T-300"]
            with redirect_stdout(list_buffer):
                main()
            list_output = list_buffer.getvalue()

            inspect_buffer = io.StringIO()
            sys.argv = ["devflow", "artifact", "inspect", record.artifact_id]
            with redirect_stdout(inspect_buffer):
                main()
            inspect_output = inspect_buffer.getvalue()
        finally:
            sys.argv = old_argv

        self.assertIn(record.artifact_id, list_output)
        self.assertIn("review.json", list_output)
        self.assertIn("artifact_id", inspect_output)
        self.assertIn(record.body_path, inspect_output)
        self.assertIn("sha256:", inspect_output)

    def test_artifact_body_path_resolves_from_metadata_path(self):
        record = write_artifact("T-400", "verification.log", "ok", role="verifier")

        self.assertEqual(artifact_body_path(record.metadata_path), record.body_path)


class TestArtifactSchema(unittest.TestCase):
    def test_artifact_schema_file_exists_and_requires_core_fields(self):
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "src",
            "devflow",
            "schemas",
            "artifact.schema.json",
        )
        with open(schema_path, "r", encoding="utf-8") as handle:
            schema = json.load(handle)

        self.assertIn("artifact_id", schema["required"])
        self.assertIn("task_id", schema["required"])
        self.assertIn("output_hash", schema["required"])
        self.assertIn("body_path", schema["required"])


if __name__ == "__main__":
    unittest.main()
