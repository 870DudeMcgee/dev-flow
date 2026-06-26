from __future__ import annotations

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
  --text-muted: #6e7681;
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
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-2);
  gap: 12px;
  flex-wrap: wrap;
}
.topbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* Repo selector */
.repo-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
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
  padding: 5px 10px;
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

/* ===== LAYOUT COLUMNS ===== */
.layout-columns {
  display: flex;
  gap: 14px;
  padding: 14px 16px 0;
}
.center-column {
  flex: 1 1 0;
  min-width: 0;
  margin: 0 auto;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.right-column {
  align-self: flex-start;
  width: 320px;
  flex-shrink: 0;
  max-height: calc(100vh - 88px);
  padding: 0;
  position: sticky;
  top: 72px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.history-panel {
  flex: 0 0 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.history-list {
  overflow-y: auto;
  padding: 4px 0;
  max-height: 96px;
}
.history-panel details {
  border-top: 1px solid var(--border-light);
  padding: 0;
}

.right-column .brainstorm-section {
  display: flex;
  flex: 1 1 auto;
  height: calc(100vh - 174px);
  max-height: 760px;
  min-height: 460px;
}
.right-column .brainstorm-section .panel-header {
  align-items: flex-start;
  flex-direction: column;
  gap: 8px;
}
.right-column .brainstorm-section .panel-header-controls {
  align-items: stretch;
  flex-wrap: wrap;
  gap: 6px;
  width: 100%;
}
.right-column .brainstorm-section .model-selector-wrap {
  flex: 1 1 100%;
  min-width: 0;
}
.right-column .brainstorm-section .model-selector {
  justify-content: space-between;
  max-width: 100%;
  width: 100%;
}
.right-column .brainstorm-section .model-dropdown {
  left: 0;
  min-width: 260px;
  right: auto;
}
.right-column .brainstorm-section .evidence-toggle {
  flex: 1 1 100%;
}
.right-column .brainstorm-transcript {
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  padding: 10px;
}
.right-column .brainstorm-chat-form {
  padding: 8px 10px 10px;
}
.right-column .brainstorm-chat-form textarea {
  min-height: 86px;
}
.right-column .brainstorm-chat-form .composer-row {
  align-items: stretch;
  flex-wrap: wrap;
}
.right-column .newline-hint {
  flex: 1 1 100%;
  margin-right: 0;
}
.right-column #brainstorm-send {
  flex: 1 1 100%;
}
.right-column .brainstorm-msg {
  gap: 6px;
}
.right-column .msg-avatar {
  height: 24px;
  width: 24px;
}
.right-column .msg-body {
  max-width: calc(100% - 30px);
}
.history-panel summary {
  align-items: center;
  color: var(--text-soft);
  cursor: pointer;
  display: flex;
  font-size: 11px;
  font-weight: 700;
  gap: 8px;
  justify-content: space-between;
  list-style: none;
  min-height: 30px;
  padding: 6px 10px;
  text-transform: uppercase;
}
.history-panel summary::-webkit-details-marker { display: none; }
.history-panel summary::marker { content: ""; }
.history-panel summary:hover { background: var(--bg-3); color: var(--text); }
.history-panel summary output {
  color: var(--text-muted);
  font-size: 10px;
  text-transform: none;
}
.history-list .session-item {
  display: grid;
  gap: 2px;
  grid-template-columns: minmax(0, 1fr) auto;
  padding: 5px 10px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  border-bottom: 1px solid var(--border-light);
  transition: background 0.1s;
}
.history-list .session-item:hover { background: var(--bg-3); }
.history-list .session-item.active { background: var(--accent-bg); border-left: 2px solid var(--accent); }
.history-list .session-item .si-preview {
  font-size: 11px;
  color: var(--text);
  grid-column: 1 / 2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.25;
}
.history-list .session-item .si-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  grid-column: 2 / 3;
  grid-row: 1;
  margin-top: 0;
  white-space: nowrap;
}
.history-list .session-item .si-meta span {
  font-size: 9px;
  color: var(--text-muted);
}
.history-list .session-item .si-badge {
  font-size: 8px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--accent-soft);
  color: var(--accent);
}

/* ===== PANELS (generic) ===== */
.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  margin-bottom: 8px;
}
.center-column > .panel { margin-bottom: 0; flex-shrink: 0; }
.right-column > .panel { flex-shrink: 0; }
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-light);
  min-height: 42px;
}
.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: 0;
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

