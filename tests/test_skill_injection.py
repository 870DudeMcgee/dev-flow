"""
Tests for the skill injection pipeline:
  - parse_task_file() reads the Skills: header
  - build_task_template() emits Skills: block
  - load_skill_content() resolves and returns skill content
  - run_implement_agent() injects skills into the system instruction
"""

import json
import os
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import MagicMock, patch

# Ensure src/ is on the path when running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from devflow.manager import parse_task_file, build_task_template
from devflow.agents.skills import load_skill_content


class TestSkillsParsedFromTaskFile(unittest.TestCase):
    """parse_task_file() must return skills declared in the task header."""

    def _make_task(self, skills_block: str) -> str:
        return textwrap.dedent(f"""\
            # Task: test-001 - Test Task
            Status: PENDING
            {skills_block}

            ## 1. Objective

            Test objective.

            ## 2. Allowed Files

            - public/index.html

            ## 7. Verification Commands

            - true
        """)

    def test_single_skill_parsed(self):
        content = self._make_task("Skills:\n- frontend-design")
        task = parse_task_file(content)
        self.assertIn("frontend-design", task["skills"])

    def test_multiple_skills_parsed(self):
        content = self._make_task("Skills:\n- frontend-design\n- design-spells")
        task = parse_task_file(content)
        self.assertIn("frontend-design", task["skills"])
        self.assertIn("design-spells", task["skills"])
        self.assertEqual(len(task["skills"]), 2)

    def test_no_skills_returns_empty_list(self):
        content = self._make_task("")
        task = parse_task_file(content)
        self.assertEqual(task["skills"], [])

    def test_skills_key_always_present(self):
        """skills must always be in the returned dict even if the header is absent."""
        content = "# Task: test-002 - Minimal\nStatus: PENDING\n\n## 1. Objective\n\nTest.\n"
        task = parse_task_file(content)
        self.assertIn("skills", task)
        self.assertIsInstance(task["skills"], list)


class TestBuildTaskTemplateSkills(unittest.TestCase):
    """build_task_template() must emit a Skills: block in the output."""

    def test_skills_emitted_in_template(self):
        template = build_task_template(
            task_id="test-003",
            title="Test task",
            skills=["frontend-design", "design-spells"],
        )
        self.assertIn("Skills:", template)
        self.assertIn("- frontend-design", template)
        self.assertIn("- design-spells", template)

    def test_empty_skills_still_emits_header(self):
        template = build_task_template(task_id="test-004", title="No skills")
        # Skills: header should be present even if empty
        self.assertIn("Skills:", template)

    def test_round_trip(self):
        """Template output must be parseable and return the same skills."""
        template = build_task_template(
            task_id="test-005",
            title="Round-trip",
            skills=["frontend-design"],
        )
        task = parse_task_file(template)
        self.assertIn("frontend-design", task["skills"])


class TestLoadSkillContent(unittest.TestCase):
    """load_skill_content() must resolve skill files from the filesystem."""

    def test_empty_list_returns_empty_string(self):
        result = load_skill_content([])
        self.assertEqual(result, "")

    def test_repo_local_skill_loaded(self):
        """A skill placed in .devflow/skills/<name>/SKILL.md should be found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, ".devflow", "skills", "test-skill")
            os.makedirs(skill_dir)
            skill_path = os.path.join(skill_dir, "SKILL.md")
            with open(skill_path, "w") as fh:
                fh.write("# Test Skill\n\nDo something magical.\n")

            result = load_skill_content(["test-skill"], cwd=tmpdir)
            self.assertIn("Do something magical.", result)
            self.assertIn("=== SKILL: test-skill ===", result)
            self.assertIn("=== END SKILL: test-skill ===", result)

    def test_frontmatter_stripped(self):
        """YAML frontmatter (--- ... ---) should be removed from skill content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_dir = os.path.join(tmpdir, ".devflow", "skills", "fm-skill")
            os.makedirs(skill_dir)
            with open(os.path.join(skill_dir, "SKILL.md"), "w") as fh:
                fh.write("---\nname: fm-skill\ndescription: Test\n---\n\n# Body\n\nContent here.\n")

            result = load_skill_content(["fm-skill"], cwd=tmpdir)
            self.assertNotIn("name: fm-skill", result)
            self.assertIn("Content here.", result)

    def test_missing_skill_skipped_with_warning(self):
        """Skills not found should be skipped (no exception) and warned to stderr."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import io
            buf = io.StringIO()
            with patch("sys.stderr", buf):
                result = load_skill_content(["nonexistent-skill"], cwd=tmpdir)
            self.assertEqual(result, "")
            self.assertIn("nonexistent-skill", buf.getvalue())

    def test_multiple_skills_concatenated(self):
        """Multiple skills must all appear in the output string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for name, body in [("skill-a", "Alpha content."), ("skill-b", "Beta content.")]:
                d = os.path.join(tmpdir, ".devflow", "skills", name)
                os.makedirs(d)
                with open(os.path.join(d, "SKILL.md"), "w") as fh:
                    fh.write(f"# {name}\n\n{body}\n")

            result = load_skill_content(["skill-a", "skill-b"], cwd=tmpdir)
            self.assertIn("Alpha content.", result)
            self.assertIn("Beta content.", result)


