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


def test_completed_worker_evidence_defaults_to_plain_language_overview() -> None:
    for label in ("What happened", "Why", "How", "Who", "When", "Evidence", "Next"):
        assert f">{label}<" in STATUS_PAGE_HTML

    assert ">Overview<" in STATUS_PAGE_HTML
    assert "Technical details" in STATUS_PAGE_HTML
    assert "else if (isStreaming)" in STATUS_PAGE_HTML
    assert "activateOutputTab(viewer, 'raw')" in STATUS_PAGE_HTML
    assert "activateOutputTab(viewer, 'summary')" in STATUS_PAGE_HTML


def test_build_diff_has_a_direct_view_code_action() -> None:
    assert "name === 'build-diff.patch'" in STATUS_PAGE_HTML
    assert "const viewCodeButton = preferredCodeArtifact" in STATUS_PAGE_HTML
    assert ">View code</button>" in STATUS_PAGE_HTML
    assert "showArtifact('${escapeHtml(r.run_id)}','${escapeHtml(preferredCodeArtifact)}')" in STATUS_PAGE_HTML
    assert "Code &amp; files" in STATUS_PAGE_HTML


def test_ram_status_is_always_in_the_header_and_compacts_responsively() -> None:
    memory_index = STATUS_PAGE_HTML.index('<div class="memory-widget" id="memory-widget"')
    system_popover_index = STATUS_PAGE_HTML.index('<div class="system-popover" id="system-popover"')

    assert memory_index < system_popover_index
    assert 'aria-label="RAM status"' in STATUS_PAGE_HTML
    assert '<span class="brand-name">DevFlow Pipeline</span>' in STATUS_PAGE_HTML
    assert ".brand-name { display: none; }" in STATUS_PAGE_HTML
    assert ".memory-graph { display: none; }" in STATUS_PAGE_HTML


def test_header_and_evidence_viewer_resist_narrow_width_overflow() -> None:
    viewer_tabs = _css_rule(".viewer-tabs")
    now_headline = _css_rule(".now-headline")
    now_latest = _css_rule(".now-latest")

    assert "overflow-x: auto" in viewer_tabs
    assert "white-space: nowrap" not in now_headline
    assert "white-space: nowrap" not in now_latest
    assert "overflow-wrap: anywhere" in now_headline
    assert "@media (max-width: 1280px)" in STATUS_PAGE_HTML
    assert "@media (max-width: 1180px)" in STATUS_PAGE_HTML
    assert ".workspace-copy { display: none; }" in STATUS_PAGE_HTML


def test_header_controls_share_a_deliberate_visual_scale() -> None:
    assert "--header-control-height: 34px" in STATUS_PAGE_HTML
    assert "--header-control-radius: 9px" in STATUS_PAGE_HTML
    assert "height: var(--header-control-height)" in _css_rule(".system-widget")
    assert "border-radius: var(--header-control-radius)" in _css_rule(".system-widget")
    assert ".header .workspace-widget" in STATUS_PAGE_HTML
    assert ".header .git-widget" in STATUS_PAGE_HTML
    assert ".header .memory-widget" in STATUS_PAGE_HTML


def test_chat_composer_exposes_accessible_progressive_dictation() -> None:
    assert 'id="chat-mic-btn"' in STATUS_PAGE_HTML
    assert 'aria-label="Start dictation"' in STATUS_PAGE_HTML
    assert 'aria-pressed="false"' in STATUS_PAGE_HTML
    assert 'id="chat-dictation-state" role="status" aria-live="polite"' in STATUS_PAGE_HTML
    assert "window.SpeechRecognition || window.webkitSpeechRecognition" in STATUS_PAGE_HTML
    assert "Dictation unavailable in this browser" in STATUS_PAGE_HTML
    assert "Microphone permission was denied" in STATUS_PAGE_HTML
    assert "function toggleChatDictation()" in STATUS_PAGE_HTML
    assert "initializeChatDictation();" in STATUS_PAGE_HTML
    assert "Lucide Mic icon (ISC): https://lucide.dev/icons/mic" in STATUS_PAGE_HTML
    assert '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z">' in STATUS_PAGE_HTML
    assert '>Mic</button>' not in STATUS_PAGE_HTML


def test_completed_run_leads_with_product_scope_code_and_result() -> None:
    for label in (
        "Product / change",
        "Why it was built",
        "Scope",
        "Files &amp; code",
        "Result",
        "Evidence",
        "Next",
    ):
        assert f">{label}<" in STATUS_PAGE_HTML

    assert 'aria-label="Completed change overview"' in STATUS_PAGE_HTML
    assert "Open code diff" in STATUS_PAGE_HTML
    assert "Open verification" in STATUS_PAGE_HTML
    assert "Detailed work history" in STATUS_PAGE_HTML
    assert "loopComplete ? completedOverviewHtml" in STATUS_PAGE_HTML


def test_worker_overview_names_the_resolved_served_model() -> None:
    assert "entry.resolved_model || entry.model" in STATUS_PAGE_HTML
    assert "entry.resolved_model_recorded" in STATUS_PAGE_HTML
    assert "routed by" in STATUS_PAGE_HTML
    assert "Exact served model not recorded" in STATUS_PAGE_HTML
    assert "resolved_model: resolvedModel" in STATUS_PAGE_HTML


def test_completed_evidence_links_optional_reliability_report() -> None:
    assert "overview.reliability || null" in STATUS_PAGE_HTML
    assert "Reliability: ${reliability.safe ? 'safe' : 'action required'}" in STATUS_PAGE_HTML
    assert "Breached metrics / thresholds" in STATUS_PAGE_HTML
    assert "Recovery / rollback" in STATUS_PAGE_HTML
    assert ">Open reliability report</button>" in STATUS_PAGE_HTML
    assert "const reliabilityHtml = reliability ?" in STATUS_PAGE_HTML


def test_short_responsive_view_keeps_activity_visible_below_scrollable_overview() -> None:
    assert "@media (max-width: 1180px) and (max-height: 820px)" in STATUS_PAGE_HTML
    assert ".run-overview { max-height: 46%; overflow-y: auto; overscroll-behavior: contain; }" in STATUS_PAGE_HTML
    assert ".activity-card { min-height: 220px; }" in STATUS_PAGE_HTML


def test_completed_overview_scroll_survives_status_refresh() -> None:
    assert 'id="run-overview-${escapeHtml(r.run_id)}"' in STATUS_PAGE_HTML
    assert "const runOverviewScroll = {};" in STATUS_PAGE_HTML
    assert "runOverviewScroll[overview.id] = overview.scrollTop;" in STATUS_PAGE_HTML
    assert "runOverviewScroll," in STATUS_PAGE_HTML
    assert "Object.entries(state.runOverviewScroll || {})" in STATUS_PAGE_HTML
    assert "overview.scrollTop = scrollTop;" in STATUS_PAGE_HTML


def test_system_popover_exposes_model_catalog_and_human_health_controls() -> None:
    assert 'id="model-catalog-summary"' in STATUS_PAGE_HTML
    assert 'id="model-catalog-profiles"' in STATUS_PAGE_HTML
    assert "fetch('/api/model-catalog')" in STATUS_PAGE_HTML
    assert "fetch('/api/model-catalog/health'" in STATUS_PAGE_HTML
    assert "function loadModelCatalog()" in STATUS_PAGE_HTML
    assert "function changeModelRoleHealth(" in STATUS_PAGE_HTML
    assert "Restore this model role?" in STATUS_PAGE_HTML
    assert "Quarantine reason" in STATUS_PAGE_HTML