.model-selector {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--bg-3);
  border: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-soft);
  cursor: pointer;
}
.model-selector .chevron { color: var(--text-muted); }
.model-selector-wrap { position: relative; }
.model-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  z-index: 100;
  min-width: 280px;
  max-height: 320px;
  overflow-y: auto;
}
.model-dropdown-item {
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-light);
  transition: background 0.1s;
}
.model-dropdown-item:last-child { border-bottom: none; }
.model-dropdown-item:hover { background: var(--bg-3); }
.model-dropdown-item.active { background: var(--accent-bg); }
.model-dropdown-item .md-name { font-size: 12px; font-weight: 600; color: var(--text); }
.model-dropdown-item .md-model { font-size: 10px; color: var(--text-muted); margin-top: 2px; }
.model-dropdown-item .md-purpose { font-size: 10px; color: var(--text-soft); margin-top: 2px; line-height: 1.3; }

.evidence-toggle {
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
  gap: 8px;
  min-width: 0;
  padding: 10px 14px 12px;
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
  height: 48px;
  line-height: 1.45;
  max-height: 160px;
  min-height: 48px;
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
  gap: 8px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  max-width: 100%;
  min-width: 0;
  padding: 8px 12px 10px;
}
.idea-greenhouse-lanes:has(.idea-card) {
  max-height: 240px;
  overflow: hidden;
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
  gap: 8px;
  justify-content: space-between;
  min-width: 0;
  padding: 6px 10px;
}
.idea-lane-header strong {
  color: var(--text);
  font-size: 12px;
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
  font-size: 10px;
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
  gap: 5px;
  margin: 7px 8px;
  min-width: 0;
  padding: 8px 9px 9px 10px;
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
  font-size: 12px;
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
  font-size: 11px;
  font-weight: 800;
}
.idea-card-meta,
.idea-card-action,
.idea-card-command,
.idea-card p {
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.35;
  margin: 0;
  min-width: 0;
  overflow: hidden;
  overflow-wrap: anywhere;
  text-overflow: ellipsis;
  white-space: normal;
}
.idea-card-action {
  color: var(--text-soft);
  font-size: 11px;
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
.next-task-action-slot .task-command-box { margin: 0; }
.next-task-action-slot {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.serial-runtime-panel {
  background: linear-gradient(90deg, var(--task-card-tint, rgba(88,166,255,0.04)), transparent 72%), var(--bg);
  border: 1px solid var(--task-accent-border, var(--border-light));
  border-left: 3px solid var(--task-accent, var(--blue));
  border-radius: var(--radius-sm);
  display: grid;
  gap: 8px;
  padding: 9px 10px;
}
.serial-runtime-panel[hidden] { display: none !important; }
.serial-runtime-head {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  min-width: 0;
}
.serial-runtime-title {
  align-items: center;
  display: flex;
  gap: 8px;
  min-width: 0;
}
.serial-runtime-title strong { color: var(--text); font-size: 13px; }
.serial-runtime-title code { color: var(--text-soft); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.serial-runtime-grid {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}
.serial-runtime-field {
  background: rgba(13,17,23,0.42);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  min-width: 0;
  padding: 6px 7px;
}
.serial-runtime-field span,
.serial-runtime-next span,
.serial-runtime-evidence span,
.serial-runtime-command span {
  color: var(--text-muted);
  display: block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.35px;
  margin-bottom: 3px;
  text-transform: uppercase;
}
.serial-runtime-field code,
.serial-runtime-command code,
.serial-runtime-evidence code {
  color: var(--text-soft);
  font-size: 11px;
  overflow-wrap: anywhere;
}
.serial-runtime-next {
  background: rgba(88,166,255,0.06);
  border: 1px solid rgba(88,166,255,0.18);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font-size: 12px;
  line-height: 1.45;
  padding: 7px 8px;
}
.serial-runtime-evidence {
  display: grid;
  gap: 5px;
}
.serial-runtime-evidence-list {
  display: grid;
  gap: 4px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.serial-runtime-evidence-list code {
  background: rgba(13,17,23,0.42);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  padding: 4px 6px;
}
.serial-runtime-command {
  align-items: center;
  display: grid;
  gap: 6px;
  grid-template-columns: minmax(0, 1fr) auto;
}
.serial-runtime-command span,
.serial-runtime-command code { grid-column: 1 / 2; }
.serial-runtime-command .btn { grid-column: 2 / 3; grid-row: 1 / span 2; }
.serial-runtime-empty { color: var(--text-soft); font-size: 12px; margin: 0; }
@media (max-width: 760px) {
  .serial-runtime-grid,
  .serial-runtime-evidence-list,
  .serial-runtime-command,
  .nt-copy-command-row,
  .nt-command-preview { grid-template-columns: 1fr; }
  .serial-runtime-command .btn,
  .nt-command-preview .btn { grid-column: 1; grid-row: auto; justify-self: start; }
}

/* Primary action highlight */
.nt-primary-action { border-left: 3px solid var(--accent) !important; }
.nt-verify-action { border-left: 3px solid var(--orange) !important; }
.nt-impl-action { border-left: 3px solid var(--purple) !important; }
.nt-impl-action p { margin: 4px 0 0; color: var(--text-soft); font-size: 12px; }
.nt-worker-options { display: grid; gap: 8px; margin: 8px 0; }
.nt-worker-card {
  background: linear-gradient(135deg, rgba(88,166,255,0.09), rgba(188,140,255,0.06));
  border: 1px solid rgba(88,166,255,0.22);
  border-left: 3px solid var(--accent);
  border-radius: var(--radius-sm);
  cursor: pointer;
  padding: 9px 10px;
  transition: background 0.12s, border-color 0.12s, transform 0.12s, opacity 0.12s;
}
.nt-worker-card:hover:not(.is-disabled),
.nt-worker-card:focus-visible:not(.is-disabled) {
  background: linear-gradient(135deg, rgba(63,185,80,0.12), rgba(88,166,255,0.10));
  border-color: rgba(63,185,80,0.46);
  transform: translateY(-1px);
}
.nt-worker-card.is-disabled {
  background: linear-gradient(135deg, rgba(110,118,129,0.08), rgba(210,153,34,0.05));
  border-color: rgba(210,153,34,0.26);
  border-left-color: var(--orange);
  cursor: not-allowed;
  opacity: 0.78;
}
.nt-worker-card-head { align-items: center; display: flex; gap: 8px; justify-content: space-between; }
.nt-worker-card-head strong { color: var(--text); font-size: 13px; }
.nt-worker-badge {
  background: var(--blue-soft);
  border: 1px solid rgba(88,166,255,0.20);
  border-radius: 999px;
  color: var(--blue);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.35px;
  padding: 2px 7px;
  text-transform: uppercase;
}
.nt-worker-model { color: var(--text-muted); font-size: 11px; margin: 5px 0 0; }
.nt-worker-copy { color: var(--text-soft); font-size: 12px; margin: 5px 0 0; }
.nt-worker-command {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  display: block;
  font-size: 11px;
  margin: 0;
  overflow: hidden;
  padding: 5px 7px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nt-worker-blocked {
  background: rgba(210,153,34,0.08);
  border: 1px solid rgba(210,153,34,0.22);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font-size: 11px;
  line-height: 1.35;
  margin: 7px 0 0;
  padding: 5px 7px;
}
.nt-worker-blocked strong { color: var(--orange); }
.nt-copy-command-row,
.nt-command-preview {
  align-items: center;
  display: grid;
  gap: 6px;
  grid-template-columns: minmax(0, 1fr) auto;
  margin-top: 7px;
}
.nt-copy-command-row code,
.nt-command-preview code {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  display: block;
  font-size: 11px;
  min-width: 0;
  overflow: hidden;
  padding: 5px 7px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nt-command-preview span {
  color: var(--text-muted);
  display: block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.35px;
  text-transform: uppercase;
}
.nt-command-preview span,
.nt-command-preview code { grid-column: 1 / 2; }
.nt-command-preview .btn { grid-column: 2 / 3; grid-row: 1 / span 2; }
.nt-worker-btn { font-size: 12px !important; padding: 6px 14px !important; }
.nt-no-workers { padding: 8px 0; }
.nt-no-workers p { margin: 2px 0; font-size: 12px; color: var(--text-soft); }
.nt-hint { color: var(--text-muted) !important; font-size: 11px !important; }
.nt-hint code { background: var(--bg); padding: 1px 4px; border-radius: 3px; font-size: 11px; }
.nt-shell-fallback { margin-top: 8px; border-top: 1px solid var(--border-light); padding-top: 8px; }
.nt-shell-fallback summary { font-size: 11px; color: var(--text-muted); cursor: pointer; padding: 2px 0; }
.nt-shell-fallback summary:hover { color: var(--text-soft); }
.nt-shell-fallback .inline-command-row { margin-top: 6px; }
.nt-reconcile-action {
  align-items: center;
  background: linear-gradient(90deg, rgba(248,81,73,0.08), rgba(248,81,73,0.025) 62%, transparent);
  border: 1px solid rgba(248,81,73,0.20);
  border-left: 3px solid var(--red);
  border-radius: var(--radius-sm);
  display: grid;
  gap: 8px;
  grid-template-columns: minmax(0, 1fr) auto;
  margin: 0;
  padding: 7px 0 7px 10px;
}
.nt-reconcile-copy {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 5px 8px;
  min-width: 0;
}
.nt-reconcile-label {
  color: var(--red);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.35px;
  text-transform: uppercase;
}
.nt-reconcile-note {
  color: var(--text-soft);
  font-size: 11px;
}
.nt-reconcile-command {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font-size: 11px;
  max-width: 100%;
  overflow: hidden;
  padding: 4px 7px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nt-utility-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 0; }
.nt-utility-row .btn-ghost {
  background: #1d242d;
  border: 1px solid #384453;
  color: var(--text);
}
.nt-utility-row .btn-ghost:hover { background: #27313d; border-color: #536171; color: #f0f3f6; }

.nt-more-actions,
.nt-close-details,
.nt-evidence-details {
  min-width: 0;
}
.nt-more-actions > summary,
.nt-close-details > summary,
.nt-evidence-details > summary,
.nt-shell-fallback summary {
  align-items: center;
  background: #1b222b;
  border: 1px solid #34404d;
  border-radius: var(--radius-sm);
  color: var(--text);
  cursor: pointer;
  display: inline-flex;
  font-size: 11px;
  font-weight: 700;
  gap: 8px;
  min-height: 28px;
  padding: 5px 10px;
  user-select: none;
}
.nt-more-actions > summary:hover,
.nt-close-details > summary:hover,
.nt-evidence-details > summary:hover,
.nt-shell-fallback summary:hover {
  background: #242d38;
  border-color: #506071;
  color: #f0f3f6;
}
.nt-more-actions[open] > summary,
.nt-close-details[open] > summary,
.nt-evidence-details[open] > summary,
.nt-shell-fallback details[open] > summary {
  background: #26313d;
  border-color: var(--blue);
  color: #f0f3f6;
}
.nt-more-actions > summary::marker,
.nt-close-details > summary::marker,
.nt-evidence-details > summary::marker,
.nt-shell-fallback summary::marker { color: var(--blue); }
.nt-more-actions > summary::-webkit-details-marker,
.nt-close-details > summary::-webkit-details-marker,
.nt-evidence-details > summary::-webkit-details-marker,
.nt-shell-fallback summary::-webkit-details-marker { color: var(--blue); }

/* Close task collapsible */
.nt-close-details { margin-top: 4px; }
.nt-close-inner { display: flex; gap: 8px; align-items: center; padding: 8px 0 4px; }

/* Evidence list */
.nt-evidence-details {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}
.nt-evidence-details > summary {
  display: grid;
  grid-template-columns: minmax(0, auto) minmax(0, 1fr);
  justify-content: stretch;
  width: 100%;
}
.nt-evidence-details > summary span {
  align-items: baseline;
  display: inline-flex;
  gap: 8px;
  min-width: 0;
}
.nt-evidence-details > summary strong {
  color: var(--text);
  font-size: 11px;
  letter-spacing: 0.35px;
  text-transform: uppercase;
}
.nt-evidence-details > summary em {
  color: var(--text-soft);
  font-size: 11px;
  font-style: normal;
  font-weight: 600;
}
.nt-evidence-details > summary code {
  color: var(--text-muted);
  font-size: 11px;
  justify-self: end;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nt-evidence-body {
  border-top: 1px solid var(--border-light);
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 7px;
}
.nt-evidence-list {
  display: grid;
  gap: 4px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.nt-evidence-item {
  align-items: center;
  background: linear-gradient(90deg, var(--task-card-tint, transparent), transparent 68%), var(--bg);
  border: 1px solid var(--border-light);
  border-left: 3px solid transparent;
  border-radius: var(--radius-sm);
  display: flex;
  gap: 8px;
  padding: 5px 8px;
}
.nt-evidence-item:hover { border-color: var(--border); }
.nt-evidence-icon {
  color: var(--task-accent);
  flex-shrink: 0;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.35px;
  text-align: center;
  text-transform: uppercase;
  width: 34px;
}
.nt-evidence-item code { font-size: 11px; color: var(--text-soft); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.nt-evidence-preview {
  background: #070a0f;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font-size: 11px;
  margin: 6px 0 0;
  max-height: 72px;
  overflow: auto;
  padding: 8px;
  white-space: pre-wrap;
}
.next-task-evidence-empty { color: var(--text-muted); font-size: 12px; }

/* Task switcher with colored left border */
.task-switcher-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px 6px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--text-muted);
  background: linear-gradient(90deg, var(--task-card-tint, transparent), transparent 64%), var(--bg);
  color: var(--text-soft);
  cursor: pointer;
  font: inherit;
  text-align: left;
  transition: border-color 0.15s, background 0.1s;
}
.task-switcher-row:hover,
.task-switcher-row.selected {
  background: var(--panel-hover);
  border-color: var(--border);
}
.ts-lane-red { border-left-color: var(--red); }
.ts-lane-orange { border-left-color: var(--orange); }
.ts-lane-blue { border-left-color: var(--blue); }
.ts-lane-green { border-left-color: var(--accent); }
.ts-lane-gray { border-left-color: var(--text-muted); }
.task-switcher-row em.task-status-badge {
  color: var(--task-accent);
  display: inline-flex;
  font-size: 9px;
  justify-self: end;
}
.task-switcher-row span:nth-child(2) {
  display: flex;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-switcher-row strong { color: var(--blue); flex-shrink: 0; }
.task-switcher-row em { color: var(--text-muted); font-size: 10px; font-style: normal; white-space: nowrap; }
.agent-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg);
  border: 1px solid var(--border-light);
  cursor: pointer;
  transition: background 0.1s;
}
.agent-row:hover { background: var(--panel-hover); }
.agent-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.agent-dot.running { background: var(--accent); }
.agent-dot.waiting { background: var(--orange); }
.agent-dot.done { background: var(--text-muted); }
.agent-name { font-size: 12px; color: var(--text); flex: 1; }
.agent-task { font-size: 11px; color: var(--text-soft); }
.agent-time { font-size: 10px; color: var(--text-muted); }

/* ===== MISSION FEED ===== */
.mission-feed-section { margin-bottom: 0; }
.mission-feed-section.is-empty .panel-header {
  border-bottom: 0;
  min-height: 38px;
  padding: 9px 14px;
}
.mission-feed-section.is-empty .mission-feed-list {
  display: none;
}
.mission-feed-list { max-height: 180px; overflow-y: auto; padding: 6px 8px; display: flex; flex-direction: column; gap: 2px; }
.feed-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-soft);
  cursor: pointer;
  transition: background 0.1s;
}
.feed-item:hover { background: var(--panel-hover); }
.feed-icon { font-size: 13px; flex-shrink: 0; margin-top: 1px; width: 16px; text-align: center; }
.feed-text { flex: 1; min-width: 0; }
.feed-text span { color: var(--text-muted); }
.feed-time { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }
.guided-action-result { padding: 0 14px 12px; }

/* ===== PIPELINE SECTION ===== */
.pipeline-stages { padding: 8px 10px 10px; display: flex; flex-direction: column; gap: 0; }
#pipeline-spine .pipeline-stages {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  padding: 8px 10px 10px;
}
.pipeline-primary-action {
  grid-column: 1 / -1;
  min-width: 0;
}
.pipeline-primary-action .btn {
  min-height: 30px;
  padding: 5px 10px;
  width: 100%;
}
.pipeline-step { display: flex; gap: 12px; position: relative; }
#pipeline-spine .pipeline-step {
  align-items: center;
  background: var(--bg-2);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  gap: 6px;
  min-height: 0;
  padding: 6px 7px;
}
.pipeline-step:not(:last-child) { padding-bottom: 0; }
#pipeline-spine .pipeline-step:not(:last-child) { padding-bottom: 6px; }
.step-number {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 24px;
}
.step-number span {
  width: 24px; height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
  z-index: 1;
}
.pipeline-step.active .step-number span { background: var(--accent); color: #fff; }
.pipeline-step.locked .step-number span { background: var(--bg-3); color: var(--text-muted); border: 1px solid var(--border); }
.step-connector { color: var(--border); flex-shrink: 0; }
#pipeline-spine .step-connector { display: none; }
.step-content { flex: 1; min-width: 0; }
.step-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 6px;
}
.step-row strong { font-size: 12px; font-weight: 650; color: var(--text); line-height: 1.25; }
.step-status {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 999px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.step-status.active { background: var(--accent-soft); color: var(--accent); }
.step-status.pending { background: var(--bg-3); color: var(--text-muted); }
.step-desc { margin: 2px 0 0; font-size: 11px; color: var(--text-soft); }
#pipeline-spine .step-desc {
  color: var(--text-soft);
  display: none;
  font-size: 10px;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
  line-height: 1.25;
  margin: 2px 0 0;
  overflow: hidden;
}
#pipeline-spine .step-source { display: none !important; }
.step-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}
#pipeline-spine .step-action {
  align-items: stretch;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: flex-start;
  margin: 4px 0 0;
}
#pipeline-spine .step-action .btn {
  flex: 1 1 96px;
  font-size: 10px;
  min-height: 22px;
  padding: 2px 5px;
  white-space: normal;
}
.step-time { font-size: 10px; color: var(--text-muted); }
.definition-editor {
  border-top: 1px solid var(--border-light);
  padding: 8px 10px 10px;
}
#pipeline-spine .definition-editor { padding: 8px 10px 10px; }
.definition-editor label {
  display: block;
  color: var(--text-muted);
  font-size: 10px;
  letter-spacing: 0.4px;
  margin-bottom: 6px;
  text-transform: uppercase;
}
.definition-editor textarea {
  width: 100%;
  min-height: 84px;
  resize: vertical;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
  color: var(--text);
  font: inherit;
  font-size: 12px;
  line-height: 1.45;
  outline: none;
  padding: 8px 10px;
}
#pipeline-spine .definition-editor textarea { height: 54px; min-height: 54px; max-height: 120px; }
.definition-editor textarea:focus { border-color: var(--accent); }

