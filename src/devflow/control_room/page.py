"""Embedded HTML page for the DevFlow pipeline status board.

Read-only dashboard. The single ACTIVE run renders as a large front-and-center
card; completed/old runs collapse into a compact history list. Auto-refreshes
every 3 seconds. No inputs — all orchestration happens in Hermes.
"""

STATUS_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DevFlow — Pipeline Status</title>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d28;
    --surface-2: #232636;
    --border: #2e3242;
    --text: #e4e6eb;
    --text-dim: #9ca3af;
    --accent: #6366f1;
    --accent-glow: rgba(99,102,241,0.18);
    --error: #ef4444;
    --success: #10b981;
    --warning: #f59e0b;
    --radius: 12px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { height: 100%; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* ── Header ── */
  .header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 14px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 10;
  }
  .header h1 {
    font-size: 18px;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .header h1 .icon {
    width: 28px; height: 28px;
    background: var(--accent);
    border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px;
  }
  .header-right { display: flex; align-items: center; gap: 16px; }
  .git-widget {
    display: grid;
    grid-template-columns: 28px minmax(120px, 1fr) auto;
    align-items: center;
    gap: 9px;
    min-width: 286px;
    max-width: 380px;
    padding: 7px 10px;
    border: 1px solid rgba(99,102,241,0.28);
    border-radius: 999px;
    background: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(15,17,23,0.86));
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04), 0 0 18px rgba(99,102,241,0.08);
  }
  .git-widget.dirty { border-color: rgba(245,158,11,0.42); background: linear-gradient(135deg, rgba(245,158,11,0.14), rgba(15,17,23,0.86)); }
  .git-widget.unpushed, .git-widget.behind, .git-widget.local { border-color: rgba(14,165,233,0.38); background: linear-gradient(135deg, rgba(14,165,233,0.12), rgba(15,17,23,0.86)); }
  .git-icon { width: 24px; height: 24px; border-radius: 8px; display: flex; align-items: center; justify-content: center; background: rgba(99,102,241,0.20); color: #c4b5fd; font-size: 13px; }
  .git-widget.dirty .git-icon { background: rgba(245,158,11,0.18); color: var(--warning); }
  .git-widget.unpushed .git-icon, .git-widget.behind .git-icon, .git-widget.local .git-icon { background: rgba(14,165,233,0.16); color: #7dd3fc; }
  .git-copy { min-width: 0; }
  .git-repo { font-size: 10px; line-height: 1; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .git-branch { margin-top: 3px; font: 700 12px/1 'SF Mono','Fira Code',monospace; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .git-state { font-size: 10px; padding: 4px 8px; border-radius: 999px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; background: rgba(16,185,129,0.16); color: var(--success); border: 1px solid rgba(16,185,129,0.25); }
  .git-widget.dirty .git-state { background: rgba(245,158,11,0.16); color: var(--warning); border-color: rgba(245,158,11,0.28); }
  .git-widget.unpushed .git-state, .git-widget.behind .git-state, .git-widget.local .git-state { background: rgba(14,165,233,0.14); color: #7dd3fc; border-color: rgba(14,165,233,0.25); }
  .memory-widget {
    display: grid;
    grid-template-columns: 84px 78px;
    align-items: center;
    gap: 10px;
    min-width: 182px;
    padding: 7px 10px;
    border: 1px solid rgba(99,102,241,0.28);
    border-radius: 999px;
    background: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(15,17,23,0.86));
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04), 0 0 18px rgba(99,102,241,0.08);
  }
  .memory-widget.warn { border-color: rgba(245,158,11,0.42); background: linear-gradient(135deg, rgba(245,158,11,0.14), rgba(15,17,23,0.86)); }
  .memory-widget.critical { border-color: rgba(239,68,68,0.55); background: linear-gradient(135deg, rgba(239,68,68,0.14), rgba(15,17,23,0.88)); }
  .memory-copy { min-width: 0; }
  .memory-label { display: flex; align-items: center; gap: 5px; font-size: 10px; line-height: 1; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); font-weight: 800; }
  .memory-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--success); box-shadow: 0 0 8px rgba(16,185,129,0.55); }
  .memory-widget.warn .memory-dot { background: var(--warning); box-shadow: 0 0 8px rgba(245,158,11,0.58); }
  .memory-widget.critical .memory-dot { background: var(--error); box-shadow: 0 0 8px rgba(239,68,68,0.58); }
  .memory-value { margin-top: 3px; font: 700 12px/1 'SF Mono','Fira Code',monospace; color: var(--text); white-space: nowrap; }
  .memory-graph { width: 78px; height: 22px; overflow: visible; }
  .memory-graph .grid { stroke: rgba(156,163,175,0.18); stroke-width: 1; }
  .memory-graph .area { fill: rgba(16,185,129,0.14); }
  .memory-graph .line { fill: none; stroke: var(--success); stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; filter: drop-shadow(0 0 3px rgba(16,185,129,0.38)); }
  .memory-widget.warn .memory-graph .area { fill: rgba(245,158,11,0.15); }
  .memory-widget.warn .memory-graph .line { stroke: var(--warning); filter: drop-shadow(0 0 3px rgba(245,158,11,0.42)); }
  .memory-widget.critical .memory-graph .area { fill: rgba(239,68,68,0.16); }
  .memory-widget.critical .memory-graph .line { stroke: var(--error); filter: drop-shadow(0 0 3px rgba(239,68,68,0.42)); }
  .repo-path {
    display: none;
    font-size: 12px; color: var(--text-dim);
    font-family: 'SF Mono', 'Fira Code', monospace;
    max-width: 380px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .live-indicator { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--success); }
  .live-dot { width: 8px; height: 8px; background: var(--success); border-radius: 50%; animation: pulse 2s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

  /* ── Layout ── */
  .content { flex: 1; max-width: 1600px; width: 100%; margin: 0 auto; padding: 16px 24px; display: flex; flex-direction: column; min-height: 0; }
  .section-label {
    font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em;
    color: var(--text-dim); margin: 24px 0 12px; font-weight: 700;
  }

  /* ── ACTIVE: big front-and-center card ── */
  .active-card {
    background: var(--surface);
    border: 1px solid var(--accent);
    border-radius: var(--radius);
    box-shadow: 0 0 28px var(--accent-glow);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    flex: 0 0 calc(100vh - 130px);
    height: calc(100vh - 130px);
    min-height: 420px;
  }
  .active-top-bar {
    padding: 16px 24px;
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    border-bottom: 1px solid var(--border);
  }
  .active-top-bar-left { display: flex; flex-direction: column; gap: 4px; min-width: 0; flex: 1; }
  .active-progress-bar-section { padding: 0 24px 12px; border-bottom: 1px solid var(--border); }
  .active-columns { display: flex; flex: 1; min-height: 0; overflow: hidden; }
  .active-card.blocked { border-color: var(--error); box-shadow: 0 0 28px rgba(239,68,68,0.18); }

  /* ── Left sidebar (meta + progress) ── */
  .active-left { padding: 20px; border-right: 1px solid var(--border); overflow: hidden; width: 280px; flex-shrink: 0; display: flex; flex-direction: column; min-height: 0; }
  .active-right { padding: 20px; min-width: 0; overflow: hidden; display: flex; flex-direction: column; flex: 1; min-height: 0; }

  .active-top {
    padding: 20px 24px;
    display: flex; align-items: flex-start; justify-content: space-between; gap: 16px;
    border-bottom: 1px solid var(--border);
  }
  .active-meta { display: flex; flex-direction: column; gap: 6px; min-width: 0; flex: 1; }
  .active-run-id { font-family: 'SF Mono','Fira Code',monospace; font-size: 13px; color: var(--text-dim); }
  .active-intent { font-size: 20px; font-weight: 700; line-height: 1.3; }
  .active-repo { font-size: 12px; color: var(--text-dim); font-family: 'SF Mono','Fira Code',monospace; }

  .stage-badge {
    font-size: 13px; font-weight: 700; padding: 7px 16px; border-radius: 20px;
    white-space: nowrap; align-self: flex-start;
  }
  .stage-badge.idea, .stage-badge.definition { background: rgba(99,102,241,0.2); color: var(--accent); }
  .stage-badge.spec, .stage-badge.planning, .stage-badge.planning_judge { background: rgba(245,158,11,0.2); color: var(--warning); }
  .stage-badge.assignment, .stage-badge.build_judge { background: rgba(99,102,241,0.3); color: #a5b4fc; }
  .stage-badge.verification { background: rgba(16,185,129,0.2); color: var(--success); }
  .stage-badge.human_decision { background: rgba(245,158,11,0.3); color: var(--warning); }
  .stage-badge.complete { background: rgba(16,185,129,0.15); color: var(--success); }
  .stage-badge.blocked { background: rgba(239,68,68,0.2); color: var(--error); }

  .active-progress { padding: 16px 24px 4px; }
  .progress-bar { display: flex; gap: 5px; align-items: center; }
  .progress-segment { flex: 1; height: 14px; border-radius: 6px; background: var(--surface-2); transition: background 0.3s; }
  .progress-segment.done { background: var(--accent); }
  .progress-segment.current { background: var(--accent); animation: shimmer 1.5s infinite; }
  .progress-segment.blocked { background: var(--error); }
  @keyframes shimmer { 0%, 100% { opacity: 1; } 50% { opacity: 0.45; } }
  .stage-labels { display: flex; gap: 5px; margin-top: 6px; font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.03em; }
  .stage-labels span { flex: 1; text-align: center; white-space: nowrap; }
  .stage-labels span.current { color: var(--accent); font-weight: 700; }

  .active-body { padding: 4px 24px 8px; }
  .panel-title { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-dim); margin-bottom: 8px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
  .panel-title .count { background: var(--accent); color: #fff; border-radius: 10px; padding: 1px 8px; font-size: 11px; }

  /* ── Worker output timeline ── */
  .worker-feed-container { flex: 1; min-height: 0; display: flex; overflow: hidden; gap: 14px; }
  .worker-timeline {
    width: 280px; flex-shrink: 0; overflow-y: auto; padding-right: 4px;
    display: flex; flex-direction: column; gap: 8px;
  }
  .timeline-item {
    display: grid; grid-template-columns: 28px 1fr; gap: 8px;
    padding: 8px; border: 1px solid var(--border); border-radius: 8px;
    background: var(--surface-2); cursor: pointer; color: var(--text-dim);
    transition: all 0.15s;
  }
  .timeline-item:hover { border-color: var(--accent); color: var(--text); }
  .timeline-item.active { border-color: var(--accent); background: rgba(99,102,241,0.15); color: var(--text); }
  .timeline-step {
    width: 24px; height: 24px; border-radius: 999px; display: flex; align-items: center; justify-content: center;
    background: #0d0f16; border: 1px solid var(--border); font: 700 11px 'SF Mono','Fira Code',monospace; color: var(--text);
  }
  .timeline-item.started .timeline-step { border-color: var(--warning); color: var(--warning); animation: pulse 1.5s infinite; }
  .timeline-item.completed .timeline-step { border-color: var(--success); color: var(--success); }
  .timeline-item.loop_exhausted .timeline-step { border-color: var(--error); color: var(--error); }
  .timeline-role { font-size: 12px; font-weight: 800; color: var(--text); line-height: 1.2; }
  .timeline-meta { margin-top: 2px; font-size: 10px; color: var(--text-dim); font-family: 'SF Mono','Fira Code',monospace; }
  .timeline-event { margin-top: 3px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
  .worker-output-detail { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }
  .worker-output { background: #0d0f16; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; flex: 1; min-height: 0; display: flex; flex-direction: column; }
  .worker-output-header {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px; border-bottom: 1px solid var(--border);
    background: rgba(99,102,241,0.05);
  }
  .worker-output-avatar { width: 28px; height: 28px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; color: #fff; flex-shrink: 0; }
  .worker-output-avatar.builder { background: var(--accent); }
  .worker-output-avatar.judge { background: var(--warning); }
  .worker-output-avatar.planner { background: #0ea5e9; }
  .worker-output-avatar.planning_judge { background: #8b5cf6; }
  .worker-output-avatar.default { background: var(--text-dim); }
  .worker-output-title { flex: 1; }
  .worker-output-role { font-size: 14px; font-weight: 700; }
  .worker-output-model { font-size: 11px; color: var(--text-dim); }
  .worker-output-status { font-size: 10px; padding: 2px 8px; border-radius: 3px; font-weight: 700; text-transform: uppercase; }
  .worker-output-status.started { background: rgba(245,158,11,0.2); color: var(--warning); }
  .worker-output-status.completed { background: rgba(16,185,129,0.2); color: var(--success); }
  .worker-output-status.error { background: rgba(239,68,68,0.2); color: var(--error); }
  .worker-output-time { font-size: 11px; color: var(--text-dim); font-family: 'SF Mono','Fira Code',monospace; }
  .worker-output-prompt {
    padding: 8px 14px; border-bottom: 1px solid rgba(46,50,66,0.3);
    font-size: 11px; color: var(--text-dim); white-space: pre-wrap; word-break: break-word;
    background: rgba(0,0,0,0.2); flex-shrink: 0;
  }
  .worker-output-content {
    padding: 14px; font-size: 13px; line-height: 1.6; color: var(--text);
    white-space: pre-wrap; word-break: break-word;
    flex: 1; min-height: 0; overflow-y: auto;
  }
  .worker-output-usage { padding: 4px 14px 10px; font-size: 10px; color: var(--text-dim); flex-shrink: 0; }

  /* ── Artifact preview ── */
  .artifacts-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .artifact-chip { font-size: 11px; padding: 4px 9px; border-radius: 5px; background: var(--surface-2); color: var(--text-dim); border: 1px solid var(--border); cursor: pointer; }
  .artifact-chip:hover { border-color: var(--accent); color: var(--text); }
  .artifact-preview { margin-top: 10px; background: #0a0c12; border: 1px solid var(--border); border-radius: 6px; padding: 10px; font-family: 'SF Mono','Fira Code',monospace; font-size: 11px; color: var(--text-dim); white-space: pre-wrap; word-break: break-word; display: none; flex: 1; min-height: 0; max-height: none; overflow-y: auto; }
  .verification-panel { margin-top: 16px; flex-shrink: 0; }
  .receipt-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }
  .receipt-pass { color: var(--success); }
  .receipt-fail { color: var(--error); }

  /* ── HISTORY: compact rows ── */
  .history-row {
    display: flex; align-items: center; gap: 12px;
    padding: 9px 16px;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
  }
  .history-row:hover { background: var(--surface); }
  .hist-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); flex-shrink: 0; }
  .hist-dot.active { background: var(--accent); }
  .hist-intent { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
  .hist-stage { font-size: 11px; color: var(--text-dim); font-weight: 600; min-width: 90px; text-align: right; }
  .hist-time { font-size: 11px; color: var(--text-dim); font-family: 'SF Mono','Fira Code',monospace; min-width: 70px; text-align: right; }

  /* ── Empty / no-active ── */
  .no-active {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 32px; text-align: center; color: var(--text-dim);
  }
  .no-active h3 { font-size: 18px; color: var(--text); margin-bottom: 6px; }

  .empty-state { text-align: center; padding: 80px 20px; color: var(--text-dim); }
  .empty-state h3 { font-size: 22px; margin-bottom: 8px; color: var(--text); }
  .empty-state p { font-size: 15px; max-width: 400px; margin: 0 auto; line-height: 1.6; }

  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  @media (max-width: 900px) {
    .repo-path { display: none; }
    .git-widget { min-width: 210px; grid-template-columns: 24px minmax(92px, 1fr) auto; }
    .memory-widget { grid-template-columns: 72px 58px; min-width: 150px; }
    .memory-graph { width: 58px; }
  }
</style>
</head>
<body>

<div class="header">
  <h1>
    <span class="icon">⚡</span>
    DevFlow Pipeline
  </h1>
  <div class="header-right">
    <div class="git-widget" id="git-widget" title="Git status unavailable">
      <span class="git-icon">⑂</span>
      <span class="git-copy">
        <span class="git-repo" id="git-repo">repo</span>
        <span class="git-branch" id="git-branch">branch</span>
      </span>
      <span class="git-state" id="git-state">--</span>
    </div>
    <div class="memory-widget" id="memory-widget" title="Approximate macOS memory pressure">
      <div class="memory-copy">
        <div class="memory-label"><span class="memory-dot"></span>Memory</div>
        <div class="memory-value" id="memory-value">-- GiB free</div>
      </div>
      <svg class="memory-graph" id="memory-graph" viewBox="0 0 78 22" preserveAspectRatio="none" aria-hidden="true">
        <path class="grid" d="M0 11 H78"></path>
        <path class="area" id="memory-area" d="M0 22 L78 22 Z"></path>
        <path class="line" id="memory-line" d=""></path>
      </svg>
    </div>
    <span class="repo-path" id="repo-path"></span>
    <span class="live-indicator"><span class="live-dot"></span>LIVE</span>
  </div>
</div>

<div class="content" id="content">
  <div class="empty-state">
    <h3>Waiting for activity</h3>
    <p>No pipeline runs yet. Start a brainstorm in Hermes to kick off the DevFlow loop.</p>
  </div>
</div>

<script>
const STAGE_NAMES = ['idea','definition','spec','planning','planning_judge','assignment','build_judge','verification','human_decision','complete'];
const STAGE_SHORT = ['Idea','Def','Spec','Plan','Judge','Assign','Build','Verify','Decision','Done'];

// Preserve open artifact preview and selected tab across auto-refreshes
let OPEN_ARTIFACT = null;  // { runId, fileName }
let SELECTED_OUTPUT = null; // { runId, index }
let MEMORY_HISTORY = [];

async function refresh() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    const scrollState = captureScrollState();
    render(data);
    if (OPEN_ARTIFACT) {
      await showArtifact(OPEN_ARTIFACT.runId, OPEN_ARTIFACT.fileName, /*silent*/ true);
    }
    if (SELECTED_OUTPUT) {
      const item = document.querySelector(`.timeline-item[data-feed-index="${SELECTED_OUTPUT.index}"]`);
      if (item) selectWorkerOutput(item, SELECTED_OUTPUT.runId);
    }
    restoreScrollState(scrollState);
  } catch (e) { console.error('refresh failed:', e); }
}

async function refreshMemory() {
  try {
    const resp = await fetch('/api/memory');
    const data = await resp.json();
    renderMemory(data);
  } catch (e) { console.error('memory refresh failed:', e); }
}

async function refreshGit() {
  try {
    const resp = await fetch('/api/git');
    const data = await resp.json();
    renderGit(data);
  } catch (e) { console.error('git refresh failed:', e); }
}

function renderGit(data) {
  const widget = document.getElementById('git-widget');
  const repo = document.getElementById('git-repo');
  const branch = document.getElementById('git-branch');
  const state = document.getElementById('git-state');
  if (!widget || !repo || !branch || !state) return;
  widget.classList.remove('dirty', 'unpushed', 'behind', 'local');
  if (!data || data.available === false) {
    repo.textContent = 'Git';
    branch.textContent = 'not available';
    state.textContent = '--';
    widget.title = (data && data.reason) ? data.reason : 'Git status unavailable';
    return;
  }
  const gitState = data.state || 'clean';
  if (gitState !== 'clean') widget.classList.add(gitState);
  repo.textContent = data.repo_name || 'repo';
  branch.textContent = data.branch || 'branch';
  state.textContent = data.label || gitState;
  const details = [
    data.repo_path || '',
    `branch ${data.branch || 'unknown'} @ ${data.commit || 'unknown'}`,
    `${data.staged || 0} staged · ${data.unstaged || 0} unstaged · ${data.untracked || 0} untracked`,
    `${data.ahead || 0} ahead · ${data.behind || 0} behind`,
    data.upstream ? `upstream ${data.upstream}` : 'no upstream',
  ].filter(Boolean);
  widget.title = details.join('\n');
}

function renderMemory(data) {
  const widget = document.getElementById('memory-widget');
  const value = document.getElementById('memory-value');
  if (!widget || !value) return;
  widget.classList.remove('warn', 'critical');
  if (!data || data.available === false) {
    value.textContent = 'unavailable';
    widget.title = (data && data.reason) ? data.reason : 'Memory pressure unavailable';
    drawMemoryGraph([]);
    return;
  }
  const pressure = Math.max(0, Math.min(1, Number(data.pressure) || 0));
  MEMORY_HISTORY.push(pressure);
  MEMORY_HISTORY = MEMORY_HISTORY.slice(-36);
  if (data.status === 'warn') widget.classList.add('warn');
  if (data.status === 'critical') widget.classList.add('critical');
  value.textContent = `${Number(data.available_gib || 0).toFixed(1)} GiB free`;
  widget.title = `${data.label || 'Memory'} · ${Number(data.pressure_percent || pressure * 100).toFixed(1)}% pressure · ${Number(data.used_gib || 0).toFixed(1)} / ${Number(data.total_gib || 0).toFixed(1)} GiB used`;
  drawMemoryGraph(MEMORY_HISTORY);
}

function drawMemoryGraph(points) {
  const line = document.getElementById('memory-line');
  const area = document.getElementById('memory-area');
  if (!line || !area) return;
  if (!points.length) {
    line.setAttribute('d', '');
    area.setAttribute('d', 'M0 22 L78 22 Z');
    return;
  }
  const width = 78;
  const height = 22;
  const maxIdx = Math.max(points.length - 1, 1);
  const coords = points.map((p, idx) => {
    const x = (idx / maxIdx) * width;
    const y = height - (Math.max(0, Math.min(1, p)) * (height - 3)) - 1.5;
    return [x, y];
  });
  const d = coords.map(([x, y], idx) => `${idx ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  const areaD = `${d} L${width} ${height} L0 ${height} Z`;
  line.setAttribute('d', d);
  area.setAttribute('d', areaD);
}

function captureScrollState() {
  const timelineScroll = {};
  const workerDetailScroll = {};
  document.querySelectorAll('.worker-feed-container').forEach(container => {
    const timeline = container.querySelector('.worker-timeline');
    if (container.id && timeline) timelineScroll[container.id] = timeline.scrollTop;
    const visibleOutput = [...container.querySelectorAll('.worker-output')]
      .find(el => getComputedStyle(el).display !== 'none');
    const detailBody = visibleOutput?.querySelector('.worker-output-content');
    if (container.id && visibleOutput && detailBody) {
      workerDetailScroll[`${container.id}:${visibleOutput.dataset.feedIndex || ''}`] = detailBody.scrollTop;
    }
  });
  return {
    pageX: window.scrollX,
    pageY: window.scrollY,
    artifact: OPEN_ARTIFACT ? {
      runId: OPEN_ARTIFACT.runId,
      scrollTop: document.getElementById('preview-' + OPEN_ARTIFACT.runId)?.scrollTop || 0,
    } : null,
    timelineScroll,
    workerDetailScroll,
  };
}

function restoreScrollState(state) {
  if (!state) return;
  const apply = () => {
    if (state.artifact) {
      const preview = document.getElementById('preview-' + state.artifact.runId);
      if (preview) preview.scrollTop = state.artifact.scrollTop;
    }
    Object.entries(state.timelineScroll || {}).forEach(([containerId, scrollTop]) => {
      const timeline = document.getElementById(containerId)?.querySelector('.worker-timeline');
      if (timeline) timeline.scrollTop = scrollTop;
    });
    Object.entries(state.workerDetailScroll || {}).forEach(([key, scrollTop]) => {
      const [containerId, feedIndex] = key.split(':');
      const detailBody = document.getElementById(containerId)
        ?.querySelector(`.worker-output[data-feed-index="${feedIndex}"] .worker-output-content`);
      if (detailBody) detailBody.scrollTop = scrollTop;
    });
    window.scrollTo(state.pageX || 0, state.pageY || 0);
  };
  requestAnimationFrame(() => {
    apply();
    setTimeout(apply, 0);
  });
}

function render(data) {
  const repoPath = document.getElementById('repo-path');
  if (repoPath) repoPath.textContent = data.repo || '';
  const el = document.getElementById('content');
  const runs = data.runs || [];
  if (runs.length === 0) {
    el.innerHTML = `<div class="empty-state"><h3>Waiting for activity</h3><p>No pipeline runs yet. Start a brainstorm in Hermes to kick off the DevFlow loop.</p></div>`;
    return;
  }

  const active = runs.filter(r => r.stage !== 'complete' && r.stage !== 'blocked');
  const history = runs.filter(r => !active.includes(r));

  let html = '';
  if (active.length) {
    const label = active.length > 1 ? `Active Pipelines (${active.length})` : 'Active Pipeline';
    html += `<div class="section-label">${label}</div>`;
    html += active.map(r => renderActive(r)).join('');
  } else {
    html += `<div class="no-active"><h3>No active pipeline</h3><p>All runs are complete. Start a new brainstorm in Hermes to begin.</p></div>`;
  }
  if (history.length) {
    html += `<div class="section-label">History (${history.length})</div>`;
    html += `<div class="history-list">${history.map(r => renderHistoryRow(r)).join('')}</div>`;
  }
  el.innerHTML = html;

  // After render, show exactly one detail panel while the left rail keeps chronological order visible.
  el.querySelectorAll('.worker-feed-container').forEach(container => {
    const activeItem = container.querySelector('.timeline-item.active');
    const activeIndex = activeItem ? activeItem.dataset.feedIndex : null;
    container.querySelectorAll('.worker-output').forEach(outEl => {
      outEl.style.display = outEl.dataset.feedIndex === activeIndex ? '' : 'none';
    });
  });
}

function renderActive(r) {
  const stageIdx = STAGE_NAMES.indexOf(r.stage);
  const segments = STAGE_NAMES.map((s, i) => {
    let cls = '';
    if (r.stage === 'blocked') cls = i <= stageIdx ? 'blocked' : '';
    else if (i < stageIdx) cls = 'done';
    else if (i === stageIdx) cls = 'current';
    return `<div class="progress-segment ${cls}"></div>`;
  }).join('');
  const labels = STAGE_SHORT.map((s, i) =>
    `<span class="${i === stageIdx ? 'current' : ''}">${s}</span>`
  ).join('');

  // Build worker feed as a chronological timeline. Oldest → newest matches the actual loop order.
  const feedEntries = (r.worker_feed || []).slice().sort((a, b) => String(a.timestamp || '').localeCompare(String(b.timestamp || '')));
  const activeFeedIndex = SELECTED_OUTPUT && SELECTED_OUTPUT.runId === r.run_id
    ? String(SELECTED_OUTPUT.index)
    : String(Math.max(feedEntries.length - 1, 0));
  const timelineHtml = feedEntries.length ? `<div class="worker-timeline" aria-label="Worker output timeline">
    ${feedEntries.map((f, idx) => {
      const role = f.role || 'worker';
      const status = f.event || 'unknown';
      const active = String(idx) === activeFeedIndex ? 'active' : '';
      const model = f.model ? ` · ${f.model}` : '';
      return `<div class="timeline-item ${escapeHtml(status)} ${active}" data-feed-index="${idx}" onclick="selectWorkerOutput(this,'${escapeHtml(r.run_id)}')">
        <span class="timeline-step">${idx + 1}</span>
        <span>
          <div class="timeline-role">${escapeHtml(role)}</div>
          <div class="timeline-meta">${formatTime(f.timestamp)}${escapeHtml(model)}</div>
          <div class="timeline-event">${escapeHtml(status)}</div>
        </span>
      </div>`;
    }).join('')}
  </div>` : '';
  const feedHtml = feedEntries.length ? `<div class="worker-output-detail">
    ${feedEntries.map((f, idx) => {
      const role = f.role || 'worker';
      const avatarClass = ['builder','judge','planner','planning_judge'].includes(role) ? role : 'default';
      const avatarText = role.slice(0,2).toUpperCase();
      const status = f.event || 'unknown';
      const content = f.content || '';
      const userPrompt = f.user_prompt || '';
      const usage = f.usage || {};
      const usageStr = usage.total_tokens ? `${usage.total_tokens} tokens` : '';
      return `<div class="worker-output" data-feed-index="${idx}">
        <div class="worker-output-header">
          <span class="worker-output-avatar ${avatarClass}">${avatarText}</span>
          <div class="worker-output-title">
            <div class="worker-output-role">Step ${idx + 1}: ${escapeHtml(role)}</div>
            <div class="worker-output-model">${escapeHtml(f.model || '')}</div>
          </div>
          <span class="worker-output-status ${escapeHtml(status)}">${escapeHtml(status)}</span>
          <span class="worker-output-time">${formatTime(f.timestamp)}</span>
        </div>
        ${userPrompt ? `<div class="worker-output-prompt">${escapeHtml(userPrompt)}</div>` : ''}
        ${content ? `<div class="worker-output-content">${escapeHtml(content)}</div>` : '<div class="worker-output-content" style="color:var(--text-dim)">No content for this event yet.</div>'}
        ${usageStr ? `<div class="worker-output-usage">${usageStr}</div>` : ''}
      </div>`;
    }).join('')}
  </div>` : '<span style="color:var(--text-dim);font-size:13px">No model output yet</span>';

  const receipts = (r.receipts || []).map(v => {
    const cls = v.passed === true ? 'receipt-pass' : v.passed === false ? 'receipt-fail' : '';
    const icon = v.passed === true ? '✓' : v.passed === false ? '✗' : '•';
    return `<div class="receipt-row ${cls}">${icon} ${escapeHtml(String(v.verifier || 'verifier'))} — ${escapeHtml(String(v.status || 'unknown'))}</div>`;
  }).join('');
  const receiptsHtml = receipts || '';

  const artifacts = (r.artifacts || []).map(a =>
    `<span class="artifact-chip" onclick="showArtifact('${escapeHtml(r.run_id)}','${escapeHtml(a)}')">${escapeHtml(a)}</span>`
  ).join('');

  return `
    <div class="active-card ${r.stage === 'blocked' ? 'blocked' : ''}">
      <div class="active-top-bar">
        <div class="active-top-bar-left">
          <span class="active-run-id">${escapeHtml(r.run_id)}</span>
          <span class="active-intent" style="font-size:18px;font-weight:700">${escapeHtml(r.intent || '(no intent recorded)')}</span>
          ${r.repo ? `<span class="active-repo">📁 ${escapeHtml(r.repo)}</span>` : ''}
        </div>
        <span class="stage-badge ${escapeHtml(r.stage)}">${escapeHtml(r.stage_label || r.stage)}</span>
      </div>
      <div class="active-progress-bar-section">
        <div class="progress-bar">${segments}</div>
        <div class="stage-labels">${labels}</div>
      </div>
      <div class="active-columns">
        <div class="active-left">
          <div class="panel-title">Artifacts <span class="count">${(r.artifacts||[]).length}</span></div>
          <div class="artifacts-row">${artifacts || '<span style="color:var(--text-dim)">None</span>'}</div>
          <div class="artifact-preview" id="preview-${escapeHtml(r.run_id)}"></div>
          ${receiptsHtml ? `<div class="verification-panel"><div class="panel-title">Verification</div>${receiptsHtml}</div>` : ''}
        </div>
        <div class="active-right">
          <div class="panel-title">Worker Outputs — chronological timeline <span class="count">${feedEntries.length}</span></div>
          <div class="worker-feed-container" id="feed-container-${escapeHtml(r.run_id)}">${timelineHtml}${feedHtml}</div>
        </div>
      </div>
    </div>`;
}

function selectWorkerOutput(itemEl, runId) {
  SELECTED_OUTPUT = { runId, index: itemEl.dataset.feedIndex };
  const container = document.getElementById('feed-container-' + runId);
  if (!container) return;
  container.querySelectorAll('.timeline-item').forEach(t => t.classList.remove('active'));
  itemEl.classList.add('active');
  const index = itemEl.dataset.feedIndex;
  container.querySelectorAll('.worker-output').forEach(el => {
    el.style.display = el.dataset.feedIndex === index ? '' : 'none';
  });
}

async function showArtifact(runId, fileName, silent=false) {
  OPEN_ARTIFACT = { runId, fileName };
  const el = document.getElementById('preview-' + runId);
  if (!el) return;  // DOM not ready (e.g. run filtered out)
  el.style.display = 'block';
  if (!silent) el.textContent = 'Loading ' + fileName + '...';
  try {
    const resp = await fetch('/api/artifact?run=' + encodeURIComponent(runId) + '&file=' + encodeURIComponent(fileName));
    const text = await resp.text();
    el.textContent = text.slice(0, 8000);
  } catch (e) {
    el.textContent = 'Failed to load: ' + e;
  }
}

function renderHistoryRow(r) {
  const stageIdx = STAGE_NAMES.indexOf(r.stage);
  const time = (r.events && r.events.length) ? formatTime(r.events[r.events.length - 1].timestamp) : '';
  const dotClass = (r.stage !== 'complete' && r.stage !== 'blocked') ? 'active' : '';
  return `
    <div class="history-row">
      <span class="hist-dot ${dotClass}"></span>
      <span class="hist-intent">${escapeHtml(r.intent || r.run_id)}</span>
      <span class="hist-stage">${escapeHtml(r.stage_label || r.stage)}</span>
      <span class="hist-time">${time}</span>
    </div>`;
}

function formatTime(iso) {
  if (!iso) return '--:--';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch { return '--:--'; }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

refresh();
refreshGit();
refreshMemory();
setInterval(refresh, 3000);
setInterval(refreshGit, 3000);
setInterval(refreshMemory, 2000);
</script>
</body>
</html>
"""
