import pathlib
import tomllib
import unittest


class TestPackaging(unittest.TestCase):
    def test_pyproject_declares_devflow_cli_entrypoint(self):
        pyproject_path = pathlib.Path("pyproject.toml")
        self.assertTrue(pyproject_path.exists())

        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["name"], "devflow")
        self.assertEqual(data["project"]["scripts"]["devflow"], "devflow.cli:main")


if __name__ == "__main__":
    unittest.main()