/* ===== SYSTEM HEALTH POPOVER ===== */
.health-bars { display: flex; flex-direction: column; gap: 7px; }
.health-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.health-row .label { width: 104px; font-size: 11px; color: var(--text-soft); flex-shrink: 0; }
.bar-track { flex: 1; height: 6px; background: var(--bg); border-radius: 3px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 3px; transition: width 0.4s ease; }
.bar-fill.good { background: var(--accent); }
.bar-fill.warn { background: var(--orange); }
.bar-fill.bad { background: var(--red); }
.local-model-row {
  align-items: flex-start;
  border-top: 1px solid var(--border-light);
  margin-top: 4px;
  padding-top: 7px;
}
.health-local-models {
  color: var(--text-muted);
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  font-size: 11px;
  gap: 5px 9px;
  line-height: 1.35;
  min-width: 0;
}
.health-local-models strong { color: var(--text); font-size: 11px; font-weight: 600; }
.health-local-models em {
  color: var(--text-soft);
  flex-basis: 100%;
  font-style: normal;
  overflow-wrap: anywhere;
}
.health-meta {
  padding: 8px 0 0;
  border-top: 1px solid var(--border-light);
  display: flex;
  gap: 16px;
  margin-top: 8px;
}
.health-meta div { display: flex; align-items: center; gap: 6px; }
.health-meta .label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.3px; }
.health-meta output { font-size: 11px; color: var(--text); }

