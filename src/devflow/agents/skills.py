"""
devflow.agents.skills
~~~~~~~~~~~~~~~~~~~~~
Resolves Devflow/Superpowers skill names to their SKILL.md content for injection
into local model system prompts.

Resolution order (first match per skill wins):
  1. <cwd>/.devflow/skills/<name>/SKILL.md         — repo-local custom skills
  2. ~/.gemini/config/skills/<name>/SKILL.md        — Antigravity user-global skills
  3. ~/.config/superpowers/skills/<name>/SKILL.md   — Superpowers fallback

Skills that cannot be resolved are silently skipped with a stderr warning.
"""

from __future__ import annotations

import os
import sys
from typing import List


def _candidate_paths(skill_name: str, cwd: str) -> List[str]:
    """Return ordered list of filesystem paths to try for a given skill name."""
    home = os.path.expanduser("~")
    return [
        # 1. Repo-local devflow skill
        os.path.join(cwd, ".devflow", "skills", skill_name, "SKILL.md"),
        # 2. Antigravity user-global skill (flat name)
        os.path.join(home, ".gemini", "config", "skills", skill_name, "SKILL.md"),
        # 3. Superpowers fallback
        os.path.join(home, ".config", "superpowers", "skills", skill_name, "SKILL.md"),
    ]


def _read_skill(skill_name: str, cwd: str) -> str | None:
    """Read and return the content of a single skill file, or None if not found."""
    for path in _candidate_paths(skill_name, cwd):
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    return handle.read()
            except OSError as exc:
                print(
                    f"[skills] Warning: found {path} but could not read it: {exc}",
                    file=sys.stderr,
                )
    return None


def load_skill_content(skill_names: List[str], cwd: str = ".") -> str:
    """
    Load and format the content of one or more skills for system-prompt injection.

    Returns a single string block containing all found skills, formatted as:

        === SKILL: <name> ===
        <skill content>
        === END SKILL: <name> ===

    Skills that are not found on the filesystem are skipped (a warning is printed
    to stderr so the orchestrator can detect missing skills).

    Args:
        skill_names: List of skill names to load (e.g. ["frontend-design", "design-spells"]).
        cwd:         Working directory used as the root for repo-local skill resolution.

    Returns:
        Formatted string of all found skill contents, or empty string if none found.
    """
    cwd = os.path.abspath(cwd)
    if not skill_names:
        return ""

    blocks: List[str] = []
    for name in skill_names:
        content = _read_skill(name, cwd)
        if content is None:
            print(
                f"[skills] Warning: skill '{name}' not found in any resolution path. "
                f"Tried: {_candidate_paths(name, cwd)}",
                file=sys.stderr,
            )
            continue
        # Strip YAML frontmatter (--- ... ---) to keep only the instructional body
        stripped = _strip_frontmatter(content)
        blocks.append(
            f"=== SKILL: {name} ===\n{stripped.strip()}\n=== END SKILL: {name} ==="
        )

    return "\n\n".join(blocks)


def _strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter delimited by '---' lines from skill content."""
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return content
    # Find closing ---
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "".join(lines[i + 1:])
    return content
