import ast
import os
import unittest


class TestArchitectureBoundaries(unittest.TestCase):
    def _check_import(self, filepath, imported_module, forbidden_prefixes, forbidden_top_level_modules):
        # Check forbidden prefixes
        for prefix in forbidden_prefixes:
            if imported_module == prefix or imported_module.startswith(prefix + "."):
                self.fail(
                    f"Architecture violation in {filepath}:\n"
                    f"Active control-room code must not import legacy quarantined code.\n"
                    f"Forbidden import found: {imported_module}\n"
                    f"Active code must be developed strictly inside src/devflow/control_room/ boundaries."
                )

        # Check forbidden top-level modules
        for forbidden in forbidden_top_level_modules:
            if imported_module == forbidden or imported_module.startswith(forbidden + "."):
                self.fail(
                    f"Architecture violation in {filepath}:\n"
                    f"Active control-room code must not import top-level legacy compatibility shims.\n"
                    f"Forbidden import found: {imported_module}\n"
                    f"Active code must be developed strictly inside src/devflow/control_room/ boundaries."
                )

    def test_active_code_does_not_import_legacy_or_shims(self):
        """Active control-room code must not import or depend on legacy or shim modules."""
        active_dir = "src/devflow/control_room"

        forbidden_top_level_modules = {
            "devflow.admin_commands",
            "devflow.agents",
            "devflow.artifacts",
            "devflow.context",
            "devflow.dag",
            "devflow.diagnostics",
            "devflow.editor",
            "devflow.evals",
            "devflow.failures",
            "devflow.impact",
            "devflow.lifecycle_commands",
            "devflow.manager",
            "devflow.memory",
            "devflow.model_gateway",
            "devflow.orchestrator",
            "devflow.orchestrator_agentic",
            "devflow.repo_map",
            "devflow.resource_commands",
            "devflow.runner",
            "devflow.safety",
            "devflow.safety_gate",
            "devflow.states",
            "devflow.task_commands",
            "devflow.trace_eval_commands",
            "devflow.traces",
            "devflow.workspace",
            "devflow.worktree_commands",
            "devflow.worktrees",
        }

        forbidden_prefixes = ("devflow._legacy",)

        for root, dirs, files in os.walk(active_dir):
            for file in files:
                if file.endswith(".py"):
                    filepath = os.path.join(root, file)
                    with open(filepath, "r", encoding="utf-8") as f:
                        source = f.read()

                    try:
                        tree = ast.parse(source, filename=filepath)
                    except SyntaxError as e:
                        self.fail(f"Syntax error parsing {filepath}: {e}")

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                self._check_import(filepath, alias.name, forbidden_prefixes, forbidden_top_level_modules)
                        elif isinstance(node, ast.ImportFrom) and node.module:
                            self._check_import(filepath, node.module, forbidden_prefixes, forbidden_top_level_modules)

    def test_top_level_shims_have_legacy_shim_marker(self):
        """Top-level shim files must be marked as legacy compatibility shims and proxy via sys.modules."""
        devflow_dir = "src/devflow"
        excluded_files = {"__init__.py", "__main__.py", "cli.py"}

        for name in os.listdir(devflow_dir):
            path = os.path.join(devflow_dir, name)
            if os.path.isdir(path):
                continue
            if name in excluded_files or not name.endswith(".py"):
                continue

            # This is a top-level module file, so it must be a compatibility shim
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertTrue(
                "Legacy shim" in content or "sys.modules[__name__]" in content,
                f"File {path} is a top-level module but is not marked as a Legacy compatibility shim.\n"
                f"All top-level devflow modules (except __init__.py, __main__.py, cli.py) must be pure shims proxying to _legacy/."
            )


if __name__ == "__main__":
    unittest.main()
