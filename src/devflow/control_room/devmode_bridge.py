from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_DEVMODE_SKILLS = (
    "using-devmode",
    "workspace-isolation",
    "using-git-worktrees",
    "finishing-a-development-branch",
    "worker-handoff",
    "verification-before-completion",
)


@dataclass(frozen=True)
class DevModeSkillStatus:
    name: str
    present: bool
    path: str | None


@dataclass(frozen=True)
class DevModeStatus:
    detected: bool
    sources: tuple[str, ...]
    local_devmode_path: str | None
    skills: tuple[DevModeSkillStatus, ...]
    task_packets_reference_devmode: bool


def detect_devmode(root: Path) -> DevModeStatus:
    repo_root = root.resolve()
    local_devmode = repo_root / ".devmode"
    sources: list[str] = []
    if local_devmode.exists():
        sources.append(_relative(repo_root, local_devmode))
    if (repo_root / "skills" / "using-devmode" / "SKILL.md").exists():
        sources.append("skills/")
    if (repo_root / ".github" / "prompts" / "devmode.prompt.md").exists():
        sources.append(".github/prompts/devmode.prompt.md")

    skills = tuple(_skill_status(repo_root, name) for name in REQUIRED_DEVMODE_SKILLS)
    detected = bool(sources) or any(skill.present for skill in skills)
    return DevModeStatus(
        detected=detected,
        sources=tuple(dict.fromkeys(sources)),
        local_devmode_path=_relative(repo_root, local_devmode) if local_devmode.exists() else None,
        skills=skills,
        task_packets_reference_devmode=task_packets_reference_devmode(),
    )


def devmode_status_dict(root: Path) -> dict[str, Any]:
    status = detect_devmode(root)
    return {
        "detected": status.detected,
        "sources": list(status.sources),
        "local_devmode_path": status.local_devmode_path,
        "skills": [
            {"name": skill.name, "present": skill.present, "path": skill.path}
            for skill in status.skills
        ],
        "task_packets_reference_devmode": status.task_packets_reference_devmode,
    }


def task_packets_reference_devmode() -> bool:
    return True


def devmode_discipline_lines(root: Path | None = None) -> list[str]:
    status = detect_devmode(root or Path.cwd())
    skill_refs = []
    for skill in status.skills:
        if skill.path:
            skill_refs.append(f"{skill.name}: {skill.path}")
        else:
            skill_refs.append(f"{skill.name}: missing")
    return [
        "DevFlow workflow discipline:",
        "Before modifying files, follow `AGENTS.md` and the DevFlow workflow adapter.",
        "Because `.devflow/` exists, also apply `workspace-isolation`.",
        "Use `using-git-worktrees` when creating or entering workspaces.",
        "Use `verification-before-completion` before completion claims.",
        "Use `worker-handoff` for handoff/checkpoint work.",
        "Use `finishing-a-development-branch` only when explicitly finishing a branch.",
        "Do not write to the main checkout from a worker workspace.",
        "Do not merge, promote, push, rebase, or resolve conflicts unless the Dev-Flow command explicitly authorizes it.",
        "Installed/local workflow skill references: " + "; ".join(skill_refs),
    ]


def render_devmode_status(root: Path) -> str:
    status = detect_devmode(root)
    lines = [
        f"devmode_detected: {'yes' if status.detected else 'no'}",
        f"local_devmode_path: {status.local_devmode_path or 'missing'}",
        "sources:",
    ]
    if status.sources:
        lines.extend(f"  - {source}" for source in status.sources)
    else:
        lines.append("  - none")
    lines.append("skill_files:")
    for skill in status.skills:
        state = "present" if skill.present else "missing"
        path = skill.path or "missing"
        lines.append(f"  - {skill.name}: {state} ({path})")
    lines.append(
        "task_packets_reference_devmode: "
        + ("yes" if status.task_packets_reference_devmode else "no")
    )
    return "\n".join(lines) + "\n"


def _skill_status(root: Path, name: str) -> DevModeSkillStatus:
    for candidate in _skill_candidates(root, name):
        if candidate.exists():
            return DevModeSkillStatus(name=name, present=True, path=_relative(root, candidate))
    return DevModeSkillStatus(name=name, present=False, path=None)


def _skill_candidates(root: Path, name: str) -> tuple[Path, ...]:
    return (
        root / ".devmode" / "skills" / name / "SKILL.md",
        root / "skills" / name / "SKILL.md",
        root / ".github" / "skills" / name / "SKILL.md",
    )


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
