"""Project Code Map service — Milestone 11.

Provides the service logic for `devflow map` commands.
No provider calls, no routing, no database, no autonomous behavior.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_TEMPLATE = """\
# Code Map

## What this repo does

<!-- One paragraph. Replace with a concise, jargon-free description. -->

## Layout

<!-- List the key top-level directories and what lives in each. -->
- `src/`         — production source
- `tests/`       — test suite (mirrors `src/` structure)
- `docs/`        — specs, contracts, architecture decisions
- `.devflow/`    — Dev-Flow runtime state (do not edit manually)

## Entry points

<!-- List the key files a worker should navigate to first. -->
- CLI:  <!-- e.g. src/mypackage/cli.py -->
- Core: <!-- e.g. src/mypackage/service.py -->

## What to read first (worker orientation)

<!-- Ordered list. Workers read this before broad repo scans. -->
1. `docs/roadmap.md`           — current direction and milestone status
2. `AGENTS.md`                 — agent operating rules (mandatory)

## What to skip

<!-- Paths that workers should never read or modify. -->
- <!-- e.g. src/mypackage/_legacy/ — quarantined, do not modify -->
- `build/`       — generated, ignored by git

## Owners / contacts

- Primary: <!-- your handle or name -->

## Last reviewed

<!-- YYYY-MM-DD -->
"""


class CodeMapError(Exception):
    """Raised when map_init cannot complete safely."""


@dataclass(frozen=True)
class CodeMapCheckResult:
    """Structured result from validating CODE_MAP.md."""

    path: Path
    ok: bool
    missing_sections: tuple[str, ...] = ()
    unfilled_sections: tuple[str, ...] = ()
    checked_paths: tuple[str, ...] = ()
    broken_paths: tuple[str, ...] = ()


_REQUIRED_SECTIONS = (
    "What this repo does",
    "Layout",
    "Entry points",
    "What to read first (worker orientation)",
    "What to skip",
    "Owners / contacts",
    "Last reviewed",
)

_PLACEHOLDER_RE = re.compile(
    r"\b(?:todo|tbd|replace me|your handle|yyyy-mm-dd|example only)\b",
    re.IGNORECASE,
)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_ENTRY_PATH_RE = re.compile(r"(?<![\w./-])(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+(?:\.[A-Za-z0-9_.-]+)?")


def map_init(root: Path, *, force: bool = False) -> Path:
    """Scaffold a blank CODE_MAP.md at *root*.

    Returns the path to the written file.
    Raises CodeMapError if the file already exists and *force* is False.
    """
    target = root / "CODE_MAP.md"
    if target.exists() and not force:
        raise CodeMapError(
            f"CODE_MAP.md already exists at {target}. "
            "Use --force to overwrite."
        )
    target.write_text(_DEFAULT_TEMPLATE, encoding="utf-8")
    return target


def map_show(root: Path) -> str:
    """Return the text contents of CODE_MAP.md at *root*.

    Raises CodeMapError with a clear message if CODE_MAP.md does not exist.
    """
    target = root / "CODE_MAP.md"
    if not target.exists():
        raise CodeMapError(
            "CODE_MAP.md not found. "
            "Run 'devflow map init' to scaffold one."
        )
    return target.read_text(encoding="utf-8")


def map_check(root: Path) -> CodeMapCheckResult:
    """Validate CODE_MAP.md for filled sections and valid entry-point paths."""
    target = root / "CODE_MAP.md"
    if not target.exists():
        raise CodeMapError(
            "CODE_MAP.md not found. "
            "Run 'devflow map init' to scaffold one."
        )

    text = target.read_text(encoding="utf-8")
    sections = _parse_sections(text)
    missing = tuple(section for section in _REQUIRED_SECTIONS if section not in sections)
    unfilled = tuple(
        section
        for section in _REQUIRED_SECTIONS
        if section in sections and not _section_is_filled(section, sections[section])
    )
    checked_paths, broken_paths = _check_entry_point_paths(root, sections.get("Entry points", ""))
    ok = not missing and not unfilled and not broken_paths
    return CodeMapCheckResult(
        path=target,
        ok=ok,
        missing_sections=missing,
        unfilled_sections=unfilled,
        checked_paths=checked_paths,
        broken_paths=broken_paths,
    )


def _parse_sections(text: str) -> dict[str, str]:
    matches = list(_SECTION_RE.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[title] = text[start:end]
    return sections


def _section_is_filled(title: str, body: str) -> bool:
    cleaned = _clean_section_body(body)
    lines = [line for line in (item.strip() for item in cleaned.splitlines()) if line and line not in {"-", "*"}]
    if not lines:
        return False
    if _PLACEHOLDER_RE.search("\n".join(lines)):
        return False
    if title == "Entry points":
        return bool(_entry_point_paths(cleaned))
    if title == "Last reviewed":
        return bool(re.search(r"\b\d{4}-\d{2}-\d{2}\b", cleaned))
    if title == "Owners / contacts":
        return any(":" not in line or line.split(":", 1)[1].strip() for line in lines)
    return True


def _clean_section_body(body: str) -> str:
    return _COMMENT_RE.sub("", body)


def _check_entry_point_paths(root: Path, body: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    paths = _entry_point_paths(_clean_section_body(body))
    broken = tuple(path for path in paths if not (root / path).exists())
    return paths, broken


def _entry_point_paths(body: str) -> tuple[str, ...]:
    found: list[str] = []
    for candidate in re.findall(r"`([^`]+)`", body):
        _append_path_candidate(found, candidate)
    for candidate in _ENTRY_PATH_RE.findall(body):
        _append_path_candidate(found, candidate)
    return tuple(dict.fromkeys(found))


def _append_path_candidate(found: list[str], candidate: str) -> None:
    candidate = candidate.strip().strip(".,:;")
    if not candidate or candidate.startswith(("/", "../", "http://", "https://")):
        return
    if candidate.endswith("/"):
        return
    if "/" not in candidate:
        return
    found.append(candidate)
