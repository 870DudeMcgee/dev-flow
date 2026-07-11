"""Layout contracts for the embedded control-room status page."""

from __future__ import annotations

import re

from devflow.control_room.page import STATUS_PAGE_HTML


def _css_rule(selector: str) -> str:
    match = re.search(
        rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\}}",
        STATUS_PAGE_HTML,
        re.DOTALL,
    )
    assert match is not None, f"missing CSS rule for {selector}"
    return match.group("body")


def test_active_worker_workspace_keeps_visible_height_ahead_of_history() -> None:
    active_card = _css_rule(".active-card")
    history_list = _css_rule(".history-list")

    assert "min-height: 480px" in active_card
    assert "max-height: 60px" in history_list
    assert "overflow-y: auto" in history_list