/* ===== TASK CONTROL ===== */
.product-review-section {
  max-width: 1120px;
  margin: 2px auto 14px;
  padding: 0 12px;
}
.product-review-header {
  background: var(--panel);
  border: 1px solid var(--border);
  border-bottom: 0;
  border-radius: var(--radius) var(--radius) 0 0;
  padding: 12px 14px;
}
.task-control-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 12px;
  border-top: 1px solid var(--border);
  border-radius: 0 0 var(--radius) var(--radius);
  background: var(--bg-2);
}
.product-review-section.is-empty {
  margin-bottom: 8px;
}
.product-review-section.is-empty .product-review-header {
  align-items: center;
  display: flex;
  padding: 9px 12px;
}
.product-review-section.is-empty .product-review-header .panel-subtitle {
  display: none;
}
.product-review-section.is-empty .task-control-grid {
  gap: 8px;
  padding: 8px;
}
.product-review-section.is-empty .dock-panel {
  background: transparent;
}
.product-review-section.is-empty .dock-panel-header {
  border-bottom: 0;
  min-height: 34px;
  padding: 8px 10px;
}
.product-review-section.is-empty .dock-panel-header h3 {
  font-size: 12px;
}
.product-review-section.is-empty .worker-lanes-list,
.product-review-section.is-empty .review-queue-list,
.product-review-section.is-empty .evidence-stream-list {
  display: none;
}
.dock-panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.dock-panel-header {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-light);
}
.dock-panel-header h3 {
  color: var(--text);
  flex-shrink: 0;
  font-size: 14px;
  font-weight: 650;
  line-height: 1.3;
  margin: 0;
}
.dock-count { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
.dock-status-note {
  margin-left: auto;
  color: var(--text-muted);
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.35px;
  text-transform: uppercase;
}

/* Worker lanes */
.worker-lanes-list { max-height: 260px; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 7px; }
.worker-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 12px;
  padding: 10px 11px;
  border: 1px solid transparent;
  border-left: 3px solid transparent;
  border-radius: 6px;
  background: linear-gradient(90deg, var(--task-card-tint, transparent), transparent 68%);
  transition: background 0.1s, border-color 0.1s;
}
.worker-card:hover { background: var(--panel-hover); border-color: var(--border-light); }
.worker-card.selected {
  background: var(--accent-bg);
  border-color: rgba(63,185,80,0.35);
}
.worker-card-main {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
  width: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  padding: 0;
  text-align: left;
}
.worker-light {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 5px;
}
.worker-light.green { background: var(--accent); }
.worker-light.yellow { background: var(--orange); }
.worker-light.gray { background: var(--text-muted); }
.worker-light.good { background: var(--accent); }
.worker-light.warn { background: var(--orange); }
.worker-light.bad { background: var(--red); }
.worker-light.neutral { background: var(--text-muted); }
.worker-copy { min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.worker-copy strong {
  font-size: 13px;
  line-height: 1.35;
  color: var(--text);
  font-weight: 600;
  overflow: hidden;
  overflow-wrap: anywhere;
  text-overflow: ellipsis;
  white-space: normal;
}
.worker-copy .task-id { color: var(--blue); font-weight: 700; }
.worker-meta {
  align-items: center;
  color: var(--text-muted);
  display: flex;
  font-size: 10px;
  gap: 6px;
  min-width: 0;
  overflow: hidden;
  flex-wrap: wrap;
}
.worker-meta .task-status-badge { flex-shrink: 0; font-size: 9px; min-height: 16px; padding: 1px 6px; }
.worker-meta-text { min-width: 0; overflow: hidden; overflow-wrap: anywhere; text-overflow: ellipsis; white-space: normal; }
.worker-event { font-size: 10px; color: var(--text-muted); overflow: hidden; overflow-wrap: anywhere; text-overflow: ellipsis; white-space: normal; }
.worker-event { color: var(--text-soft); }
.worker-next {
  background: rgba(110, 118, 129, 0.08);
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-soft);
  font-size: 10px;
  justify-self: start;
  padding: 2px 7px;
  white-space: normal;
}
.worker-branch { font-size: 10px; color: var(--text-soft); flex-shrink: 0; margin-left: 0; overflow-wrap: anywhere; }
.worker-time { font-size: 10px; color: var(--text-muted); flex-shrink: 0; width: auto; text-align: left; }
.worker-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; justify-content: flex-start; }
.task-row-btn { white-space: normal; }

