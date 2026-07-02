import ast
from pathlib import Path
import unittest


REMOVED_TOP_LEVEL_MODULES = {
    "admin_commands",
    "artifacts",
    "context",
    "dag",
    "diagnostics",
    "editor",
    "evals",
    "failures",
    "impact",
    "lifecycle_commands",
    "manager",
    "memory",
    "model_gateway",
    "orchestrator",
    "orchestrator_agentic",
    "repo_map",
    "resource_commands",
    "runner",
    "safety",
    "safety_gate",
    "states",
    "task_commands",
    "trace_eval_commands",
    "traces",
    "workspace",
    "worktree_commands",
    "worktrees",
}

ALLOWED_TOP_LEVEL_FILES = {
    "__init__.py",
    "__main__.py",
    "cli.py",
    "df_telegram_bridge.py",
    "df_telegram_gateway_handler.py",
}

FORBIDDEN_IMPORTS = {"devflow._legacy", "devflow.agents"} | {
    f"devflow.{name}" for name in REMOVED_TOP_LEVEL_MODULES
}


def _python_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _is_forbidden_import(imported_module: str) -> bool:
    return any(
        imported_module == forbidden or imported_module.startswith(forbidden + ".")
        for forbidden in FORBIDDEN_IMPORTS
    )


class TestArchitectureBoundaries(unittest.TestCase):
    def test_legacy_runtime_and_pure_shims_are_removed(self):
        devflow_dir = Path("src/devflow")

        self.assertFalse((devflow_dir / "_legacy").exists())
        self.assertFalse((devflow_dir / "agents").exists())
        self.assertFalse((devflow_dir / "schemas").exists())

        for module_name in REMOVED_TOP_LEVEL_MODULES:
            self.assertFalse(
                (devflow_dir / f"{module_name}.py").exists(),
                f"Removed legacy shim still exists: src/devflow/{module_name}.py",
            )

    def test_only_explicit_top_level_python_entrypoints_remain(self):
        devflow_dir = Path("src/devflow")
        top_level_python = {
            path.name
            for path in devflow_dir.glob("*.py")
            if path.is_file()
        }

        self.assertEqual(top_level_python, ALLOWED_TOP_LEVEL_FILES)

    def test_surviving_top_level_modules_do_not_import_legacy_runtime(self):
        for path in Path("src/devflow").glob("*.py"):
            for imported_module in _python_imports(path):
                self.assertFalse(
                    imported_module == "devflow._legacy"
                    or imported_module.startswith("devflow._legacy."),
                    f"{path} imports removed legacy runtime: {imported_module}",
                )

    def test_active_code_does_not_import_removed_legacy_or_shims(self):
        for path in Path("src/devflow/control_room").rglob("*.py"):
            for imported_module in _python_imports(path):
                self.assertFalse(
                    _is_forbidden_import(imported_module),
                    f"{path} imports removed legacy/shim module: {imported_module}",
                )


if __name__ == "__main__":
    unittest.main()
