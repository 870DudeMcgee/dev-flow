import unittest

from hello import build_greeting


class HelloProjectTests(unittest.TestCase):
    def test_default_greeting_names_devflow(self):
        self.assertEqual(build_greeting(), "Hello, Devflow!")

    def test_custom_greeting_strips_name(self):
        self.assertEqual(build_greeting("  VS Code  "), "Hello, VS Code!")


if __name__ == "__main__":
    unittest.main()