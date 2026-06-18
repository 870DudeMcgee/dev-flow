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
  --sidebar-w: 220px;
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
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px 12px;
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
.brand-text strong { display: block; font-size: 14px; color: var(--text); }
.brand-text span { font-size: 11px; color: var(--text-soft); }

.nav-list { padding: 8px 8px 0; display: flex; flex-direction: column; gap: 2px; }
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  text-decoration: none;
  font-size: 14px;
  transition: background 0.12s, color 0.12s;
  cursor: pointer;
}
.nav-item:hover { background: var(--bg-3); color: var(--text); }
.nav-item.active { background: var(--accent-bg); color: var(--accent); font-weight: 500; }
.nav-item.small { font-size: 13px; padding: 6px 12px; }
.nav-icon { flex-shrink: 0; opacity: 0.8; }
.nav-item.active .nav-icon { opacity: 1; }

.sidebar-spacer { flex: 1; }

.sidebar-status-card {
  margin: 4px 8px 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-3);
  display: flex;
  align-items: center;
  gap: 10px;
}
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

.control-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-soft);
}
.control-status .chevron { color: var(--text-muted); }

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
  gap: 0;
  padding: 0;
}
.center-column {
  flex: 1;
  min-width: 0;
  padding: 16px 16px 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}
.right-column {
  width: 340px;
  flex-shrink: 0;
  padding: 16px 16px 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.history-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.history-list {
  overflow-y: auto;
  flex: 1;
  padding: 4px 0;
  max-height: 400px;
}
.history-list .session-item {
  padding: 8px 10px;
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}
.history-list .session-item .si-meta {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 3px;
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
  margin-bottom: 12px;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-light);
  min-height: 40px;
}
.panel-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  letter-spacing: -0.01em;
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
.brainstorm-transcript {
  min-height: 220px;
  max-height: 420px;
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
  padding: 10px 14px;
}
.brainstorm-chat-form textarea {
  width: 100%;
  min-height: 44px;
  max-height: 140px;
  padding: 10px 12px;
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
  margin-top: 8px;
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

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.12s, opacity 0.12s;
  padding: 6px 14px;
}
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: var(--accent); color: #fff; font-weight: 500; }
.btn-primary:hover:not(:disabled) { background: #2ea043; }
.btn-secondary { background: var(--bg-3); color: var(--text-soft); border: 1px solid var(--border); }
.btn-secondary:hover:not(:disabled) { background: var(--panel-hover); color: var(--text); }
.btn-sm { font-size: 11px; padding: 4px 10px; }
.icon-btn {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  padding: 4px 8px;
}
.icon-btn:hover { background: var(--panel-hover); color: var(--text); }

/* ===== NEXT TASK LAUNCHPAD ===== */
.orchestrator-content { padding: 12px 14px; display: flex; flex-direction: column; gap: 12px; }
.orchestrator-directive .label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.orchestrator-directive h3 { margin: 4px 0 2px; font-size: 15px; font-weight: 600; color: var(--text); }
.orchestrator-directive p { margin: 0 0 8px; font-size: 13px; color: var(--text-soft); }
.next-task-summary h3 { overflow-wrap: anywhere; }
.next-task-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.next-task-meta div,
.next-task-definition,
.next-task-evidence {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
}
.next-task-meta span,
.next-task-definition .label,
.next-task-evidence .label {
  display: block;
  color: var(--text-muted);
  font-size: 10px;
  letter-spacing: 0.4px;
  margin-bottom: 2px;
  text-transform: uppercase;
}
.next-task-meta strong {
  display: block;
  color: var(--text);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.next-task-definition p {
  margin: 0;
  color: var(--text-soft);
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
}
.next-action { display: flex; flex-direction: column; gap: 2px; }
.next-action code {
  padding: 6px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
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
.next-task-evidence-head {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}
.next-task-evidence code,
.next-task-evidence-paths code {
  display: block;
  background: #070a0f;
  border: 1px solid var(--border);
  border-radius: 5px;
  color: var(--text-soft);
  font-size: 11px;
  overflow: hidden;
  padding: 5px 7px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.next-task-evidence pre {
  background: #070a0f;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font-size: 11px;
  margin: 8px 0 0;
  max-height: 120px;
  overflow: auto;
  padding: 8px;
  white-space: pre-wrap;
}
.next-task-evidence-paths { display: flex; flex-direction: column; gap: 5px; margin-top: 7px; }
.next-task-evidence-empty { color: var(--text-muted); font-size: 12px; }
.task-switcher-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-light);
  background: var(--bg);
  color: var(--text-soft);
  cursor: pointer;
  font: inherit;
  text-align: left;
}
.task-switcher-row:hover,
.task-switcher-row.selected {
  background: var(--panel-hover);
  border-color: var(--border);
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

/* ===== PIPELINE SECTION (right column) ===== */
.pipeline-stages { padding: 10px 14px 14px; display: flex; flex-direction: column; gap: 0; }
.pipeline-step { display: flex; gap: 12px; position: relative; }
.pipeline-step:not(:last-child) { padding-bottom: 8px; }
.step-number {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 28px;
}
.step-number span {
  width: 28px; height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
  z-index: 1;
}
.pipeline-step.active .step-number span { background: var(--accent); color: #fff; }
.pipeline-step.locked .step-number span { background: var(--bg-3); color: var(--text-muted); border: 1px solid var(--border); }
.step-connector { color: var(--border); flex-shrink: 0; }
.step-content { flex: 1; min-width: 0; }
.step-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.step-row strong { font-size: 13px; font-weight: 600; color: var(--text); }
.step-status {
  font-size: 10px;
  padding: 1px 8px;
  border-radius: 999px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.step-status.active { background: var(--accent-soft); color: var(--accent); }
.step-status.pending { background: var(--bg-3); color: var(--text-muted); }
.step-desc { margin: 2px 0 0; font-size: 11px; color: var(--text-soft); }
.step-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}
.step-time { font-size: 10px; color: var(--text-muted); }
.definition-editor {
  border-top: 1px solid var(--border-light);
  padding: 10px 14px 14px;
}
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
.definition-editor textarea:focus { border-color: var(--accent); }

/* ===== SYSTEM HEALTH ===== */
.health-section { margin-bottom: 0; }
.health-bars { padding: 10px 14px; display: flex; flex-direction: column; gap: 8px; }
.health-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.health-row .label { width: 80px; font-size: 11px; color: var(--text-soft); flex-shrink: 0; }
.bar-track { flex: 1; height: 6px; background: var(--bg); border-radius: 3px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 3px; transition: width 0.4s ease; }
.bar-fill.good { background: var(--accent); }
.bar-fill.warn { background: var(--orange); }
.bar-fill.bad { background: var(--red); }
.health-meta {
  padding: 8px 14px 10px;
  border-top: 1px solid var(--border-light);
  display: flex;
  gap: 16px;
}
.health-meta div { display: flex; align-items: center; gap: 6px; }
.health-meta .label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.3px; }
.health-meta output { font-size: 11px; color: var(--text); }

/* ===== BOTTOM DOCK ===== */
.bottom-dock {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  padding: 12px 16px 8px;
  border-top: 1px solid var(--border);
  background: var(--bg-2);
}
.dock-panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.dock-panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-light);
}
.dock-panel-header h3 { margin: 0; font-size: 12px; font-weight: 600; color: var(--text); flex-shrink: 0; }
.dock-count { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
.dock-view-all {
  margin-left: auto;
  font-size: 11px;
  color: var(--blue);
  text-decoration: none;
  flex-shrink: 0;
}
.dock-view-all:hover { text-decoration: underline; }

/* Worker lanes */
.worker-lanes-list { max-height: 240px; overflow-y: auto; padding: 6px 8px; display: flex; flex-direction: column; gap: 6px; }
.worker-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto 54px auto;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 6px;
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
  font-size: 12px;
  color: var(--text);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.worker-copy .task-id { color: var(--blue); font-weight: 700; }
.worker-meta, .worker-event { font-size: 10px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.worker-event { color: var(--text-soft); }
.worker-next { font-size: 10px; color: var(--text-soft); border: 1px solid var(--border); border-radius: 999px; padding: 2px 7px; white-space: nowrap; }
.worker-branch { font-size: 10px; color: var(--text-soft); flex-shrink: 0; margin-left: auto; }
.worker-time { font-size: 10px; color: var(--text-muted); flex-shrink: 0; width: 54px; text-align: right; }
.worker-actions { display: flex; align-items: center; gap: 5px; justify-content: flex-end; }
.task-row-btn { white-space: nowrap; }

/* Review queue */
.review-queue-list { max-height: 240px; overflow-y: auto; padding: 6px 8px; display: flex; flex-direction: column; gap: 5px; }
.review-card {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  transition: background 0.1s;
  font-size: 12px;
}
.review-card:hover { background: var(--panel-hover); }
.review-priority {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 999px;
  font-weight: 600;
  flex-shrink: 0;
}
.review-priority.high { background: var(--red-soft); color: var(--red); }
.review-priority.med { background: var(--orange-soft); color: var(--orange); }
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
.review-main span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.review-main strong { color: var(--text); font-size: 12px; }
.review-main span { color: var(--text-muted); font-size: 10px; }
.review-branch { font-size: 11px; color: var(--text-soft); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.review-files { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }
.review-worker { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }
.review-time { font-size: 10px; color: var(--text-muted); flex-shrink: 0; width: 40px; text-align: right; }

/* Evidence stream */
.evidence-stream-list { max-height: 240px; overflow-y: auto; padding: 6px 8px; display: flex; flex-direction: column; gap: 3px; }
.evidence-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-soft);
  cursor: pointer;
  transition: background 0.1s;
}
.evidence-item:hover { background: var(--panel-hover); }
.evidence-main {
  display: flex;
  align-items: center;
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
.evidence-icon { font-size: 13px; flex-shrink: 0; width: 16px; text-align: center; }
.evidence-text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.evidence-text strong { color: var(--blue); }
.evidence-time { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }
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
.focus-grid span,
.task-command-box label {
  display: block;
  color: var(--text-muted);
  font-size: 10px;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  margin-bottom: 3px;
}
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
.command-result.pending { border-color: var(--border); background: var(--bg); }
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
  .right-column { width: 280px; }
}
@media (max-width: 1200px) {
  .bottom-dock { grid-template-columns: 1fr 1fr; }
  .right-column { display: none; }
  .next-task-meta { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .bottom-dock { grid-template-columns: 1fr; }
  .sidebar { display: none; }
  .topbar { padding: 8px 12px; gap: 8px; }
  .topbar-left { flex-wrap: wrap; }
  .panel { margin-bottom: 10px; }
  .panel-header { min-height: 36px; padding: 8px 12px; }
  .brainstorm-transcript { min-height: 130px; max-height: 180px; padding: 10px 12px; }
  .brainstorm-chat-form { padding: 8px 12px; }
  .brainstorm-chat-form textarea { min-height: 38px; padding: 8px 10px; }
  .pipeline-stages { padding: 8px 12px; }
  .pipeline-step { gap: 8px; }
  .pipeline-step:not(:last-child) { padding-bottom: 4px; }
  .step-number { min-width: 24px; }
  .step-number span { width: 24px; height: 24px; font-size: 11px; }
  .step-connector { height: 16px; }
  .step-desc { display: none; }
  .step-action { margin-top: 4px; }
  .definition-editor { padding: 8px 12px 10px; }
  .definition-editor textarea { min-height: 48px; }
  .layout-columns { flex-direction: column; padding: 12px 12px 0; }
  .center-column,
  .right-column {
    display: contents;
    padding: 0;
  }
  #brainstorm-section { order: 1; }
  .pipeline-section { order: 2; }
  #orchestrator-section { order: 3; }
  .health-section { order: 4; }
  .history-panel { order: 5; }
  #mission-feed-section { order: 6; }
  .next-task-meta { grid-template-columns: 1fr; }
}
"""
