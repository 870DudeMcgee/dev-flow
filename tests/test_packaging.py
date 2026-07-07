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
        self.assertEqual(
            data["project"]["description"],
            "A local operating layer for turning ideas into verified product implementations.",
        )
        self.assertEqual(data["project"]["readme"], "README.md")
        self.assertEqual(data["project"]["scripts"]["devflow"], "devflow.cli:main")
        self.assertEqual(data["project"]["urls"]["Repository"], "https://github.com/870DudeMcgee/dev-flow")

    def test_package_readme_is_devflow_product_readme(self):
        readme = pathlib.Path("README.md").read_text(encoding="utf-8")

        self.assertEqual(readme.splitlines()[0], "# DevFlow")
        self.assertIn("local operating layer", readme)
        self.assertIn("verified product implementations", readme)
        self.assertIn("docs/DEVFLOW_SOURCE_OF_TRUTH.md", readme)
        self.assertIn("Idea -> Brainstorm -> Spec -> Plan -> Judge -> Build -> Judge -> Verify", readme)
        retired_phrase = "local-" + "first " + "control " + "room for parallel AI coding " + "workers"
        retired_mvp_doc = "docs/" + "control-" + "room-mvp.md"
        retired_north_star = "PRODUCT_" + "NORTH_STAR.md"
        self.assertNotIn(retired_phrase, readme)
        self.assertNotIn(retired_mvp_doc, readme)
        self.assertNotIn(retired_north_star, readme)

    def test_declared_devflow_cli_entrypoint_resolves_to_callable(self):
        data = tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))
        module_name, function_name = data["project"]["scripts"]["devflow"].split(":", 1)

        entrypoint = getattr(import_module(module_name), function_name)

        self.assertTrue(callable(entrypoint))


if __name__ == "__main__":
    unittest.main()
