import pathlib
import tomllib
import unittest
from importlib import import_module


class TestPackaging(unittest.TestCase):
    def test_pyproject_declares_devflow_cli_entrypoint(self):
        pyproject_path = pathlib.Path("pyproject.toml")
        self.assertTrue(pyproject_path.exists())

        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["name"], "devflow")
        self.assertEqual(data["project"]["readme"], "README.md")
        self.assertEqual(data["project"]["scripts"]["devflow"], "devflow.cli:main")
        self.assertEqual(data["project"]["urls"]["Repository"], "https://github.com/870DudeMcgee/dev-flow")

    def test_package_readme_is_devflow_product_readme(self):
        readme = pathlib.Path("README.md").read_text(encoding="utf-8")

        self.assertEqual(readme.splitlines()[0], "# Dev-Flow")
        self.assertIn("# Dev-Flow", readme)
        self.assertIn("local-first control room", readme)
        self.assertIn("path-isolated, not sandboxed", readme)

    def test_declared_devflow_cli_entrypoint_resolves_to_callable(self):
        data = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))
        module_name, function_name = data["project"]["scripts"]["devflow"].split(":", 1)

        entrypoint = getattr(import_module(module_name), function_name)

        self.assertTrue(callable(entrypoint))


if __name__ == "__main__":
    unittest.main()
