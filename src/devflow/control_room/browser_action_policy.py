"""Canonical browser action policy projection.

This module is intentionally declarative. It owns the browser-visible
allowed/blocked mutation labels shared by the supervisor policy, task workbench,
and operating-layer snapshots. It does not execute commands or loosen the
server's exact approval parsers.
"""

from __future__ import annotations

BROWSER_ALLOWED_MUTATIONS: tuple[str, ...] = (
    "idea capture",
    "task creation",
    "shell worker execution",
    "serial local-agent packet creation",
    "model/provider onboarding",
    "task verification",
    "task promotion",
)

BROWSER_BLOCKED_MUTATIONS: tuple[str, ...] = (
    "non-shell worker execution",
    "local/provider model execution",
    "Hermes worker runtime launch",
    "patch application",
    "cleanup apply",
    "sync",
    "push",
    "project publication",
    "autonomous routing",
    "broad mutation",
)


def get_browser_allowed_mutations() -> list[str]:
    """Return browser mutations that are allowed with exact approval gates."""
    return list(BROWSER_ALLOWED_MUTATIONS)


def get_browser_blocked_mutations() -> list[str]:
    """Return browser mutations that remain blocked from browser execution."""
    return list(BROWSER_BLOCKED_MUTATIONS)


__all__ = [
    "BROWSER_ALLOWED_MUTATIONS",
    "BROWSER_BLOCKED_MUTATIONS",
    "get_browser_allowed_mutations",
    "get_browser_blocked_mutations",
]