class TestImplementAgentInjectsSkills(unittest.TestCase):
    """run_implement_agent() must pass skill content in the system_instruction to Ollama."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Write a minimal task file with a skill declared
        skill_dir = os.path.join(self.tmpdir, ".devflow", "skills", "test-design")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as fh:
            fh.write("# Test Design Skill\n\nUSE PREMIUM DARK GLASSMORPHISM ONLY.\n")

        task_dir = os.path.join(self.tmpdir, ".devflow", "tasks")
        os.makedirs(task_dir)
        self.task_path = os.path.join(task_dir, "test_task.md")
        with open(self.task_path, "w") as fh:
            fh.write(textwrap.dedent("""\
                # Task: skill-inject-test - Test skill injection
                Status: PENDING
                Skills:
                - test-design

                ## 1. Objective

                Test that skills are injected into the system instruction.

                ## 2. Allowed Files

                - public/index.html

                ## 7. Verification Commands

                - true
            """))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_skill_content_in_system_instruction(self):
        captured_instruction = []

        def mock_invoke(model, system_instruction, prompt, temperature, json_mode):
            captured_instruction.append(system_instruction)
            return json.dumps({
                "status": "ready",
                "diff": "",
                "touched_paths": [],
                "risk": "low",
                "confidence": 1.0,
            })

        # Patch all external dependencies
        with patch("devflow.agents.runner.ollama.invoke_local_model", side_effect=mock_invoke), \
             patch("devflow.agents.runner.build_context_pack") as mock_ctx, \
             patch("devflow.agents.runner.read_artifact") as mock_read, \
             patch("devflow.agents.runner.load_agent_profile") as mock_profile, \
             patch("devflow.agents.runner.write_artifact") as mock_write:

            mock_ctx.return_value = MagicMock(metadata_path="fake/path")
            mock_read.return_value = ("", '{"context": "stub"}')
            mock_profile.return_value = MagicMock(
                role="implementer",
                preferred_model="qwen2.5-coder:14b",
                fallback_models=[],
                temperature=0.0,
            )
            mock_write.return_value = MagicMock()

            from devflow.agents.runner import run_implement_agent
            run_implement_agent(
                os.path.relpath(self.task_path, self.tmpdir),
                cwd=self.tmpdir,
            )

        self.assertTrue(len(captured_instruction) > 0, "Ollama was never called")
        instruction = captured_instruction[0]
        self.assertIn("USE PREMIUM DARK GLASSMORPHISM ONLY.", instruction,
                      "Skill content was not injected into system instruction")
        self.assertIn("=== SKILL: test-design ===", instruction)
        self.assertIn("ANTI-PATTERN BLACKLIST", instruction,
                      "Anti-pattern blacklist missing from system instruction")
        self.assertIn("--bg-dark", instruction,
                      "CSS design tokens missing from system instruction")


if __name__ == "__main__":
    unittest.main()
