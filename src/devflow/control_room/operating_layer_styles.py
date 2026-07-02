from __future__ import annotations

from devflow.control_room.operating_layer_model_picker_styles import (
    BUILDER_JUDGE_MODEL_PICKER_CSS,
    MODEL_PICKER_CSS,
)
from devflow.control_room.operating_layer_task_control_styles import TASK_CONTROL_WORKBENCH_CSS


APP_CSS = """:root {
  --bg: #0d1117;
  --bg-2: #161b22;
  --bg-3: #1c2128;
  --panel: #1a1f26;
  --panel-hover: #21262d;
  --border: #30363d;
  --border-light: #21262d;
  --text: #e6edf3;
  --text-soft: #8b949e;
  /* Bumped from #6e7681 (~3.0:1 on --panel, fails WCAG AA) to ~4.7:1 for body text. */
  --text-muted: #9aa4af;
  /* Decorative/non-essential glyphs only — not for real text content. */
  --text-faint: #6e7681;
  --accent: #3fb950;
  --accent-soft: rgba(63, 185, 80, 0.12);
  --accent-bg: rgba(63, 185, 80, 0.08);
  --blue: #58a6ff;
  --blue-soft: rgba(88, 166, 255, 0.08);
  --orange: #d29922;
  --orange-soft: rgba(210, 153, 34, 0.1);
  --red: #f85149;
  --red-soft: rgba(248, 81, 73, 0.1);
  --purple: #bc8cff;
  --shadow: 0 1px 3px rgba(0,0,0,0.3), 0 4px 12px rgba(0,0,0,0.15);
  --radius: 8px;
  --radius-sm: 6px;
  --sidebar-w: 56px;
  --sidebar-expanded-w: 220px;
}
*, *::before, *::after { box-sizing: border-box; }
html {
  font-size: 14px;
  background: var(--bg);
  color: var(--text);
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
  line-height: 1.5;
  min-width: 0;
}

/* ===== APP SHELL ===== */
.app-shell {
  display: flex;
  min-height: 100vh;
  width: 100%;
}
#main-panel {
  flex: 1;
  min-width: 0;
}

/* ===== SIDEBAR ===== */
.sidebar {
  position: sticky;
  top: 0;
  width: var(--sidebar-w);
  height: 100vh;
  background: var(--bg-2);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  z-index: 10;
  overflow: hidden;
  transition: width 0.16s ease, box-shadow 0.16s ease;
}
.sidebar:hover,
.sidebar:focus-within {
  width: var(--sidebar-expanded-w);
  box-shadow: 12px 0 24px rgba(0,0,0,0.24);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: var(--sidebar-expanded-w);
  padding: 12px 11px 10px;
  border-bottom: 1px solid var(--border);
}
.brand-mark {
  width: 32px; height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, var(--accent), #2ea043);
  color: #fff;
  font-weight: 700;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.brand-text { display: none; }
.sidebar:hover .brand-text,
.sidebar:focus-within .brand-text { display: block; }
.brand-text strong { display: block; font-size: 14px; color: var(--text); }
.brand-text span { font-size: 11px; color: var(--text-soft); }

.nav-list { padding: 8px 8px 0; display: flex; flex-direction: column; gap: 2px; }
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  justify-content: center;
  min-height: 36px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  text-decoration: none;
  font-size: 14px;
  transition: background 0.12s, color 0.12s;
  cursor: pointer;
}
.nav-item span { display: none; }
.sidebar:hover .nav-item,
.sidebar:focus-within .nav-item { justify-content: flex-start; }
.sidebar:hover .nav-item span,
.sidebar:focus-within .nav-item span { display: inline; }
.nav-item:hover { background: var(--bg-3); color: var(--text); }
.nav-item.active { background: var(--accent-bg); color: var(--accent); font-weight: 500; }
.nav-item.small { font-size: 13px; padding: 6px 12px; }
.nav-icon { flex-shrink: 0; opacity: 0.8; }
.nav-item.active .nav-icon { opacity: 1; }

.sidebar-spacer { flex: 1; }

.sidebar-status-card {
  margin: 4px 8px 12px;
  min-width: calc(var(--sidebar-expanded-w) - 16px);
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-3);
  display: flex;
  align-items: center;
  gap: 10px;
}
.sidebar-status-card div { display: none; }
.sidebar:hover .sidebar-status-card div,
.sidebar:focus-within .sidebar-status-card div { display: block; }
.sidebar-status-card strong { display: block; font-size: 13px; color: var(--text); }
.sidebar-status-card .status-sub { font-size: 11px; color: var(--text-soft); }

.sidebar-footer {
  padding: 4px 8px 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* ===== TOP BAR ===== */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-2);
  gap: 8px;
  flex-wrap: wrap;
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Repo selector */
.repo-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  cursor: pointer;
  transition: border-color 0.12s, background 0.12s;
  position: relative;
}
.repo-selector:hover { border-color: var(--text-soft); background: var(--bg-3); }
.repo-icon { font-size: 16px; flex-shrink: 0; }
.repo-info { display: flex; flex-direction: column; gap: 0; }
.repo-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.repo-info strong { font-size: 13px; color: var(--text); }
.repo-path { font-size: 11px; color: var(--text-soft); }
.repo-selector .chevron { color: var(--text-muted); margin-left: 4px; }

/* Topbar pills */
.topbar-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-3);
  border: 1px solid transparent;
}
.pill-icon { font-size: 14px; color: var(--text-muted); }
.pill-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.topbar-pill strong { font-size: 12px; color: var(--text); }

/* Status dots */
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.status-dot.online { background: var(--accent); box-shadow: 0 0 6px rgba(63,185,80,0.4); }
.status-dot.clean { background: var(--accent); }
.status-dot.warning { background: var(--orange); }
.status-dot.error { background: var(--red); }

/* Topbar button */
.topbar-btn {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 5px 12px;
  color: var(--text-soft);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.topbar-btn:hover { background: var(--bg-3); color: var(--text); }

.topbar-health {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-3);
  position: relative;
  font-size: 12px;
  color: var(--text-soft);
}
#topbar-health { flex-shrink: 0; }
.topbar-health-label {
  color: var(--text);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.3px;
  text-transform: uppercase;
}
.topbar-health-summary {
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
}
.topbar-health-details { position: relative; }
.topbar-health-details summary {
  align-items: center;
  border-radius: 4px;
  color: var(--text-muted);
  cursor: pointer;
  display: inline-flex;
  height: 20px;
  justify-content: center;
  list-style: none;
  width: 20px;
}
.topbar-health-details summary::-webkit-details-marker { display: none; }
.topbar-health-details summary::marker { content: ""; }
.topbar-health-details[open] summary,
.topbar-health-details summary:hover { background: var(--bg); color: var(--text); }
.topbar-health-popover {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  min-width: 320px;
  padding: 8px;
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  z-index: 120;
}

/* ===== REPO DROPDOWN ===== */
.repo-dropdown {
  position: absolute;
  top: 56px;
  left: calc(var(--sidebar-w) + 20px);
  width: 320px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  z-index: 100;
  overflow: hidden;
}
.repo-dropdown-header {
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-muted);
}
.repo-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.1s;
}
.repo-item:hover { background: var(--panel-hover); }
.repo-item.active { background: var(--accent-bg); }
.repo-item strong { font-size: 13px; color: var(--text); display: block; }
.repo-item .repo-path { font-size: 11px; color: var(--text-soft); }
.repo-item-icon { font-size: 14px; color: var(--text-muted); flex-shrink: 0; }
.repo-item .check { margin-left: auto; color: var(--accent); font-weight: 700; }

/* ===== ZONE LAYOUT (main + chat sidebar) ===== */
.layout-columns {
  display: flex;
  gap: 12px;
  padding: 0 14px;
}
.main-content {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}
.snapshot-warning-strip {
  margin: 0 0 8px;
  border: 1px solid rgba(180, 83, 9, 0.35);
  border-left: 3px solid var(--orange);
  border-radius: var(--radius-sm);
  background: rgba(180, 83, 9, 0.08);
  color: var(--text);
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
}
.snapshot-warning-strip[hidden] { display: none; }
.snapshot-warning-strip strong {
  color: var(--orange);
  font-size: 12px;
}
.snapshot-warning-strip ul {
  display: flex;
  flex-direction: column;
  gap: 2px;
  list-style: none;
  margin: 0;
  padding: 0;
}
.snapshot-warning-strip li {
  color: var(--text-soft);
  font-size: 11px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}
.chat-sidebar {
  flex: 0 0 320px;
  width: 320px;
  max-height: calc(100vh - 88px);
  position: sticky;
  top: 72px;
  display: flex;
  flex-direction: column;
  align-self: flex-start;
}
.chat-sidebar .brainstorm-section {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  max-height: calc(100vh - 88px);
  min-height: 400px;
}
.chat-sidebar .brainstorm-section .panel-header {
  align-items: flex-start;
  flex-direction: column;
  gap: 8px;
  min-height: auto;
  overflow: visible;
}
.chat-sidebar .brainstorm-section .panel-header-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  width: 100%;
}
.chat-sidebar .brainstorm-section .model-selector-wrap {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
}
.chat-sidebar .brainstorm-section .model-dropdown {
  left: 0;
  min-width: 260px;
  right: auto;
}
.chat-sidebar .brainstorm-transcript {
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  overflow-y: auto;
  padding: 10px;
}
.chat-sidebar .brainstorm-chat-form {
  padding: 8px 10px 10px;
  flex-shrink: 0;
}
.chat-sidebar .brainstorm-chat-form textarea {
  min-height: 64px;
}
.chat-sidebar .brainstorm-chat-form .composer-row {
  align-items: stretch;
  flex-wrap: wrap;
}
.chat-sidebar .newline-hint {
  flex: 1 1 100%;
  margin-right: 0;
}
.chat-sidebar #brainstorm-send {
  flex: 1 1 100%;
}
.chat-sidebar .brainstorm-msg {
  gap: 6px;
}
.chat-sidebar .msg-avatar {
  height: 24px;
  width: 24px;
}
.chat-sidebar .msg-body {
  max-width: calc(100% - 30px);
}
.zone {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 0;
  scroll-margin-top: 60px;
}
.zone + .zone {
  border-top: 1px solid var(--border);
  margin-top: 2px;
}
.zone-header {
  align-items: baseline;
  display: flex;
  gap: 12px;
  padding: 0 2px;
}
.zone-title {
  color: var(--text);
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.2px;
  margin: 0;
}
.zone-hint {
  color: var(--text-muted);
  font-size: 12px;
}
/* Collapsible empty sections */
.zone .panel.is-empty,
.zone .product-review-section.is-empty {
  overflow: hidden;
  max-height: 48px;
  transition: max-height 0.2s ease;
}
.zone .panel.is-empty .panel-header,
.zone .product-review-section.is-empty .product-review-header {
  border-bottom: 0;
  cursor: pointer;
}
.zone .panel.is-empty.expanded,
.zone .product-review-section.is-empty.expanded {
  max-height: 2000px;
}
.zone .panel.is-empty .panel-body,
.zone .panel.is-empty .task-control-grid,
.zone .panel.is-empty .mission-feed-list,
.zone .panel.is-empty .worker-lanes-list,
.zone .panel.is-empty .review-queue-list,
.zone .panel.is-empty .evidence-stream-list,
.zone .panel.is-empty .dock-panel-body,
.zone .product-review-section.is-empty .task-control-grid,
.zone .product-review-section.is-empty .worker-lanes-list,
.zone .product-review-section.is-empty .review-queue-list,
.zone .product-review-section.is-empty .evidence-stream-list {
  display: none;
}
.zone .panel.is-empty.expanded .panel-body,
.zone .panel.is-empty.expanded .task-control-grid,
.zone .panel.is-empty.expanded .mission-feed-list,
.zone .panel.is-empty.expanded .worker-lanes-list,
.zone .panel.is-empty.expanded .review-queue-list,
.zone .panel.is-empty.expanded .evidence-stream-list,
.zone .panel.is-empty.expanded .dock-panel-body,
.zone .product-review-section.is-empty.expanded .task-control-grid,
.zone .product-review-section.is-empty.expanded .worker-lanes-list,
.zone .product-review-section.is-empty.expanded .review-queue-list,
.zone .product-review-section.is-empty.expanded .evidence-stream-list {
  display: revert;
}
.zone .panel.is-empty .empty-toggle-hint,
.zone .product-review-section.is-empty .empty-toggle-hint {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 600;
  margin-left: auto;
}

/* ===== TOOL TABS ===== */
.tools-tabs {
  align-items: center;
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 0;
  padding: 0 2px;
}
.tools-tab {
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  color: var(--text-soft);
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  padding: 8px 16px;
  transition: border-color 0.12s, color 0.12s;
}
.tools-tab:hover { color: var(--text); }
.tools-tab.active {
  border-bottom-color: var(--accent);
  color: var(--text);
}
.tools-panel[hidden] { display: none !important; }

/* ===== ARCHITECTURE EVIDENCE ===== */
.architecture-evidence-section {
  margin-top: 8px;
}
.architecture-evidence-section.is-stale {
  border-color: rgba(210, 153, 34, 0.34);
}
.architecture-evidence-content {
  display: grid;
  gap: 10px;
  padding: 12px 14px 14px;
}
.architecture-summary-row {
  align-items: stretch;
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(0, 1fr) minmax(240px, 0.62fr);
}
.architecture-summary-main,
.architecture-next-action,
.architecture-evidence-block,
.architecture-metric {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}
.architecture-summary-main,
.architecture-next-action {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 10px 11px;
}
.architecture-summary-main strong {
  color: var(--text);
  font-size: 13px;
  line-height: 1.35;
}
.architecture-summary-main span,
.architecture-next-action span,
.architecture-evidence-block li span,
.architecture-empty {
  color: var(--text-soft);
  font-size: 12px;
  line-height: 1.4;
}
.architecture-source-chip {
  color: var(--text-muted) !important;
  font-size: 10px !important;
  font-weight: 700;
  letter-spacing: 0.35px;
  text-transform: uppercase;
}
.architecture-next-action {
  align-content: start;
}
.architecture-next-action code {
  background: #070a0f;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  display: block;
  font-size: 11px;
  min-width: 0;
  overflow: hidden;
  padding: 6px 8px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.architecture-next-action .btn {
  justify-self: start;
}
.architecture-metric-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(6, minmax(0, 1fr));
}
.architecture-metric {
  border-left: 3px solid var(--border);
  display: grid;
  gap: 2px;
  min-width: 0;
  padding: 8px 9px;
}
.architecture-metric span,
.architecture-evidence-block h4 {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.35px;
  margin: 0;
  text-transform: uppercase;
}
.architecture-metric strong {
  color: var(--text);
  font-size: 13px;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.architecture-freshness {
  border-left-color: var(--orange);
}
.architecture-diagnostics {
  border-left-color: var(--blue);
}
.architecture-evidence-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.architecture-evidence-block {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 10px 11px;
}
.architecture-question-block {
  grid-column: 1 / -1;
}
.architecture-artifact-list,
.architecture-diagnostic-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}
.architecture-provenance-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}
.architecture-provenance {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  display: grid;
  gap: 2px;
  min-width: 0;
  padding: 8px 9px;
}
.architecture-provenance span {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.35px;
  text-transform: uppercase;
}
.architecture-provenance strong {
  color: var(--text);
  font-size: 12px;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.architecture-action-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.architecture-viewer-overlay .architecture-viewer-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 86vh;
  max-width: min(1100px, 94vw);
  width: 94vw;
}
.architecture-viewer-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.architecture-viewer-header strong {
  color: var(--text);
  font-size: 14px;
}
.architecture-viewer-report {
  background: #070a0f;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  flex: 1 1 auto;
  font-size: 12px;
  line-height: 1.45;
  margin: 0;
  max-height: 74vh;
  overflow: auto;
  padding: 12px 14px;
  white-space: pre-wrap;
  word-break: break-word;
}
.architecture-viewer-frame {
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  flex: 1 1 auto;
  min-height: 60vh;
  width: 100%;
}
.architecture-artifact-chip,
.architecture-diagnostic-chip {
  align-items: center;
  background: var(--bg-2);
  border: 1px solid var(--border-light);
  border-radius: 999px;
  display: inline-flex;
  gap: 6px;
  max-width: 100%;
  min-width: 0;
  padding: 3px 8px;
}
.architecture-artifact-chip strong,
.architecture-diagnostic-chip {
  color: var(--text-soft);
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}
.architecture-artifact-chip code {
  color: var(--text-muted);
  font-size: 10px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.architecture-evidence-block ul {
  display: grid;
  gap: 6px;
  list-style: none;
  margin: 0;
  padding: 0;
}
.architecture-evidence-block li {
  border-top: 1px solid var(--border-light);
  display: grid;
  gap: 2px;
  min-width: 0;
  padding-top: 6px;
}
.architecture-evidence-block li:first-child {
  border-top: 0;
  padding-top: 0;
}
.architecture-evidence-block li strong {
  color: var(--text);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

/* ===== INLINE BRAINSTORM HISTORY ===== */
.brainstorm-history-inline {
  border-top: 1px solid var(--border-light);
  padding: 0 12px;
}
.brainstorm-history-inline summary {
  align-items: center;
  color: var(--text-soft);
  cursor: pointer;
  display: flex;
  font-size: 11px;
  font-weight: 700;
  gap: 8px;
  list-style: none;
  min-height: 32px;
  padding: 6px 4px;
  text-transform: uppercase;
}
.brainstorm-history-inline summary::-webkit-details-marker { display: none; }
.brainstorm-history-inline summary::marker { content: ""; }
.brainstorm-history-inline summary:hover { color: var(--text); }
.brainstorm-history-inline summary output {
  color: var(--text-muted);
  font-size: 10px;
  text-transform: none;
}
.brainstorm-history-inline summary .btn {
  margin-left: auto;
  text-transform: none;
}
.brainstorm-history-inline .history-list {
  max-height: 120px;
  overflow-y: auto;
  padding: 4px 0 8px;
}

/* Inline brainstorm full width */
.brainstorm-section .brainstorm-transcript {
  min-height: clamp(240px, 36vh, 400px);
  max-height: clamp(240px, 36vh, 400px);
}
.brainstorm-section .brainstorm-chat-form textarea {
  min-height: 64px;
}
.brainstorm-section .panel-header-controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.brainstorm-section .model-selector-wrap {
  position: relative;
}
.brainstorm-section .model-dropdown {
  left: 0;
  right: auto;
}

/* ===== PANELS (generic) ===== */
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  margin-bottom: 6px;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-light);
  min-height: 38px;
}
.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0;
}
/* h2 panel-title (zone-level panels) inherits same style */
.panel-title-sm {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.panel-subtitle {
  margin: 3px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.35;
}
.panel-header-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

""" + MODEL_PICKER_CSS + """.evidence-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-soft);
  cursor: pointer;
}
.evidence-toggle input { accent-color: var(--accent); }

/* ===== BRAINSTORM SECTION ===== */
.brainstorm-section {
  display: flex;
  flex-direction: column;
}
.brainstorm-transcript {
  min-height: clamp(340px, 44vh, 520px);
  max-height: clamp(340px, 44vh, 520px);
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.brainstorm-empty-state {
  color: var(--text-muted);
  font-size: 13px;
  padding: 20px;
  text-align: center;
}
.brainstorm-msg { display: flex; gap: 8px; animation: fadeIn 0.2s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.brainstorm-msg.user { flex-direction: row-reverse; }
.msg-avatar { width: 28px; height: 28px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; }
.msg-avatar.ai { background: var(--bg-3); color: var(--accent); border: 1px solid var(--border); }
.msg-avatar.user { background: var(--accent); color: #fff; }
.msg-body { max-width: 75%; }
.msg-meta { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; }
.msg-author { font-size: 11px; font-weight: 600; color: var(--text); }
.msg-time { font-size: 10px; color: var(--text-muted); }
.msg-bubble {
  padding: 8px 12px;
  border-radius: var(--radius);
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg-bubble.ai { background: var(--bg-3); color: var(--text); border: 1px solid var(--border); }
.msg-bubble.user { background: var(--accent-bg); color: var(--text); border: 1px solid rgba(63,185,80,0.2); }
.msg-actions { display: flex; gap: 6px; margin-top: 6px; }
.msg-action-btn {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 11px;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.1s, border-color 0.1s;
}
.msg-action-btn:hover { color: var(--text); border-color: var(--text-soft); }
.thinking-dots span { display: inline-block; animation: thinkBlink 1.2s infinite; opacity: 0.3; font-weight: bold; }
.thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes thinkBlink { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }

/* Brainstorm form */
.brainstorm-chat-form {
  border-top: 1px solid var(--border-light);
  padding: 8px 12px;
}
.brainstorm-chat-form textarea {
  width: 100%;
  min-height: 58px;
  max-height: 150px;
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
  outline: none;
  transition: border-color 0.12s;
}
.brainstorm-chat-form textarea:focus { border-color: var(--accent); }
.brainstorm-chat-form textarea::placeholder { color: var(--text-muted); }
.composer-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.composer-shortcuts { display: flex; gap: 4px; }
.shortcut-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px; height: 22px;
  border-radius: 4px;
  background: var(--bg-3);
  border: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}
.newline-hint { font-size: 10px; color: var(--text-muted); margin-right: auto; }

/* ===== IDEA GREENHOUSE ===== */
.idea-greenhouse-section {
  min-width: 0;
}
.unified-workbench-section {
  border-color: rgba(88, 166, 255, 0.28);
}
.unified-workbench-section .panel-header {
  min-height: 38px;
  padding: 8px 12px;
}
.unified-workbench-section .panel-subtitle {
  display: none;
}
.workbench-overview {
  border-top: 1px solid var(--border-light);
  display: grid;
  gap: 5px;
  grid-template-columns: minmax(0, 1.25fr) minmax(260px, 0.75fr);
  padding: 5px 10px 0;
}
.workbench-stage-path {
  display: grid;
  gap: 5px;
  grid-column: 1 / -1;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}
.workbench-stage-chip {
  align-items: start;
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  display: grid;
  gap: 2px;
  min-height: 28px;
  min-width: 0;
  padding: 4px 5px;
  position: relative;
}
.workbench-stage-chip::before {
  background: var(--border);
  border-radius: 999px;
  content: "";
  height: 3px;
  left: 8px;
  position: absolute;
  right: 8px;
  top: 0;
}
.workbench-stage-chip.done::before { background: var(--accent); }
.workbench-stage-chip.active::before { background: var(--blue); }
.workbench-stage-chip strong {
  color: var(--text);
  font-size: 11px;
  line-height: 1.2;
}
.workbench-stage-chip.pending strong {
  color: var(--text-muted);
}
.workbench-stage-chip code {
  display: none;
  color: var(--text-muted);
  font-size: 10px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.workbench-gate-strip {
  display: grid;
  gap: 5px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.workbench-gate-card,
.workbench-next-action,
.workbench-result-card {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--border);
  border-radius: var(--radius-sm);
  min-width: 0;
  padding: 4px 6px;
}
.workbench-gate-card {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
}
.workbench-gate-card.good,
.workbench-result-card.good { border-left-color: var(--accent); }
.workbench-gate-card.warn,
.workbench-result-card.warn { border-left-color: var(--orange); }
.workbench-gate-card.neutral,
.workbench-result-card.neutral { border-left-color: var(--blue); }
.workbench-gate-card div,
.workbench-next-action div,
.workbench-result-card {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.workbench-gate-card strong,
.workbench-next-action strong,
.workbench-result-card strong {
  color: var(--text);
  font-size: 12px;
  line-height: 1.3;
}
.workbench-gate-card span,
.workbench-gate-card em,
.workbench-next-action span,
.workbench-result-card span {
  color: var(--text-soft);
  font-size: 11px;
  font-style: normal;
  line-height: 1.35;
}
.workbench-gate-card span,
.workbench-gate-card em,
.workbench-next-action span,
.workbench-next-action code {
  display: none;
}
.workbench-gate-card em {
  color: var(--text-muted);
}
.workbench-next-action {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
}
.workbench-next-action code,
.workbench-result-card code {
  color: var(--text-muted);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.workbench-next-buttons {
  align-items: center;
  display: flex !important;
  flex: 0 0 auto;
  flex-direction: row !important;
  flex-wrap: wrap;
  gap: 6px !important;
  justify-content: flex-end;
}
.workbench-implement-result:empty {
  display: none;
}
.workbench-implement-result {
  display: grid;
  gap: 8px;
  grid-column: 1 / -1;
}
.status-pill {
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 999px;
  display: inline-flex;
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.3px;
  line-height: 1.2;
  min-height: 22px;
  padding: 3px 8px;
  text-transform: uppercase;
  white-space: nowrap;
}
.status-pill.muted {
  background: rgba(110, 118, 129, 0.10);
  color: var(--text-soft);
}
.idea-capture-form {
  border-top: 1px solid var(--border-light);
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 8px 12px 8px;
}
.idea-capture-form textarea,
.idea-capture-form input {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  font: inherit;
  font-size: 12px;
  min-width: 0;
  outline: none;
  padding: 8px 10px;
  transition: border-color 0.12s;
  width: 100%;
}
.idea-capture-form textarea {
  height: 38px;
  line-height: 1.45;
  max-height: 160px;
  min-height: 38px;
  resize: vertical;
}
.idea-capture-form input {
  flex: 1 1 200px;
  min-height: 30px;
}
.idea-capture-form textarea:focus,
.idea-capture-form input:focus {
  border-color: var(--accent);
}
.idea-capture-form textarea::placeholder,
.idea-capture-form input::placeholder {
  color: var(--text-muted);
}
.idea-capture-form .composer-row {
  align-items: stretch;
  flex-wrap: wrap;
  margin-top: 0;
}
.idea-capture-form .btn {
  flex: 0 0 auto;
  justify-content: center;
  white-space: nowrap;
}
.idea-primary-action:empty,
.idea-greenhouse-lanes:empty {
  display: none;
}
.idea-primary-action:not(:empty) {
  background: linear-gradient(90deg, var(--blue-soft), transparent 70%), var(--bg);
  border: 1px solid rgba(88, 166, 255, 0.22);
  border-left: 3px solid var(--blue);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  display: flex;
  flex-direction: column;
  font-size: 12px;
  gap: 5px;
  margin: 0 14px 8px;
  min-width: 0;
  padding: 7px 10px;
}
.idea-primary-action strong {
  color: var(--text);
  font-size: 12px;
}
.idea-primary-action code {
  background: #070a0f;
  border: 1px solid var(--border-light);
  border-radius: 5px;
  color: var(--text-soft);
  display: block;
  font-size: 11px;
  overflow: hidden;
  padding: 5px 7px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.idea-greenhouse-lanes {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  max-width: 100%;
  min-width: 0;
  padding: 6px 10px 8px;
}
.idea-greenhouse-lanes:has(.idea-card) {
  max-height: 180px;
  overflow: hidden;
}
.obsidian-intake-section {
  min-width: 0;
}
.obsidian-intake-section:not(.is-ready) {
  display: none;
}
.obsidian-intake-section.is-unavailable .panel-header {
  min-height: 44px;
  padding: 8px 12px;
}
.obsidian-intake-section.is-unavailable .panel-subtitle {
  display: none;
}
.obsidian-intake-lane-counts:empty,
.obsidian-intake-body:empty {
  display: none;
}
.obsidian-intake-lane-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 14px 8px;
}
.obsidian-lane-chip {
  align-items: center;
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: 999px;
  color: var(--text-soft);
  display: inline-flex;
  font-size: 11px;
  gap: 6px;
  min-height: 24px;
  padding: 4px 9px;
}
.obsidian-lane-chip strong {
  color: var(--text);
  font-size: 11px;
}
.obsidian-intake-body {
  border-top: 1px solid var(--border-light);
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(220px, 0.8fr) minmax(0, 1.2fr);
  padding: 10px 14px 14px;
}
.obsidian-intake-empty {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font-size: 12px;
  padding: 10px 12px;
}
.obsidian-intake-empty.error {
  border-left: 3px solid var(--red);
  color: var(--text);
}
.obsidian-intake-list {
  display: grid;
  gap: 6px;
  max-height: 260px;
  overflow: auto;
}
.obsidian-intake-card {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: inherit;
  cursor: pointer;
  display: grid;
  gap: 3px;
  min-width: 0;
  padding: 8px 10px;
  text-align: left;
}
.obsidian-intake-card.is-selected {
  border-color: rgba(88, 166, 255, 0.35);
  box-shadow: inset 0 0 0 1px rgba(88, 166, 255, 0.2);
}
.obsidian-intake-card strong {
  color: var(--text);
  font-size: 12px;
}
.obsidian-intake-card-meta,
.obsidian-intake-card-summary,
.obsidian-intake-detail-meta,
.obsidian-intake-detail-grid div span,
.obsidian-intake-detail-actions-status {
  color: var(--text-soft);
  font-size: 11px;
}
.obsidian-intake-card-summary {
  overflow: hidden;
  text-overflow: ellipsis;
}
.obsidian-intake-detail {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 10px 12px;
}
.obsidian-intake-detail-header {
  display: grid;
  gap: 4px;
}
.obsidian-intake-detail-header h4 {
  color: var(--text);
  font-size: 14px;
  margin: 0;
}
.obsidian-intake-detail-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.obsidian-intake-detail-grid div {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.obsidian-intake-detail-grid div strong {
  color: var(--text);
  font-size: 11px;
}
.obsidian-intake-detail-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.obsidian-intake-detail-actions-status {
  margin-left: auto;
}
@media (max-width: 900px) {
  .obsidian-intake-body {
    grid-template-columns: 1fr;
  }
}
.idea-lane {
  --idea-accent: var(--border);
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-top: 2px solid var(--idea-accent);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.idea-lane .idea-card {
  flex-shrink: 0;
}
.idea-lane-header {
  align-items: center;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  gap: 6px;
  justify-content: space-between;
  min-width: 0;
  padding: 4px 8px;
}
.idea-lane-header strong {
  color: var(--text);
  font-size: 11px;
  font-weight: 700;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.idea-lane-header span,
.idea-lane-header output {
  color: var(--text-muted);
  flex-shrink: 0;
  font-size: 9px;
}
.idea-lane.raw,
.idea-card.raw {
  --idea-accent: var(--text-muted);
  --idea-tint: rgba(110, 118, 129, 0.035);
}
.idea-lane.clarify,
.idea-card.clarify {
  --idea-accent: var(--purple);
  --idea-tint: rgba(188, 140, 255, 0.055);
}
.idea-lane.candidate,
.idea-card.candidate {
  --idea-accent: var(--blue);
  --idea-tint: var(--blue-soft);
}
.idea-lane.promoted,
.idea-card.promoted {
  --idea-accent: var(--accent);
  --idea-tint: var(--accent-bg);
}
.idea-lane.parked,
.idea-card.parked {
  --idea-accent: var(--text-muted);
  --idea-tint: rgba(110, 118, 129, 0.06);
}
.idea-lane.archived,
.idea-card.archived {
  --idea-accent: var(--text-muted);
  --idea-tint: transparent;
  opacity: 0.72;
}
.idea-card {
  --idea-accent: var(--border);
  --idea-tint: transparent;
  background: linear-gradient(90deg, var(--idea-tint), transparent 68%), var(--bg);
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--idea-accent);
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 4px 6px;
  min-width: 0;
  padding: 5px 7px 6px 8px;
}
.idea-card:hover {
  background: var(--panel-hover);
  border-color: var(--border);
}
.idea-card header,
.idea-card-head,
.idea-card-title-row {
  align-items: baseline;
  display: flex;
  gap: 6px;
  min-width: 0;
}
.idea-card strong,
.idea-card-title {
  color: var(--text);
  font-size: 11px;
  font-weight: 700;
  min-width: 0;
  overflow: hidden;
  overflow-wrap: anywhere;
  text-overflow: ellipsis;
  white-space: normal;
}
.idea-card-id {
  color: var(--blue);
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 800;
}
.idea-card-meta,
.idea-card-action,
.idea-card-command,
.idea-card p {
  color: var(--text-muted);
  font-size: 9px;
  line-height: 1.3;
  margin: 0;
  min-width: 0;
  overflow: hidden;
  overflow-wrap: anywhere;
  text-overflow: ellipsis;
  white-space: normal;
}
.idea-card-action {
  color: var(--text-soft);
  font-size: 10px;
  font-weight: 600;
}
.idea-card-meta,
.idea-card-action {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.idea-card code,
.idea-card-command {
  background: #070a0f;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  color: var(--text-soft);
  display: block;
  font-size: 10px;
  padding: 3px 5px;
  white-space: nowrap;
}
.idea-card .btn {
  align-self: flex-start;
  margin-top: 2px;
}
.idea-card-secondary-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}
.idea-card[role="button"] {
  cursor: pointer;
}
.idea-card[role="button"]:focus-visible {
  border-color: var(--blue);
  box-shadow: 0 0 0 2px rgba(88, 166, 255, 0.22);
  outline: none;
}
.idea-detail-head .lane-raw,
.idea-detail-head .lane-parked,
.idea-detail-head .lane-archived {
  background: rgba(110, 118, 129, 0.12);
  color: var(--text-soft);
}
.idea-detail-head .lane-clarify {
  background: rgba(188, 140, 255, 0.14);
  color: var(--purple);
}
.idea-detail-head .lane-candidate {
  background: var(--blue-soft);
  color: var(--blue);
}
.idea-detail-head .lane-promoted {
  background: var(--accent-bg);
  color: var(--accent);
}
.idea-detail-grid strong {
  overflow-wrap: anywhere;
}
.idea-detail-next-action {
  border-left-color: var(--blue);
}
.idea-detail-evidence .path-line {
  display: block;
  margin: 5px 0;
}
.idea-detail-metadata pre {
  background: #070a0f;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font-size: 11px;
  line-height: 1.45;
  margin: 8px 0 0;
  max-height: 240px;
  overflow: auto;
  padding: 10px;
  white-space: pre-wrap;
}
.idea-detail-metadata-list {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 0;
}
.idea-detail-metadata-list div {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  min-width: 0;
  padding: 7px 8px;
}
.idea-detail-metadata-list dt {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  margin-bottom: 3px;
  text-transform: uppercase;
}
.idea-detail-metadata-list dd {
  color: var(--text-soft);
  font-size: 11px;
  margin: 0;
  overflow-wrap: anywhere;
}
.idea-detail-muted {
  color: var(--text-muted);
  font-size: 12px;
  margin: 0;
}

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 650;
  font-family: inherit;
  cursor: pointer;
  min-height: 28px;
  min-width: 0;
  overflow-wrap: anywhere;
  padding: 6px 14px;
  text-align: center;
  transition: background 0.12s, border-color 0.12s, color 0.12s, opacity 0.12s, transform 0.12s;
  white-space: normal;
}
.btn:hover:not(:disabled) { transform: translateY(-1px); }
.btn:focus-visible,
.icon-btn:focus-visible,
.nt-worker-card:focus-visible,
summary:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary {
  background: var(--accent);
  border-color: rgba(63,185,80,0.58);
  box-shadow: 0 0 0 1px rgba(63,185,80,0.12);
  color: #fff;
}
.btn-primary:hover:not(:disabled) { background: #2ea043; border-color: rgba(63,185,80,0.78); }
.btn-secondary {
  background: #1f2630;
  border-color: #3a4654;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.035);
  color: var(--text);
}
.btn-secondary:hover:not(:disabled) { background: #27313d; border-color: #536171; color: #f0f3f6; }
.btn-readonly {
  background: rgba(88,166,255,0.10);
  border-color: rgba(88,166,255,0.42);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.035);
  color: #9ccbff;
}
.btn-readonly:hover:not(:disabled) {
  background: rgba(88,166,255,0.18);
  border-color: rgba(88,166,255,0.68);
  color: #d3e8ff;
}
.btn-caution {
  background: rgba(210,153,34,0.13);
  border-color: rgba(210,153,34,0.50);
  box-shadow: 0 0 0 1px rgba(210,153,34,0.09);
  color: #f0c36a;
}
.btn-caution:hover:not(:disabled) {
  background: rgba(210,153,34,0.22);
  border-color: rgba(210,153,34,0.76);
  color: #ffe0a3;
}
.btn-danger {
  background: rgba(248,81,73,0.13);
  border-color: rgba(248,81,73,0.48);
  color: #ff9b95;
}
.btn-danger:hover:not(:disabled) {
  background: rgba(248,81,73,0.20);
  border-color: rgba(248,81,73,0.72);
  color: #ffd0cc;
}
.btn-sm { font-size: 11px; min-height: 26px; padding: 4px 11px; }
.icon-btn {
  align-items: center;
  background: #1d242d;
  border: 1px solid #384453;
  border-radius: var(--radius-sm);
  color: var(--text);
  cursor: pointer;
  display: inline-flex;
  font: inherit;
  font-size: 11px;
  font-weight: 650;
  justify-content: center;
  min-height: 26px;
  min-width: 0;
  overflow-wrap: anywhere;
  padding: 4px 8px;
  text-align: center;
  white-space: normal;
}
.icon-btn:hover { background: #27313d; border-color: #536171; color: #f0f3f6; }

/* ===== NEXT TASK LAUNCHPAD ===== */
.orchestrator-content { padding: 9px 12px; display: flex; flex-direction: column; gap: 8px; }
.next-task-content {
  max-width: 920px;
  width: 100%;
  margin: 0 auto;
}
.orchestrator-section.is-idle .operator-next-steps,
.orchestrator-section.is-idle .next-task-meta,
.orchestrator-section.is-idle .next-task-definition,
.orchestrator-section.is-idle #next-task-action-slot,
.orchestrator-section.is-idle #serial-runtime-panel,
.orchestrator-section.is-idle #next-task-latest-evidence,
.orchestrator-section.is-idle .next-task-switcher-wrap,
.orchestrator-section.is-idle #next-task-command-output {
  display: none !important;
}
.orchestrator-section.is-idle .orchestrator-content {
  align-items: center;
  display: grid;
  gap: 8px 14px;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 0.8fr);
  padding: 7px 12px 9px;
}
.orchestrator-section.is-idle .panel-header {
  border-bottom: 0;
  min-height: 36px;
}
.orchestrator-section.is-idle .orchestrator-directive .label {
  display: none;
}
.orchestrator-section.is-idle .orchestrator-directive .next-task-title {
  font-size: 13px;
  margin: 0 0 1px;
}
.orchestrator-section.is-idle .orchestrator-directive p {
  font-size: 12px;
  margin-bottom: 0;
}
.orchestrator-section.is-idle .next-action {
  min-width: 0;
}
.orchestrator-section.is-idle .next-action .label {
  font-size: 9px;
}
.orchestrator-section.is-idle .next-action code {
  font-size: 11px;
  min-height: 28px;
  padding: 5px 8px;
  white-space: normal;
}
.orchestrator-directive .label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.operator-next-steps {
  border-bottom: 1px solid var(--border-light);
  display: grid;
  gap: 6px;
  padding: 8px 12px 9px;
}
.operator-next-steps-head {
  align-items: baseline;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  min-width: 0;
}
.operator-next-steps-head strong {
  color: var(--text);
  font-size: 13px;
  letter-spacing: 0.2px;
}
.operator-next-steps-head span {
  color: var(--text-muted);
  font-size: 11px;
  text-align: right;
}
.operator-next-steps-grid {
  display: grid;
  gap: 6px;
  grid-template-columns: minmax(0, 1.25fr) minmax(0, 1.45fr) repeat(3, minmax(0, 1fr));
}
.operator-next-step {
  align-content: start;
  background: linear-gradient(90deg, var(--task-card-tint, rgba(88,166,255,0.04)), transparent 78%), var(--bg);
  border: 1px solid var(--task-accent-border, var(--border-light));
  border-left: 3px solid var(--task-accent, var(--blue));
  border-radius: var(--radius-sm);
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 6px 7px;
}
.operator-next-step > span {
  color: var(--text-muted);
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.35px;
  text-transform: uppercase;
}
.operator-next-step strong {
  color: var(--text-soft);
  font-size: 11px;
  line-height: 1.3;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.operator-next-step em {
  color: var(--text-muted);
  font-size: 11px;
  font-style: normal;
}
.operator-next-step .btn {
  justify-self: start;
  margin-top: 1px;
}
@media (max-width: 1180px) {
  .operator-next-steps-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .operator-next-steps-head { align-items: flex-start; flex-direction: column; gap: 3px; }
  .operator-next-steps-head span { text-align: left; }
  .operator-next-steps-grid { grid-template-columns: 1fr; }
}
.orchestrator-directive .next-task-title { margin: 4px 0 2px; font-size: 15px; font-weight: 600; color: var(--text); display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.next-task-summary .next-task-title { overflow-wrap: anywhere; }
.nt-task-id { font-size: 12px; font-weight: 700; color: var(--blue); background: var(--blue-soft); padding: 1px 8px; border-radius: 4px; flex-shrink: 0; }
.nt-task-title { font-size: 15px; font-weight: 600; color: var(--text); }
.orchestrator-directive p { margin: 0 0 8px; font-size: 13px; color: var(--text-soft); display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.nt-worker-info { color: var(--text); font-weight: 500; }
.nt-reason { color: var(--text-muted); font-size: 12px; }

/* Shared task status vocabulary */
.task-tone-red {
  --task-accent: var(--red);
  --task-accent-soft: var(--red-soft);
  --task-accent-border: rgba(248, 81, 73, 0.34);
  --task-card-tint: rgba(248, 81, 73, 0.045);
}
.task-tone-orange {
  --task-accent: var(--orange);
  --task-accent-soft: var(--orange-soft);
  --task-accent-border: rgba(210, 153, 34, 0.34);
  --task-card-tint: rgba(210, 153, 34, 0.045);
}
.task-tone-blue {
  --task-accent: var(--blue);
  --task-accent-soft: var(--blue-soft);
  --task-accent-border: rgba(88, 166, 255, 0.28);
  --task-card-tint: rgba(88, 166, 255, 0.04);
}
.task-tone-green {
  --task-accent: var(--accent);
  --task-accent-soft: var(--accent-soft);
  --task-accent-border: rgba(63, 185, 80, 0.30);
  --task-card-tint: rgba(63, 185, 80, 0.045);
}
.task-tone-gray {
  --task-accent: var(--text-muted);
  --task-accent-soft: rgba(110, 118, 129, 0.12);
  --task-accent-border: rgba(110, 118, 129, 0.24);
  --task-card-tint: rgba(110, 118, 129, 0.035);
}
.task-rail-red { border-left-color: var(--red) !important; }
.task-rail-orange { border-left-color: var(--orange) !important; }
.task-rail-blue { border-left-color: var(--blue) !important; }
.task-rail-green { border-left-color: var(--accent) !important; }
.task-rail-gray { border-left-color: var(--text-muted) !important; }
.task-status-badge {
  align-items: center;
  background: var(--task-accent-soft);
  border: 1px solid var(--task-accent-border);
  border-radius: 999px;
  color: var(--task-accent);
  display: inline-flex;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.35px;
  line-height: 1.2;
  max-width: 100%;
  min-height: 18px;
  padding: 2px 7px;
  text-transform: uppercase;
  white-space: nowrap;
}

/* Lane status badges */
.lane-badge { display: inline-flex; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 999px; text-transform: uppercase; letter-spacing: 0.5px; }
.lane-red { background: var(--red-soft); color: var(--red); }
.lane-orange { background: var(--orange-soft); color: var(--orange); }
.lane-blue { background: var(--blue-soft); color: var(--blue); }
.lane-green { background: var(--accent-soft); color: var(--accent); }
.lane-gray { background: rgba(110,118,129,0.15); color: var(--text-muted); }

/* Verification badges */
.verify-badge { display: inline-flex; font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 999px; }
.verify-passed { background: var(--accent-soft); color: var(--accent); }
.verify-failed { background: var(--red-soft); color: var(--red); }
.verify-notrun { background: rgba(110,118,129,0.12); color: var(--text-muted); }

/* Metadata cards */
.next-task-meta {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  min-width: 0;
}
.next-task-definition,
.next-task-evidence {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-left: 3px solid transparent;
  border-radius: var(--radius-sm);
  padding: 7px 9px;
}
.next-task-definition[hidden],
.next-task-switcher-wrap[hidden] { display: none !important; }
.next-task-evidence {
  background: transparent;
  border: 0;
  padding: 0;
}
.nt-meta-card {
  align-items: baseline;
  background: transparent;
  border: 0;
  border-radius: 0;
  display: inline-flex;
  gap: 6px;
  min-height: 0;
  min-width: 0;
  padding: 0;
}
.nt-meta-card > span:not(.task-status-badge):not(.lane-badge):not(.verify-badge),
.next-task-definition .label,
.next-task-evidence .label {
  display: block;
  color: var(--text-muted);
  font-size: 10px;
  letter-spacing: 0.4px;
  margin-bottom: 3px;
  text-transform: uppercase;
}
.nt-meta-card strong {
  display: inline-block;
  color: var(--text);
  font-size: 12px;
  max-width: 230px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nt-meta-secondary {
  align-items: center;
  display: flex;
  flex: 1 1 100%;
  gap: 6px 14px;
  min-width: 0;
}
.nt-meta-mini {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 0;
  display: flex;
  gap: 8px;
  min-width: 0;
  padding: 0;
}
.nt-meta-mini span {
  color: var(--text-muted);
  flex-shrink: 0;
  font-size: 10px;
  letter-spacing: 0.35px;
  text-transform: uppercase;
}
.nt-meta-mini strong {
  color: var(--text-soft);
  font-size: 11px;
  font-weight: 600;
  max-width: 360px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.next-task-definition p {
  margin: 0;
  color: var(--text-soft);
  font-size: 12px;
  line-height: 1.45;
  max-height: 58px;
  overflow: auto;
  white-space: pre-wrap;
}
.next-action { display: flex; flex-direction: column; gap: 2px; }
.next-action code {
  padding: 6px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-left: 3px solid var(--blue);
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-family: "SF Mono", "Cascadia Code", ui-monospace, monospace;
  color: var(--text);
  overflow-x: auto;
  white-space: nowrap;
}
.orchestrator-agents { display: flex; flex-direction: column; gap: 6px; }
.orchestrator-agents .label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.agent-progress-list { display: flex; flex-direction: column; gap: 4px; }
""" + TASK_CONTROL_WORKBENCH_CSS + """/* ===== FOOTER ===== */
.app-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  font-size: 11px;
  color: var(--text-muted);
  border-top: 1px solid var(--border);
  background: var(--bg);
}
.footer-sep { color: var(--border); }
.app-footer .version { margin-left: auto; }
.app-footer .status-dot { width: 6px; height: 6px; }

/* ===== FOCUS OVERLAY ===== */
.focus-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  z-index: 500;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.15s ease;
}
.focus-overlay[hidden] { display: none; }
.focus-panel {
  width: 700px;
  max-height: 80vh;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 20px 60px rgba(0,0,0,0.4);
  overflow: auto;
  position: relative;
}
.focus-close {
  position: absolute;
  top: 12px;
  right: 12px;
  margin: 0;
  width: 30px; height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text-soft);
  font-size: 18px;
  cursor: pointer;
  z-index: 1;
}
.focus-close:hover { background: var(--panel-hover); color: var(--text); }
#focus-content { padding: 44px 24px 24px; }
.focus-task-head {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: start;
  gap: 10px;
  margin-bottom: 14px;
}
.focus-task-head h2 {
  margin: 0;
  font-size: 18px;
  line-height: 1.35;
  color: var(--text);
}
.focus-task-id {
  color: var(--blue);
  font-size: 12px;
  font-weight: 700;
  padding-top: 3px;
}
.focus-status {
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  text-transform: uppercase;
}
.focus-status.good { background: var(--accent-soft); color: var(--accent); }
.focus-status.warn { background: var(--orange-soft); color: var(--orange); }
.focus-status.bad { background: var(--red-soft); color: var(--red); }
.focus-status.neutral { background: var(--bg-3); color: var(--text-soft); }
.focus-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}
.focus-grid div,
.task-command-box,
.focus-section {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  padding: 9px 10px;
}
.focus-grid div {
  background: linear-gradient(90deg, var(--task-card-tint, transparent), transparent 70%), var(--bg);
  border-left: 3px solid transparent;
}
.focus-grid > div > span:not(.task-status-badge):not(.lane-badge):not(.verify-badge),
.task-command-box label {
  display: block;
  color: var(--text-muted);
  font-size: 10px;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  margin-bottom: 3px;
}
.focus-grid .task-status-badge { margin-top: 2px; }
.focus-grid strong {
  display: block;
  color: var(--text);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-command-box { margin: 8px 0; }
.task-command-box code,
.path-line {
  display: block;
  background: #070a0f;
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text-soft);
  font-size: 11px;
  padding: 6px 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-command-box p { margin: 6px 0 0; color: var(--text-muted); font-size: 12px; }
.inline-command-row { display: flex; gap: 8px; align-items: center; }
.inline-command-row input,
.inline-command-row select,
.task-command-box textarea {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  font: inherit;
  font-size: 12px;
  min-width: 0;
  padding: 7px 9px;
}
.inline-command-row input { flex: 1; }
.task-command-box textarea {
  display: block;
  min-height: 72px;
  resize: vertical;
  width: 100%;
}
.task-action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin: 10px 0;
}
.focus-section { margin-top: 10px; }
.focus-section h3 {
  margin: 0 0 7px;
  color: var(--text);
  font-size: 12px;
}
.focus-section ul { margin: 0; padding-left: 18px; color: var(--text-soft); font-size: 12px; }
.event-row {
  display: grid;
  grid-template-columns: 54px 150px minmax(0, 1fr);
  gap: 8px;
  padding: 5px 0;
  border-top: 1px solid var(--border-light);
  color: var(--text-soft);
  font-size: 11px;
}
.event-row:first-of-type { border-top: 0; }
.event-row span { color: var(--text-muted); }
.event-row strong { color: var(--text); font-weight: 600; }
.event-row em { color: var(--text-muted); font-style: normal; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.focus-section pre,
.command-result pre {
  background: #070a0f;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font-size: 11px;
  margin: 0;
  max-height: 220px;
  overflow: auto;
  padding: 8px;
  white-space: pre-wrap;
}
.command-result {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-top: 10px;
  padding: 9px;
}
.command-result.good { border-color: rgba(63,185,80,0.28); background: rgba(63,185,80,0.05); }
.command-result.bad { border-color: rgba(248,81,73,0.28); background: rgba(248,81,73,0.05); }
.command-result.blocked { border-color: rgba(210,153,34,0.36); background: rgba(210,153,34,0.07); }
.command-result.validation { border-color: rgba(248,81,73,0.30); background: rgba(248,81,73,0.06); }
.command-result.pending { border-color: var(--border); background: var(--bg); }
.command-result-classification,
.command-result-field {
  border: 1px solid var(--border-light);
  border-radius: 999px;
  color: var(--text-soft);
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.3px;
  padding: 2px 7px;
  text-transform: uppercase;
}
.command-result-classification { background: var(--orange-soft); border-color: rgba(210,153,34,0.26); color: var(--orange); }
.command-result-field { background: rgba(248,81,73,0.10); border-color: rgba(248,81,73,0.24); color: var(--red); }
.command-result-truncated { color: var(--text-muted) !important; font-size: 11px !important; }
.command-result-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 7px;
}
.command-result-head strong { color: var(--text); font-size: 12px; white-space: nowrap; }
.command-result-head code {
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.command-result p { margin: 0 0 7px; color: var(--text-soft); font-size: 12px; }
.command-result pre.stderr { color: var(--red); margin-top: 6px; }

/* ===== STATUS BADGE (unified) ===== */
/* One consistent badge system: active/idle/empty/online/warn/bad */
.status-badge {
  align-items: center;
  border: 1px solid transparent;
  border-radius: 999px;
  display: inline-flex;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.3px;
  line-height: 1.2;
  min-height: 20px;
  padding: 2px 8px;
  text-transform: uppercase;
  white-space: nowrap;
}
.status-badge.online,
.status-badge.active {
  background: var(--accent-soft);
  border-color: rgba(63, 185, 80, 0.28);
  color: var(--accent);
}
.status-badge.idle,
.status-badge.empty {
  background: rgba(110, 118, 129, 0.10);
  border-color: rgba(110, 118, 129, 0.22);
  color: var(--text-soft);
}
.status-badge.warn {
  background: var(--orange-soft);
  border-color: rgba(210, 153, 34, 0.28);
  color: var(--orange);
}
.status-badge.bad,
.status-badge.error {
  background: var(--red-soft);
  border-color: rgba(248, 81, 73, 0.28);
  color: var(--red);
}
.info-icon { font-size: 14px; color: var(--text-muted); cursor: help; }

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* ===== RESPONSIVE ===== */
@media (max-width: 1400px) {
  .chat-sidebar { flex: 0 0 300px; width: 300px; }
}
@media (min-width: 1201px) {
  .task-control-grid {
    gap: 8px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    padding: 10px;
  }
  .dock-panel-header {
    min-height: 38px;
    padding: 8px 10px;
  }
  .worker-lanes-list,
  .review-queue-list,
  .evidence-stream-list {
    max-height: 230px;
    padding: 6px;
  }
}
@media (max-width: 1200px) {
  .task-control-grid { grid-template-columns: 1fr 1fr; }
  .chat-sidebar { flex: 0 0 280px; width: 280px; }
  .architecture-metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .architecture-provenance-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .workbench-stage-path { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .task-control-grid { grid-template-columns: 1fr; gap: 12px; padding: 12px; }
  .product-review-section { padding: 0 12px 16px; }
  .sidebar { display: none; }
  .topbar { padding: 8px 12px; gap: 8px; }
  .topbar-left { flex: 1 1 100%; gap: 8px; min-width: 0; }
  .topbar-right { flex: 1 1 100%; justify-content: space-between; min-width: 0; }
  .repo-selector { flex: 1 1 100%; min-width: 0; }
  .repo-info { min-width: 0; }
  .repo-info strong,
  .repo-path {
    display: block;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .topbar-pill { flex: 1 1 0; justify-content: center; min-width: 0; padding: 5px 8px; }
  .topbar-pill strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .panel { margin-bottom: 10px; }
  .panel-header { min-height: 44px; padding: 10px 12px; }
  .unified-workbench-section .panel-subtitle { display: none; }
  .brainstorm-transcript { min-height: 260px; max-height: 420px; padding: 10px 12px; }
  .brainstorm-chat-form { padding: 8px 12px; }
  .brainstorm-chat-form textarea { min-height: 38px; padding: 8px 10px; }
  .idea-capture-form { padding: 8px 10px 10px; }
  .idea-capture-form textarea { min-height: 44px; }
  .idea-capture-form input { flex: 1 1 150px; }
  .idea-capture-form .btn { flex: 0 0 auto; }
  .idea-primary-action:not(:empty) { margin: 0 12px 10px; }
  .idea-greenhouse-lanes { grid-template-columns: repeat(3, minmax(0, 1fr)); padding: 6px 8px 8px; }
  .idea-greenhouse-lanes:has(.idea-card) { max-height: 104px; }
  .idea-lane > .idea-card-meta { display: none; }
  .pipeline-stages { padding: 8px 12px; }
  .pipeline-primary-context { grid-template-columns: 1fr; }
  .pipeline-step { gap: 8px; }
  .pipeline-step:not(:last-child) { padding-bottom: 4px; }
  .step-number { min-width: 24px; }
  .step-number span { width: 24px; height: 24px; font-size: 11px; }
  .step-connector { height: 16px; }
  .step-desc { display: none; }
  .step-action { margin-top: 4px; }
  .layout-columns { flex-direction: column; padding: 0 12px; }
  .main-content { max-height: none; padding: 0; position: static; }
  .chat-sidebar {
    flex: 0 0 auto;
    max-height: none;
    position: static;
    width: 100%;
  }
  .chat-sidebar .brainstorm-section {
    max-height: none;
    min-height: 0;
  }
  .next-task-meta,
  .nt-meta-secondary { align-items: flex-start; flex-direction: column; }
  .nt-evidence-list { grid-template-columns: 1fr; }
  .nt-reconcile-action { align-items: flex-start; grid-template-columns: 1fr; padding-right: 0; }
  .nt-reconcile-action .btn { justify-self: start; }
  .architecture-summary-row,
  .architecture-evidence-grid { grid-template-columns: 1fr; }
  .architecture-metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .architecture-provenance-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .architecture-question-block { grid-column: auto; }
  .workbench-overview { gap: 6px; grid-template-columns: 1fr; padding: 6px 10px 0; }
  .workbench-stage-path { gap: 4px; grid-template-columns: repeat(5, minmax(0, 1fr)); }
  .workbench-stage-chip { min-height: 32px; padding: 5px 4px; }
  .workbench-stage-chip strong { font-size: 10px; }
  .workbench-stage-chip code,
  .workbench-gate-card em,
  .workbench-next-action code { display: none; }
  .workbench-gate-strip { gap: 6px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .workbench-gate-card { align-items: flex-start; flex-direction: column; gap: 5px; padding: 6px; }
  .workbench-gate-card span { display: none; }
  .workbench-next-action span,
  .workbench-result-card span { font-size: 10px; }
  .workbench-next-action { gap: 6px; padding: 6px; }
  .workbench-stage-path,
  .workbench-implement-result { grid-column: auto; }
  .workbench-next-action { align-items: flex-start; flex-direction: column; }
  .workbench-next-buttons { justify-content: flex-start; }
}

/* ===== BUILDER-JUDGE LOOP ===== */
.refactor-section,
.builder-judge-section { margin-top: 8px; }
.refactor-section .bj-form-row { align-items: flex-end; }
.refactor-section .btn { flex-shrink: 0; min-height: 29px; }
.refactor-result {
  color: var(--text-soft);
  display: grid;
  font-size: 12px;
  gap: 6px;
  padding-top: 4px;
}
.refactor-result-card {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  display: grid;
  gap: 5px;
  padding: 8px 10px;
}
.refactor-result-card.good { border-left: 3px solid var(--accent); }
.refactor-result-card.warn { border-left: 3px solid var(--orange); }
.refactor-result-card.bad { border-left: 3px solid var(--red); }
.refactor-result-card code {
  background: #070a0f;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  display: block;
  font-size: 11px;
  overflow: hidden;
  padding: 5px 7px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.refactor-work-view { display: grid; gap: 12px; }
.refactor-work-head .focus-status { border: 1px solid var(--border); }
.refactor-status-good { background: var(--accent-soft); color: var(--accent); }
.refactor-status-warn { background: var(--orange-soft); color: var(--orange); }
.refactor-status-bad { background: var(--red-soft); color: var(--red); }
.refactor-status-neutral { background: var(--bg-3); color: var(--text-soft); }
.refactor-rationale-box p {
  color: var(--text-soft);
  font-size: 12px;
  line-height: 1.45;
  margin: 0 0 8px;
}
.refactor-phase-list {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
}
.refactor-phase {
  background: var(--bg-2);
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--text-muted);
  border-radius: var(--radius-sm);
  display: grid;
  gap: 2px;
  min-height: 72px;
  padding: 8px 10px;
}
.refactor-phase span { color: var(--text); font-size: 12px; font-weight: 700; }
.refactor-phase strong { color: var(--text-soft); font-size: 10px; text-transform: uppercase; }
.refactor-phase em { color: var(--text-muted); font-size: 11px; font-style: normal; line-height: 1.35; }
.refactor-phase-done { border-left-color: var(--accent); }
.refactor-phase-active { border-left-color: var(--orange); }
.refactor-phase-pending { border-left-color: var(--text-muted); }
.refactor-work-tabs {
  align-items: center;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  gap: 6px;
  overflow-x: auto;
  padding-top: 4px;
}
.refactor-tab {
  background: transparent;
  border: 0;
  border-bottom: 2px solid transparent;
  color: var(--text-soft);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  padding: 7px 8px;
}
.refactor-tab.active {
  border-bottom-color: var(--accent);
  color: var(--text);
}
.refactor-tab-panels section {
  display: grid;
  gap: 10px;
  padding-top: 6px;
}
.refactor-tab-panels section[hidden] { display: none; }
.refactor-tab-panels h3 {
  color: var(--text);
  font-size: 14px;
  margin: 0;
}
.refactor-overview-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}
.refactor-evidence-card {
  background: var(--bg-2);
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--text-muted);
  border-radius: var(--radius-sm);
  display: grid;
  gap: 4px;
  padding: 9px 10px;
}
.refactor-evidence-card.good { border-left-color: var(--accent); }
.refactor-evidence-card.warn { border-left-color: var(--orange); }
.refactor-evidence-card.muted { border-left-color: var(--text-muted); }
.refactor-evidence-card strong { color: var(--text); font-size: 12px; }
.refactor-evidence-card code {
  color: var(--text-muted);
  font-size: 11px;
  overflow-wrap: anywhere;
}
.refactor-evidence-card span,
.refactor-panel-note,
.refactor-empty {
  color: var(--text-soft);
  font-size: 12px;
  line-height: 1.4;
  margin: 0;
}
.refactor-log-tail {
  background: #070a0f;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font-size: 12px;
  line-height: 1.45;
  margin: 0;
  max-height: 360px;
  overflow: auto;
  padding: 10px;
  white-space: pre-wrap;
  word-break: break-word;
}
.refactor-artifact-list { display: grid; gap: 6px; }
.refactor-artifact {
  align-items: center;
  background: var(--bg-2);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(90px, 0.6fr) minmax(0, 2fr) auto;
  padding: 7px 9px;
}
.refactor-artifact span,
.refactor-artifact strong {
  color: var(--text-soft);
  font-size: 11px;
}
.refactor-artifact code {
  color: var(--text);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (max-width: 720px) {
  .refactor-artifact { grid-template-columns: 1fr; }
  .refactor-work-tabs { flex-wrap: wrap; }
}
.bj-form-area { display: flex; flex-direction: column; gap: 6px; padding: 8px 0; }
.bj-form-group { display: flex; flex-direction: column; gap: 2px; }
.bj-form-group label { font-size: 10px; color: var(--text-soft); font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.bj-form-group textarea, .bj-form-group select, .bj-form-group input {
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm);
  color: var(--text); padding: 4px 8px; font-size: 12px; outline: none; font-family: inherit;
}
.bj-form-group textarea:focus, .bj-form-group select:focus, .bj-form-group input:focus {
  border-color: var(--accent);
}
""" + BUILDER_JUDGE_MODEL_PICKER_CSS + """.bj-checkbox-group { justify-content: center; }
.bj-checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-soft); cursor: pointer; text-transform: none !important; letter-spacing: 0 !important; font-weight: 400 !important; }
.bj-required { color: var(--red); }
.bj-optional { color: var(--text-muted); font-weight: 400; text-transform: none; }

@media (max-width: 720px) {
  .bj-form-row {
    align-items: stretch;
    flex-direction: column;
  }
}

.bj-progress-area { padding: 8px 0; border-top: 1px solid var(--border-light); }
.bj-rounds-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.bj-round-summary { font-size: 12px; color: var(--text-soft); }
.bj-rounds-list { display: flex; flex-direction: column; gap: 8px; max-height: 400px; overflow-y: auto; }
.bj-running-msg { color: var(--text-soft); font-size: 13px; padding: 12px; text-align: center; font-style: italic; }
.bj-error-msg { color: var(--red); font-size: 13px; padding: 12px; }

.bj-round-card {
  background: var(--bg-2); border: 1px solid var(--border-light); border-radius: var(--radius-sm);
  padding: 10px 12px; border-left: 3px solid var(--text-muted);
}
.bj-round-card.bj-score-pass { border-left-color: var(--accent); }
.bj-round-card.bj-score-warn { border-left-color: var(--orange); }
.bj-round-card.bj-score-fail { border-left-color: var(--red); }
.bj-round-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.bj-round-num { font-size: 13px; font-weight: 700; color: var(--text); }
.bj-round-score { font-size: 14px; font-weight: 700; margin-left: auto; }
.bj-score-pass .bj-round-score { color: var(--accent); }
.bj-score-warn .bj-round-score { color: var(--orange); }
.bj-score-fail .bj-round-score { color: var(--red); }
.bj-passed-badge { background: var(--accent-soft); color: var(--accent); padding: 1px 6px; border-radius: 3px; font-size: 10px; font-weight: 700; }
.bj-round-models { display: flex; gap: 12px; font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
.bj-judge-feedback { font-size: 12px; color: var(--text-soft); margin: 4px 0; }
.bj-issues { margin: 4px 0 0 0; padding-left: 16px; }
.bj-issues li { font-size: 12px; color: var(--orange); margin-bottom: 2px; }
.bj-round-error { color: var(--red); font-size: 12px; margin-top: 4px; }

.bj-result-area { padding: 12px 0; border-top: 1px solid var(--border-light); }
.bj-result-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.bj-result-header h3 { font-size: 14px; margin: 0; }
.bj-score-badge { font-size: 16px; font-weight: 700; padding: 2px 10px; border-radius: 4px; }
.bj-score-badge.bj-score-pass { background: var(--accent-soft); color: var(--accent); }
.bj-score-badge.bj-score-warn { background: var(--orange-soft); color: var(--orange); }
.bj-final-draft { background: var(--bg); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 10px; margin: 8px 0; max-height: 300px; overflow-y: auto; }
.bj-draft-pre { white-space: pre-wrap; word-break: break-word; font-size: 13px; color: var(--text); font-family: inherit; margin: 0; }
.bj-stop-reason { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
.bj-next-action { font-size: 12px; color: var(--blue); margin-top: 4px; }

.bj-history-header { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--border-light); }
.bj-loops-list { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; max-height: 200px; overflow-y: auto; }
.bj-empty-state { color: var(--text-muted); font-size: 12px; padding: 8px; text-align: center; }
.bj-loop-item { background: var(--bg-2); border: 1px solid var(--border-light); border-radius: var(--radius-sm); padding: 8px 10px; cursor: pointer; transition: border-color 0.15s; }
.bj-loop-item:hover { border-color: var(--border); }
.bj-loop-item-header { display: flex; align-items: center; gap: 8px; }
.bj-loop-status { font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 3px; text-transform: uppercase; }
.bj-status-pass { background: var(--accent-soft); color: var(--accent); }
.bj-status-escalate { background: var(--orange-soft); color: var(--orange); }
.bj-status-fail { background: var(--red-soft); color: var(--red); }
.bj-status-other { background: var(--blue-soft); color: var(--blue); }
.bj-loop-score { font-size: 12px; font-weight: 700; margin-left: auto; }
.bj-loop-rounds { font-size: 11px; color: var(--text-muted); }
.bj-loop-dod { font-size: 11px; color: var(--text-soft); margin: 4px 0 2px; }
.bj-loop-models { display: flex; gap: 12px; font-size: 10px; color: var(--text-muted); }

/* ===== CLASSIFY FORM (Slice 2) ===== */
.idea-detail-classify-section { background: var(--bg-3); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px 14px; margin-top: 8px; }
.idea-classify-title { font-size: 13px; font-weight: 600; color: var(--text); margin: 0 0 8px; }
.idea-classify-row { display: flex; gap: 8px; align-items: stretch; margin-bottom: 8px; }
.idea-classify-select { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px 8px; color: var(--text); font-size: 12px; font-family: inherit; cursor: pointer; flex: none; width: 150px; }
.idea-classify-select:focus { border-color: var(--accent); outline: none; }
.idea-classify-note { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px 8px; color: var(--text); font-size: 12px; font-family: inherit; flex: 1; resize: vertical; min-height: 32px; }
.idea-classify-note:focus { border-color: var(--accent); outline: none; }
.idea-classify-error { color: var(--red); font-size: 11px; margin-top: 4px; margin-bottom: 4px; }
.idea-classify-note-error, .idea-classify-select-error { border-color: var(--red) !important; }

/* ===== PARK/ARCHIVE FORM (Slice 3) ===== */
.idea-detail-park-section,
.idea-detail-archive-section { background: var(--bg-3); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px 14px; margin-top: 8px; }
.idea-archive-title { font-size: 13px; font-weight: 600; color: var(--text); margin: 0 0 8px; }
.idea-archive-reason { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px 8px; color: var(--text); font-size: 12px; font-family: inherit; flex: 1; resize: vertical; min-height: 32px; width: 100%; }
.idea-archive-reason:focus { border-color: var(--accent); outline: none; }
.idea-archive-reason::placeholder { color: var(--text-muted); }

/* ============================================================
   A11Y + UX IMPROVEMENTS
   ============================================================ */

/* --- Reduced motion: respect user preference --- */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .sidebar { transition: none !important; }
}

/* --- Utility classes (replaced inline styles) --- */
.btn-full { width: 100%; }
.btn-compact { padding: 2px 8px; font-size: 10px; }
.btn-compact-md { padding: 3px 10px; font-size: 11px; }
.btn-icon-sm { padding: 2px 8px; font-size: 10px; line-height: 1; }
.bj-number-input { width: 80px; }

/* Repo dropdown classes (replaced inline styles) */
.repo-current-path { padding: 4px 12px; font-size: 11px; color: var(--text-muted); word-break: break-all; }
.repo-browser { max-height: 300px; overflow-y: auto; padding: 4px 0; }
.repo-dropdown-footer { padding: 8px 12px; border-top: 1px solid var(--border-light); display: flex; gap: 8px; align-items: center; }
.repo-path-input {
  flex: 1; padding: 4px 8px; font-size: 12px;
  background: var(--bg); border: 1px solid var(--border);
  border-radius: var(--radius-sm); color: var(--text); outline: none;
}
.repo-path-input:focus { border-color: var(--accent); }
.repo-open-btn { padding: 4px 12px; font-size: 11px; }

/* --- Sidebar mobile toggle + backdrop --- */
.sidebar-toggle {
  display: none;
  background: none; border: none; color: var(--text-soft);
  padding: 6px; border-radius: var(--radius-sm); cursor: pointer;
  align-items: center; justify-content: center; flex-shrink: 0;
}
.sidebar-toggle:hover { color: var(--text); background: var(--panel-hover); }
.sidebar-toggle:focus-visible { outline: 2px solid var(--blue); outline-offset: 2px; }

.sidebar-backdrop {
  display: none;
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 19;
}

@media (max-width: 900px) {
  .sidebar-toggle { display: inline-flex; }
  .sidebar-backdrop:not([hidden]) { display: block; }
  .sidebar {
    position: fixed; top: 0; left: 0;
    transform: translateX(-100%);
    transition: transform 0.2s ease;
    z-index: 20;
    width: var(--sidebar-expanded-w);
  }
  .sidebar.mobile-open { transform: translateX(0); }
  /* When sidebar is fixed+open on mobile, show full labels without hover. */
  .sidebar.mobile-open .brand-text { display: block; }
  .sidebar.mobile-open .nav-item span { display: inline; }
  .sidebar.mobile-open .nav-item { justify-content: flex-start; }
  .sidebar.mobile-open .sidebar-status-card div { display: block; }
}

/* --- Keyboard navigation highlight for custom dropdowns --- */
.model-dropdown-item.keyboard-active,
.repo-browser .repo-browser-item.keyboard-active {
  background: var(--blue-soft);
  outline: 2px solid var(--blue);
  outline-offset: -2px;
}

/* --- Loading / skeleton / empty / error states --- */
.df-skeleton {
  background: linear-gradient(90deg, var(--bg-3) 25%, var(--panel-hover) 50%, var(--bg-3) 75%);
  background-size: 200% 100%;
  animation: df-shimmer 1.4s ease-in-out infinite;
  border-radius: var(--radius-sm);
  min-height: 14px;
}
@keyframes df-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.df-skeleton-line { height: 14px; margin: 6px 0; }
.df-skeleton-line.short { width: 60%; }

.df-empty-state {
  color: var(--text-muted); font-size: 12px;
  padding: 12px 8px; text-align: center;
  font-style: italic;
}

.df-error-banner {
  background: var(--red-soft); border: 1px solid rgba(248,81,73,0.34);
  border-radius: var(--radius-sm); padding: 8px 12px;
  color: var(--red); font-size: 12px;
  display: flex; align-items: center; gap: 8px;
  margin: 4px 0;
}
.df-error-banner::before {
  content: '⚠'; font-size: 14px; flex-shrink: 0;
}
.df-error-banner .df-error-dismiss {
  margin-left: auto; background: none; border: none;
  color: var(--red); cursor: pointer; font-size: 14px; padding: 0 4px;
}
.df-error-banner .df-error-dismiss:hover { opacity: 0.7; }

/* --- Status indicators: icon alongside color for colorblind users --- */
.task-tone-red .dock-status-note::before,
.task-tone-red .nt-worker-card-status::before { content: '✕ '; }
.task-tone-orange .dock-status-note::before,
.task-tone-orange .nt-worker-card-status::before { content: '◐ '; }
.task-tone-green .dock-status-note::before,
.task-tone-green .nt-worker-card-status::before { content: '✓ '; }
.task-tone-gray .dock-status-note::before,
.task-tone-gray .nt-worker-card-status::before { content: '○ '; }

/* Screen-reader-only utility */
.sr-only {
  position: absolute; width: 1px; height: 1px;
  padding: 0; margin: -1px; overflow: hidden;
  clip: rect(0,0,0,0); white-space: nowrap; border: 0;
}

/* Ensure focus-overlay content is scrollable if tall */
.focus-panel {
  max-height: 90vh;
  overflow-y: auto;
}

/* Repo browser items (replaced inline styles from JS) */
.repo-item { cursor: pointer; }
.repo-devflow-badge { font-size: 9px; color: var(--accent); margin-left: 4px; }
.repo-browser-empty { padding: 12px; text-align: center; color: var(--text-muted); font-size: 12px; }
"""
