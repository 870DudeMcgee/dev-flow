import os
import unittest

class TestDevModeContract(unittest.TestCase):
    def setUp(self):
        # The root of the DevMode clone relative to this test file.
        # This test file is scratch/DevMode/tests/test_devmode_contract.py
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_files_exist(self):
        expected_files = [
            os.path.join("docs", "devmode-contract.md"),
            "README.md",
            "AGENTS.md",
            os.path.join("skills", "using-devmode", "SKILL.md")
        ]
        for f in expected_files:
            full_path = os.path.join(self.base_dir, f)
            self.assertTrue(os.path.isfile(full_path), f"File {f} does not exist at {full_path}")

    def test_readme_links_to_contract(self):
        readme_path = os.path.join(self.base_dir, "README.md")
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("docs/devmode-contract.md", content, "README.md does not link to docs/devmode-contract.md")

    def test_agents_links_to_contract(self):
        agents_path = os.path.join(self.base_dir, "AGENTS.md")
        with open(agents_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("docs/devmode-contract.md", content, "AGENTS.md does not link to docs/devmode-contract.md")

    def test_contract_mentions_four_gates(self):
        contract_path = os.path.join(self.base_dir, "docs", "devmode-contract.md")
        with open(contract_path, "r", encoding="utf-8") as f:
            content = f.read()
        gates = [
            "Mode Gate",
            "Context Gate",
            "Change Gate",
            "Verification Gate"
        ]
        for gate in gates:
            self.assertIn(gate, content, f"docs/devmode-contract.md does not mention gate: {gate}")

    def test_contract_contains_handoff_headings(self):
        contract_path = os.path.join(self.base_dir, "docs", "devmode-contract.md")
        with open(contract_path, "r", encoding="utf-8") as f:
            content = f.read()
        headings = [
            "## Status",
            "## Files Changed",
            "## Verification",
            "## Risks",
            "## Next Safe Action"
        ]
        for heading in headings:
            self.assertIn(heading, content, f"docs/devmode-contract.md does not contain heading: {heading}")

    def test_agents_contains_handoff_headings(self):
        agents_path = os.path.join(self.base_dir, "AGENTS.md")
        with open(agents_path, "r", encoding="utf-8") as f:
            content = f.read()
        headings = [
            "## Status",
            "## Files Changed",
            "## Verification",
            "## Risks",
            "## Next Safe Action"
        ]
        for heading in headings:
            self.assertIn(heading, content, f"AGENTS.md is missing heading: {heading}")

    def test_unsafe_phrases_absent(self):
        unsafe_phrases = [
            "delete the non-compliant work",
            "apologize",
            "start over",
            "override default system prompt",
            "override system prompt",
            "you do not have a choice"
        ]
        authority_files = [
            "README.md",
            "AGENTS.md",
            os.path.join("docs", "devmode-contract.md"),
            os.path.join("skills", "using-devmode", "SKILL.md")
        ]
        for f in authority_files:
            full_path = os.path.join(self.base_dir, f)
            with open(full_path, "r", encoding="utf-8") as file_obj:
                content = file_obj.read().lower()
            for phrase in unsafe_phrases:
                self.assertNotIn(phrase, content, f"Forbidden phrase '{phrase}' found in {f}")

    def test_contract_mentions_instruction_priority(self):
        contract_path = os.path.join(self.base_dir, "docs", "devmode-contract.md")
        with open(contract_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertTrue("priority" in content.lower() or "outrank" in content.lower(),
                        "docs/devmode-contract.md does not mention instruction priority")
        self.assertTrue("platform" in content.lower() or "system" in content.lower(),
                        "docs/devmode-contract.md does not mention platform or system instructions")

    def test_harness_compatibility(self):
        readme_path = os.path.join(self.base_dir, "README.md")
        compat_path = os.path.join(self.base_dir, "docs", "harness-compatibility.md")
        with open(readme_path, "r", encoding="utf-8") as f:
            readme_content = f.read()
        with open(compat_path, "r", encoding="utf-8") as f:
            compat_content = f.read()
        
        harnesses = ["Claude Code", "Gemini CLI", "Cursor", "Codex", "OpenCode", "VS Code / GitHub Copilot"]
        for h in harnesses:
            self.assertIn(h, readme_content, f"README.md does not mention harness: {h}")
            self.assertIn(h, compat_content, f"docs/harness-compatibility.md does not mention harness: {h}")

if __name__ == "__main__":
    unittest.main()
