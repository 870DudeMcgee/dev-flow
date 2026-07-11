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


def test_complete_run_now_card_reports_human_acceptance() -> None:
    assert "Human decision accepted; the loop is complete." in STATUS_PAGE_HTML
    assert "No action required. Start the next bounded iteration when ready." in STATUS_PAGE_HTML


def test_chat_session_and_model_selection_survive_page_refresh() -> None:
    assert "localStorage.getItem('devflow.chat.session')" in STATUS_PAGE_HTML
    assert "localStorage.setItem('devflow.chat.session', sessionId)" in STATUS_PAGE_HTML
    assert "localStorage.getItem('devflow.chat.model')" in STATUS_PAGE_HTML
    assert "data.default_model" in STATUS_PAGE_HTML