/* Review queue */
.review-queue-list { max-height: 260px; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 7px; }
.review-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  align-items: flex-start;
  gap: 8px;
  padding: 10px 11px;
  border: 1px solid transparent;
  border-left: 3px solid transparent;
  border-radius: 6px;
  background: linear-gradient(90deg, var(--task-card-tint, transparent), transparent 68%);
  transition: background 0.1s;
  font-size: 12px;
}
.review-card:hover { background: var(--panel-hover); }
.review-priority {
  font-size: 10px;
  justify-self: start;
  padding: 1px 7px;
  border-radius: 999px;
  font-weight: 600;
  flex-shrink: 0;
}
.review-priority.high { background: var(--red-soft); color: var(--red); }
.review-priority.med { background: var(--orange-soft); color: var(--orange); }
.review-priority.low { background: rgba(110,118,129,0.12); color: var(--text-muted); }
.review-main {
  min-width: 0;
  background: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
  padding: 0;
  text-align: left;
}
.review-main strong,
.review-main span,
.review-main em {
  display: block;
  overflow: hidden;
  overflow-wrap: anywhere;
  text-overflow: ellipsis;
  white-space: normal;
}
.review-main strong { color: var(--text); font-size: 13px; line-height: 1.35; }
.review-main strong .task-status-badge {
  display: inline-flex;
  font-size: 9px;
  margin-left: 6px;
  vertical-align: 1px;
}
.review-main span { color: var(--text-muted); font-size: 10px; }
.review-main em { color: var(--text-soft); font-size: 10px; font-style: normal; margin-top: 1px; }
.review-card .task-row-btn { justify-self: start; }
.review-branch { font-size: 11px; color: var(--text-soft); flex: 1; min-width: 0; overflow: hidden; overflow-wrap: anywhere; text-overflow: ellipsis; white-space: normal; }
.review-files { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }
.review-worker { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }
.review-time { font-size: 10px; color: var(--text-muted); flex-shrink: 0; width: 40px; text-align: right; }

