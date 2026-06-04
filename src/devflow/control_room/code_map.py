"""Project Code Map service — Milestone 11B.

Provides the scaffold logic for `devflow map init`.
No provider calls, no routing, no database, no autonomous behavior.
"""
from __future__ import annotations

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