/* Evidence stream */
.evidence-stream-list { max-height: 260px; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 7px; }
.evidence-item {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 8px;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-left: 3px solid transparent;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--task-card-tint, transparent), transparent 68%);
  font-size: 11px;
  color: var(--text-soft);
  cursor: pointer;
  transition: background 0.1s;
}
.evidence-item:hover { background: var(--panel-hover); }
.evidence-main {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
  flex: 1;
  background: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
  padding: 0;
  text-align: left;
}
.evidence-icon {
  color: var(--task-accent);
  font-size: 13px;
  flex-shrink: 0;
  font-weight: 800;
  width: 16px;
  text-align: center;
}
.evidence-copy { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.evidence-text,
.evidence-path { overflow: hidden; overflow-wrap: anywhere; text-overflow: ellipsis; white-space: normal; }
.evidence-text strong { color: var(--blue); }
.evidence-text .task-status-badge {
  display: inline-flex;
  font-size: 9px;
  margin: 0 5px 0 4px;
  min-height: 15px;
  padding: 1px 5px;
}
.evidence-path { font-size: 10px; color: var(--text-muted); }
.evidence-time { font-size: 10px; color: var(--text-muted); flex-shrink: 0; margin-left: 24px; }
.empty-panel-note {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px;
  color: var(--text-muted);
  font-size: 12px;
}
.empty-panel-note code {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  padding: 5px 7px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== FOOTER ===== */
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

/* ===== STATUS BADGE ===== */
.status-badge {
  font-size: 10px;
  padding: 2px 10px;
  border-radius: 999px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.status-badge.online { background: var(--accent-soft); color: var(--accent); }
.info-icon { font-size: 14px; color: var(--text-muted); cursor: help; }

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* ===== RESPONSIVE ===== */
@media (max-width: 1400px) {
  .right-column { width: 300px; }
}
@media (min-width: 1201px) {
  .layout-columns {
    overflow-y: visible;
  }
  .task-control-grid {
    gap: 10px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    padding: 12px;
  }
  .dock-panel-header {
    min-height: 42px;
    padding: 10px 12px;
  }
  .worker-lanes-list,
  .review-queue-list,
  .evidence-stream-list {
    max-height: 260px;
    padding: 8px;
  }
}
@media (max-width: 1200px) {
  .task-control-grid { grid-template-columns: 1fr 1fr; }
  .right-column { width: 300px; }
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
  .brainstorm-transcript { min-height: 260px; max-height: 420px; padding: 10px 12px; }
  .right-column .brainstorm-section { height: auto; max-height: none; min-height: 0; }
  .right-column .brainstorm-transcript { min-height: 260px; max-height: 420px; }
  .brainstorm-chat-form { padding: 8px 12px; }
  .brainstorm-chat-form textarea { min-height: 38px; padding: 8px 10px; }
  .idea-capture-form { padding: 10px 12px 12px; }
  .idea-capture-form textarea { min-height: 64px; }
  .idea-capture-form input,
  .idea-capture-form .btn { flex: 1 1 100%; }
  .idea-primary-action:not(:empty) { margin: 0 12px 10px; }
  .idea-greenhouse-lanes { grid-template-columns: 1fr; }
  .pipeline-stages { padding: 8px 12px; }
  .pipeline-step { gap: 8px; }
  .pipeline-step:not(:last-child) { padding-bottom: 4px; }
  .step-number { min-width: 24px; }
  .step-number span { width: 24px; height: 24px; font-size: 11px; }
  .step-connector { height: 16px; }
  .step-desc { display: none; }
  .step-action { margin-top: 4px; }
  .definition-editor { padding: 8px 12px 10px; }
  .definition-editor textarea { min-height: 38px; }
  .layout-columns { flex-direction: column; padding: 12px 12px 0; }
  .center-column,
  .right-column {
    display: contents;
    max-height: none;
    padding: 0;
    position: static;
  }
  #idea-greenhouse-section { order: 1; }
  .history-panel { order: 2; }
  #brainstorm-section { order: 3; }
  #pipeline-spine { order: 4; }
  #orchestrator-section { order: 5; }
  #pipeline-spine .pipeline-stages { grid-template-columns: 1fr; }
  #product-review-section { order: 6; }
  #mission-feed-section { order: 7; }
  #builder-judge-section { order: 8; }
  .next-task-meta,
  .nt-meta-secondary { align-items: flex-start; flex-direction: column; }
  .nt-evidence-list { grid-template-columns: 1fr; }
  .nt-reconcile-action { align-items: flex-start; grid-template-columns: 1fr; padding-right: 0; }
  .nt-reconcile-action .btn { justify-self: start; }
}

/* ===== BUILDER-JUDGE LOOP ===== */
.builder-judge-section { margin-top: 8px; }
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
.bj-form-row { display: flex; gap: 10px; align-items: flex-end; }
.bj-form-row .bj-form-group { flex: 1; }
.bj-checkbox-group { justify-content: center; }
.bj-checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-soft); cursor: pointer; text-transform: none !important; letter-spacing: 0 !important; font-weight: 400 !important; }
.bj-required { color: var(--red); }
.bj-optional { color: var(--text-muted); font-weight: 400; text-transform: none; }

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
"""
