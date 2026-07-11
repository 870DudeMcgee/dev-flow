"""Embedded HTML page for the DevFlow pipeline status board.

Operator dashboard. Active runs render as a compact queue with exactly one
focused workspace; completed/old runs collapse into history. Auto-refreshes
every 3 seconds while preserving interactive UI state. Explicit controls record
bounded dispatch, cancellation, and stale-lock requests through the V2 server.
"""

STATUS_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DevFlow — Pipeline Status</title>
<style>
  :root {
    --bg: #030615;
    --surface: #080e22;
    --surface-2: #0e1731;
    --surface-3: #121d3d;
    --border: #18345d;
    --border-bright: #24568f;
    --text: #eef7ff;
    --text-dim: #8ea5c8;
    --text-faint: #61789e;
    --accent: #16c9ff;
    --accent-strong: #1677ff;
    --accent-glow: rgba(22, 201, 255, 0.16);
    --violet: #8f5bff;
    --magenta: #ff4fc8;
    --error: #ff4f7f;
    --success: #45efb0;
    --warning: #ffb84d;
    --font-body: 'Avenir Next', Avenir, 'Segoe UI', sans-serif;
    --font-display: 'Avenir Next Condensed', 'DIN Condensed', 'Avenir Next', sans-serif;
    --font-mono: 'SFMono-Regular', 'SF Mono', Menlo, Consolas, monospace;
    --radius: 14px;
    --panel-radius: 10px;
    --header-control-height: 34px;
    --header-control-radius: 9px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { height: 100%; overflow: hidden; }
  body {
    font-family: var(--font-body);
    background:
      radial-gradient(circle at 12% -10%, rgba(0, 201, 255, 0.13), transparent 34%),
      radial-gradient(circle at 88% 0%, rgba(143, 91, 255, 0.12), transparent 32%),
      linear-gradient(145deg, #030615 0%, #05091a 52%, #040617 100%);
    color: var(--text);
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* ── Header ── */
  .header {
    background: linear-gradient(100deg, rgba(7, 14, 35, 0.96), rgba(5, 8, 25, 0.94));
    border-bottom: 1px solid rgba(22, 201, 255, 0.24);
    padding: 14px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 10;
    flex: 0 0 auto;
    box-shadow: 0 12px 38px rgba(0, 0, 0, 0.32), 0 1px 0 rgba(143, 91, 255, 0.12);
    backdrop-filter: blur(18px);
  }
  .header h1 {
    font-family: var(--font-display);
    font-size: 34px;
    font-weight: 800;
    font-style: italic;
    letter-spacing: -0.025em;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 10px;
    color: transparent;
    background: linear-gradient(100deg, #20e8ff 8%, #1687ff 46%, #a65cff 76%, #ff4fc8 100%);
    background-clip: text;
    -webkit-background-clip: text;
    filter: drop-shadow(0 0 14px rgba(22, 135, 255, 0.2));
  }
  .header h1 .icon {
    width: 68px; height: 68px;
    border-radius: 10px;
    display: block;
    object-fit: contain;
    filter: drop-shadow(0 0 12px rgba(22, 201, 255, 0.28)) drop-shadow(0 0 20px rgba(143, 91, 255, 0.14));
  }
  .header-right { display: flex; align-items: center; gap: 16px; position: relative; min-width: 0; flex: 1; justify-content: flex-end; }
  .git-widget {
    display: grid;
    grid-template-columns: 28px minmax(120px, 1fr) auto;
    align-items: center;
    gap: 9px;
    min-width: 286px;
    max-width: 380px;
    padding: 7px 10px;
    border: 1px solid rgba(22, 201, 255, 0.24);
    border-radius: 999px;
    background: linear-gradient(135deg, rgba(22, 201, 255, 0.09), rgba(7, 12, 31, 0.9));
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04), 0 0 20px rgba(22, 201, 255, 0.06);
    cursor: pointer;
    transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
  }
  .git-widget:hover, .git-widget.open { transform: translateY(-1px); border-color: rgba(22, 201, 255, 0.5); box-shadow: inset 0 1px 0 rgba(255,255,255,0.05), 0 0 26px rgba(22, 201, 255, 0.13); }
  .git-widget.dirty { border-color: rgba(255,184,77,0.5); background: linear-gradient(135deg, rgba(255,184,77,0.13), rgba(7,12,31,0.9)); }
  .git-widget.unpushed, .git-widget.behind, .git-widget.local { border-color: rgba(14,165,233,0.38); background: linear-gradient(135deg, rgba(14,165,233,0.12), rgba(15,17,23,0.86)); }
  .git-icon { width: 24px; height: 24px; border-radius: 8px; display: flex; align-items: center; justify-content: center; background: rgba(22,201,255,0.15); color: #6ee7ff; font-size: 13px; }
  .git-widget.dirty .git-icon { background: rgba(245,158,11,0.18); color: var(--warning); }
  .git-widget.unpushed .git-icon, .git-widget.behind .git-icon, .git-widget.local .git-icon { background: rgba(14,165,233,0.16); color: #7dd3fc; }
  .git-copy { min-width: 0; }
  .git-repo { font-size: 10px; line-height: 1; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .git-branch { margin-top: 3px; font: 700 12px/1 var(--font-mono); color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .git-state { font-size: 10px; padding: 4px 8px; border-radius: 999px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.04em; white-space: nowrap; background: rgba(16,185,129,0.16); color: var(--success); border: 1px solid rgba(16,185,129,0.25); }
  .git-widget.dirty .git-state { background: rgba(245,158,11,0.16); color: var(--warning); border-color: rgba(245,158,11,0.28); }
  .git-widget.unpushed .git-state, .git-widget.behind .git-state, .git-widget.local .git-state { background: rgba(14,165,233,0.14); color: #7dd3fc; border-color: rgba(14,165,233,0.25); }
  .git-popover {
    position: absolute;
    top: 44px;
    right: 214px;
    width: min(520px, calc(100vw - 48px));
    max-height: min(560px, calc(100vh - 96px));
    display: none;
    flex-direction: column;
    overflow: hidden;
    z-index: 20;
    background: rgba(5, 10, 28, 0.98);
    border: 1px solid rgba(22,201,255,0.34);
    border-radius: 16px;
    box-shadow: 0 20px 70px rgba(0,0,0,0.5), 0 0 30px rgba(22,201,255,0.12);
    backdrop-filter: blur(12px);
  }
  .git-popover.open { display: flex; }
  .git-popover-head { padding: 14px 16px 10px; border-bottom: 1px solid var(--border); display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
  .git-popover-title { font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); font-weight: 800; }
  .git-popover-branch { margin-top: 4px; font: 700 13px var(--font-mono); color: var(--text); word-break: break-all; }
  .git-popover-meta { margin-top: 7px; display: flex; flex-wrap: wrap; gap: 6px; }
  .git-meta-pill { font-size: 10px; padding: 3px 7px; border: 1px solid var(--border); border-radius: 999px; color: var(--text-dim); background: rgba(255,255,255,0.03); }
  .git-popover-close { border: 1px solid var(--border); background: var(--surface-2); color: var(--text-dim); border-radius: 8px; width: 28px; height: 28px; cursor: pointer; }
  .git-popover-close:hover { color: var(--text); border-color: var(--accent); }
  .git-change-list { padding: 8px; overflow-y: auto; }
  .git-change-row { display: grid; grid-template-columns: 84px 1fr 42px; gap: 10px; align-items: center; padding: 9px 10px; border-radius: 10px; color: var(--text); }
  .git-change-row:hover { background: rgba(22,201,255,0.07); }
  .git-change-label { font-size: 10px; padding: 3px 7px; border-radius: 999px; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 800; text-align: center; color: var(--text-dim); background: rgba(156,163,175,0.12); }
  .git-change-label.staged { color: var(--success); background: rgba(16,185,129,0.13); }
  .git-change-label.unstaged { color: var(--warning); background: rgba(245,158,11,0.13); }
  .git-change-label.untracked { color: #7dd3fc; background: rgba(14,165,233,0.13); }
  .git-change-label.mixed { color: #c9b8ff; background: rgba(143,91,255,0.16); }
  .git-change-path { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 12px var(--font-mono); }
  .git-change-code { color: var(--text-dim); font: 11px var(--font-mono); text-align: right; }
  .git-empty { padding: 20px; color: var(--text-dim); font-size: 13px; text-align: center; }
  .memory-widget {
    display: grid;
    grid-template-columns: 84px 78px;
    align-items: center;
    gap: 10px;
    min-width: 182px;
    padding: 7px 10px;
    border: 1px solid rgba(143,91,255,0.25);
    border-radius: 999px;
    background: linear-gradient(135deg, rgba(143,91,255,0.10), rgba(7,12,31,0.9));
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.04), 0 0 20px rgba(143,91,255,0.07);
  }
  .memory-widget.warn { border-color: rgba(245,158,11,0.42); background: linear-gradient(135deg, rgba(245,158,11,0.14), rgba(15,17,23,0.86)); }
  .memory-widget.critical { border-color: rgba(239,68,68,0.55); background: linear-gradient(135deg, rgba(239,68,68,0.14), rgba(15,17,23,0.88)); }
  .memory-copy { min-width: 0; }
  .memory-label { display: flex; align-items: center; gap: 5px; font-size: 10px; line-height: 1; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-dim); font-weight: 800; }
  .memory-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--success); box-shadow: 0 0 8px rgba(16,185,129,0.55); }
  .memory-widget.warn .memory-dot { background: var(--warning); box-shadow: 0 0 8px rgba(245,158,11,0.58); }
  .memory-widget.critical .memory-dot { background: var(--error); box-shadow: 0 0 8px rgba(239,68,68,0.58); }
  .memory-value { margin-top: 3px; font: 700 12px/1 var(--font-mono); color: var(--text); white-space: nowrap; }
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
    font-family: var(--font-mono);
    max-width: 380px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .live-indicator { display: flex; align-items: center; gap: 6px; font: 800 11px/1 var(--font-display); letter-spacing: 0.11em; color: var(--success); }
  .ui-version { font: 800 10px/1 var(--font-display); letter-spacing: 0.1em; color: #b8c9e5; border: 1px solid rgba(143,91,255,0.3); border-radius: 999px; padding: 5px 9px; background: rgba(143,91,255,0.09); }
  .live-dot { width: 8px; height: 8px; background: var(--success); border-radius: 50%; animation: pulse 2s infinite; box-shadow: 0 0 10px rgba(69,239,176,0.7); }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

  /* ── Layout ── */
  .content { flex: 1; max-width: 1600px; width: 100%; margin: 0 auto; padding: 10px 18px 12px; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
  .section-label {
    font: 800 11px/1 var(--font-display); text-transform: uppercase; letter-spacing: 0.16em;
    color: #78dfff; margin: 0 0 8px; flex: 0 0 auto;
  }

  .run-queue {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 8px; margin-bottom: 10px; flex: 0 0 auto;
  }
  .run-queue-item {
    min-width: 0; display: grid;
    grid-template-columns: 10px minmax(0, 1fr) auto;
    grid-template-areas: "signal intent stage" "signal meta status";
    gap: 3px 10px; align-items: center; padding: 10px 12px;
    border: 1px solid var(--border); border-radius: 10px;
    background: rgba(7, 14, 35, 0.78); color: var(--text);
    text-align: left; cursor: pointer; font-family: inherit;
  }
  .run-queue-item:hover { border-color: var(--border-bright); background: rgba(12, 25, 54, 0.88); }
  .run-queue-item.selected { border-color: var(--accent); box-shadow: 0 0 18px rgba(22,201,255,0.12); }
  .run-signal { grid-area: signal; width: 8px; height: 34px; border-radius: 4px; background: var(--accent); }
  .run-queue-item.failed .run-signal, .run-queue-item.stalled .run-signal { background: var(--error); }
  .run-queue-item.cancelling .run-signal { background: var(--warning); }
  .run-queue-intent { grid-area: intent; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 800; }
  .run-queue-meta { grid-area: meta; color: var(--text-dim); font: 10px var(--font-mono); }
  .run-queue-stage { grid-area: stage; color: var(--accent); font-size: 10px; font-weight: 900; text-transform: uppercase; }
  .run-queue-status { grid-area: status; color: var(--text-dim); font-size: 9px; font-weight: 900; text-transform: uppercase; text-align: right; }
  .execution-status { margin-left: 8px; color: var(--warning); font: 900 10px var(--font-display); letter-spacing: .08em; text-transform: uppercase; }

  /* ── Run selector dropdown (collapsible active runs) ── */
  .run-selector { position: relative; margin-bottom: 10px; flex: 0 0 auto; }
  .run-selector-trigger {
    width: 100%; display: grid;
    grid-template-columns: 10px minmax(0, 1fr) auto auto 18px;
    grid-template-areas: "signal intent stage status chevron" "signal meta stage status chevron";
    gap: 3px 10px; align-items: center; padding: 10px 14px;
    border: 1px solid var(--border-bright); border-radius: 10px;
    background: linear-gradient(135deg, rgba(22,201,255,0.08), rgba(7,14,35,0.85));
    color: var(--text); text-align: left; cursor: pointer; font-family: inherit;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .run-selector-trigger:hover { border-color: var(--accent); }
  .run-selector.open .run-selector-trigger {
    border-color: var(--accent); box-shadow: 0 0 18px rgba(22,201,255,0.12);
    border-bottom-left-radius: 0; border-bottom-right-radius: 0;
  }
  .run-selector-trigger.failed, .run-selector-item.failed { border-color: rgba(239,68,68,0.4); }
  .run-selector-trigger.stalled, .run-selector-item.stalled { border-color: rgba(239,68,68,0.4); }
  .run-selector-trigger.failed .run-signal, .run-selector-trigger.stalled .run-signal,
  .run-selector-item.failed .run-signal, .run-selector-item.stalled .run-signal { background: var(--error); }
  .run-selector-trigger.cancelling .run-signal,
  .run-selector-item.cancelling .run-signal { background: var(--warning); }
  .run-selector-chevron { grid-area: chevron; font-size: 11px; color: var(--text-dim); transition: transform 0.2s; justify-self: end; }
  .run-selector.open .run-selector-chevron { transform: rotate(180deg); }
  .run-selector-intent { grid-area: intent; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 800; }
  .run-selector-meta { grid-area: meta; color: var(--text-dim); font: 10px var(--font-mono); }
  .run-selector-stage { grid-area: stage; color: var(--accent); font-size: 10px; font-weight: 900; text-transform: uppercase; white-space: nowrap; }
  .run-selector-status { grid-area: status; color: var(--text-dim); font-size: 9px; font-weight: 900; text-transform: uppercase; text-align: right; white-space: nowrap; }
  .run-selector-dropdown {
    display: none; position: absolute; top: 100%; left: 0; right: 0;
    background: rgba(5, 10, 28, 0.98); border: 1px solid var(--accent); border-top: 0;
    border-radius: 0 0 10px 10px; overflow-y: auto; overflow-x: hidden;
    z-index: 15; max-height: 320px;
    box-shadow: 0 12px 40px rgba(0,0,0,0.45);
    backdrop-filter: blur(12px);
  }
  .run-selector.open .run-selector-dropdown { display: block; }
  .run-selector-item {
    width: 100%; display: grid;
    grid-template-columns: 10px minmax(0, 1fr) auto auto;
    grid-template-areas: "signal intent stage status" "signal meta stage status";
    gap: 3px 10px; align-items: center; padding: 10px 14px;
    border: 0; border-top: 1px solid rgba(24,52,93,0.5);
    background: transparent; color: var(--text);
    text-align: left; cursor: pointer; font-family: inherit;
    transition: background 0.12s;
  }
  .run-selector-item:hover { background: rgba(22,201,255,0.08); }
  .run-selector-item.selected { background: rgba(22,201,255,0.12); }

  /* ── ACTIVE: big front-and-center card ── */
  .active-card {
    background: linear-gradient(155deg, rgba(10,18,43,0.98), rgba(6,11,29,0.98));
    border: 1px solid rgba(22,201,255,0.48);
    border-radius: var(--radius);
    box-shadow: 0 18px 60px rgba(0,0,0,0.34), 0 0 30px var(--accent-glow), inset 0 1px 0 rgba(255,255,255,0.035);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    flex: 1 1 auto;
    height: auto;
    min-height: 480px;
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
  .active-run-id { font-family: var(--font-mono); font-size: 12px; color: #75dfff; }
  .active-intent { font-family: var(--font-display); font-size: 22px; font-weight: 800; line-height: 1.25; letter-spacing: 0.01em; }
  .active-repo { font-size: 12px; color: var(--text-dim); font-family: var(--font-mono); }

  .stage-badge {
    font-size: 13px; font-weight: 700; padding: 7px 16px; border-radius: 20px;
    white-space: nowrap; align-self: flex-start;
  }
  .stage-badge.idea, .stage-badge.definition { background: rgba(22,201,255,0.13); color: var(--accent); border: 1px solid rgba(22,201,255,0.24); }
  .stage-badge.spec, .stage-badge.planning, .stage-badge.planning_judge { background: rgba(245,158,11,0.2); color: var(--warning); }
  .stage-badge.assignment, .stage-badge.build_judge { background: rgba(143,91,255,0.18); color: #c8b4ff; border: 1px solid rgba(143,91,255,0.28); }
  .stage-badge.verification { background: rgba(16,185,129,0.2); color: var(--success); }
  .stage-badge.human_decision { background: rgba(245,158,11,0.3); color: var(--warning); }
  .stage-badge.complete { background: rgba(16,185,129,0.15); color: var(--success); }
  .stage-badge.blocked { background: rgba(239,68,68,0.2); color: var(--error); }

  .active-progress { padding: 16px 24px 4px; }
  .progress-bar { display: flex; gap: 5px; align-items: center; }
  .progress-segment { flex: 1; height: 14px; border-radius: 6px; background: var(--surface-2); transition: background 0.3s; }
  .progress-segment.done { background: linear-gradient(90deg, var(--accent-strong), var(--accent)); box-shadow: 0 0 10px rgba(22,201,255,0.18); }
  .progress-segment.current { background: linear-gradient(90deg, var(--accent), var(--violet)); animation: shimmer 1.5s infinite; box-shadow: 0 0 14px rgba(143,91,255,0.28); }
  .progress-segment.blocked { background: var(--error); }
  @keyframes shimmer { 0%, 100% { opacity: 1; } 50% { opacity: 0.45; } }
  .stage-labels { display: flex; gap: 5px; margin-top: 6px; font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.03em; }
  .stage-labels span { flex: 1; text-align: center; white-space: nowrap; }
  .stage-labels span.current { color: var(--accent); font-weight: 700; }

  .active-body { padding: 4px 24px 8px; }
  .panel-title { font: 800 11px/1 var(--font-display); text-transform: uppercase; letter-spacing: 0.12em; color: #a9bad5; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
  .panel-title .count { background: linear-gradient(100deg, var(--accent-strong), var(--violet)); color: #fff; border-radius: 10px; padding: 2px 8px; font-size: 10px; }

  /* ── Worker output: operator summary → attempts → raw evidence ── */
  .worker-feed-container {
    flex: 1; min-height: 0;
    display: grid;
    grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    grid-template-areas: "summary summary" "attempts viewer";
    gap: 12px; overflow: hidden;
  }
  .worker-current-summary {
    grid-area: summary; min-width: 0;
    display: grid; grid-template-columns: minmax(0, 1fr) auto;
    gap: 5px 16px; padding: 11px 14px;
    border: 1px solid var(--border); border-left: 3px solid var(--accent);
    border-radius: 10px; background: linear-gradient(100deg, rgba(22,201,255,0.10), rgba(143,91,255,0.055) 48%, rgba(5,10,27,0.45));
  }
  .worker-current-summary.failed { border-left-color: var(--error); background: linear-gradient(90deg, rgba(239,68,68,0.11), rgba(13,15,22,0.35)); }
  .worker-current-summary.needs_attention { border-left-color: var(--warning); background: linear-gradient(90deg, rgba(245,158,11,0.11), rgba(13,15,22,0.35)); }
  .worker-current-summary.passed { border-left-color: var(--success); background: linear-gradient(90deg, rgba(16,185,129,0.10), rgba(13,15,22,0.35)); }
  .worker-current-kicker { font-size: 10px; line-height: 1; text-transform: uppercase; letter-spacing: 0.09em; color: var(--text-dim); font-weight: 800; }
  .worker-current-headline { grid-column: 1; min-width: 0; font-size: 14px; line-height: 1.3; font-weight: 800; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .worker-current-next { grid-column: 1 / -1; min-width: 0; font-size: 12px; line-height: 1.35; color: var(--text-dim); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .worker-current-next strong { color: var(--text); font-weight: 700; }
  .outcome-badge { align-self: center; justify-self: end; padding: 3px 8px; border-radius: 999px; font-size: 9px; line-height: 1.2; font-weight: 900; text-transform: uppercase; letter-spacing: 0.06em; border: 1px solid var(--border); color: var(--text-dim); }
  .outcome-badge.failed { border-color: rgba(239,68,68,0.55); color: var(--error); background: rgba(239,68,68,0.12); }
  .outcome-badge.needs_attention, .outcome-badge.running { border-color: rgba(245,158,11,0.5); color: var(--warning); background: rgba(245,158,11,0.10); }
  .outcome-badge.passed { border-color: rgba(16,185,129,0.5); color: var(--success); background: rgba(16,185,129,0.10); }
  .worker-card-list { grid-area: attempts; overflow-y: auto; overflow-anchor: none; padding-right: 4px; display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .worker-list-heading { padding: 0 2px 2px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; font-weight: 800; color: var(--text-dim); }
  .worker-loop-group { flex: 0 0 auto; border: 1px solid var(--border); border-radius: var(--panel-radius); background: rgba(5,10,28,0.58); overflow: hidden; }
  .worker-loop-group:not([open]) { min-height: 50px; }
  .worker-loop-group.current-loop { border-color: rgba(22,201,255,0.42); box-shadow: 0 0 16px rgba(22,201,255,0.06); }
  .worker-loop-group summary {
    display: grid; align-items: center; column-gap: 7px; row-gap: 3px;
    grid-template-columns: 10px minmax(0, 1fr) auto;
    grid-template-areas: "chevron title outcome" ". meta meta";
    padding: 8px 10px; cursor: pointer; color: var(--text); min-width: 0;
    font-size: 11px; font-weight: 800; line-height: 1.25;
    list-style: none;
  }
  .worker-loop-group summary::-webkit-details-marker { display: none; }
  .worker-loop-group summary::before { content: '▸'; grid-area: chevron; font-size: 9px; color: var(--text-dim); transition: transform 0.15s; }
  .worker-loop-group[open] summary::before { transform: rotate(90deg); }
  .worker-loop-group summary .loop-title { grid-area: title; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .worker-loop-group summary .loop-subtitle { grid-area: meta; min-width: 0; font: 10px/1.3 var(--font-mono); color: var(--text-dim); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .worker-loop-group summary .loop-outcome { grid-area: outcome; }
  .worker-loop-items { display: flex; flex-direction: column; gap: 4px; padding: 0 6px 6px; }
  .worker-loop-group.previous-loops { border-color: rgba(255,255,255,0.08); background: rgba(8,14,34,0.42); }
  .worker-loop-group.previous-loops > summary { font-weight: 700; color: var(--text-dim); }
  .worker-loop-group.previous-loops .worker-loop-group { background: rgba(5,10,28,0.4); border-color: rgba(255,255,255,0.06); }
  .worker-loop-group.previous-loops[open] > summary { border-bottom: 1px solid var(--border); padding-bottom: 10px; }
  .output-card {
    width: 100%; display: grid; align-items: center; gap: 2px 7px;
    grid-template-columns: 22px minmax(0, 1fr) auto;
    grid-template-areas: "avatar role time" "avatar summary outcome";
    padding: 7px 9px; border-radius: 7px;
    border: 1px solid var(--border); background: var(--surface-2);
    color: inherit; font: inherit; text-align: left; cursor: pointer; transition: all 0.12s; min-width: 0;
  }
  .output-card:hover { border-color: var(--accent); background: rgba(22,201,255,0.065); }
  .output-card.selected { border-color: var(--accent); background: linear-gradient(100deg, rgba(22,201,255,0.12), rgba(143,91,255,0.075)); box-shadow: 0 0 16px rgba(22,201,255,0.1); }
  .output-card:focus-visible, .worker-loop-group summary:focus-visible, .viewer-tab:focus-visible { outline: 2px solid #75e3ff; outline-offset: 2px; }
  .output-avatar { grid-area: avatar; width: 20px; height: 20px; border-radius: 5px; display: flex; align-items: center; justify-content: center; font-size: 8px; font-weight: 700; color: #fff; }
  .output-avatar.builder { background: var(--accent); }
  .output-avatar.judge { background: var(--warning); }
  .output-avatar.planner { background: #0ea5e9; }
  .output-avatar.planning_judge { background: #8b5cf6; }
  .output-avatar.default { background: var(--text-dim); }
  .output-card-role { grid-area: role; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; font-weight: 700; color: var(--text); }
  .output-card-summary { grid-area: summary; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; color: var(--text-dim); }
  .output-card-time { grid-area: time; font-size: 10px; color: var(--text-dim); font-family: var(--font-mono); }
  .output-card-outcome { grid-area: outcome; font-size: 8px; }
  .output-card.streaming { border-color: var(--accent); animation: streamPulse 1.6s ease-in-out infinite; }
  .output-card .card-live-dot { display: none; }
  .output-card.streaming .card-live-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); margin-left: 4px; animation: liveBlink 0.8s ease-in-out infinite alternate; }
  @keyframes streamPulse { 0%,100% { box-shadow: 0 0 0 rgba(22,201,255,0); } 50% { box-shadow: 0 0 12px rgba(22,201,255,0.28); } }
  @keyframes liveBlink { 0% { opacity: 0.3; } 100% { opacity: 1; } }
  .viewer-panel.output-viewer-reasoning { padding: 12px 14px; font-size: 12px; line-height: 1.55; color: var(--text-dim); white-space: pre-wrap; word-break: break-word; border-left: 2px solid rgba(143,91,255,0.5); }

  .output-viewer { grid-area: viewer; min-width: 0; min-height: 0; display: flex; flex-direction: column; background: rgba(4,9,25,0.92); border: 1px solid var(--border); border-radius: var(--panel-radius); overflow: hidden; }
  .output-viewer-header { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-bottom: 1px solid var(--border); background: linear-gradient(90deg, rgba(22,201,255,0.06), rgba(143,91,255,0.04)); flex-shrink: 0; }
  .output-viewer-title { flex: 1; min-width: 0; }
  .output-viewer-role { font-size: 14px; font-weight: 700; color: var(--text); }
  .output-viewer-model { font-size: 11px; color: var(--text-dim); margin-top: 1px; }
  .output-status { font-size: 9px; padding: 2px 7px; border-radius: 3px; font-weight: 700; text-transform: uppercase; flex-shrink: 0; }
  .viewer-tabs { display: flex; align-items: center; gap: 3px; padding: 6px 10px; border-bottom: 1px solid var(--border); background: rgba(0,0,0,0.18); overflow-x: auto; overflow-y: hidden; flex: 0 0 auto; }
  .viewer-tab { flex: 0 0 auto; white-space: nowrap; border: 0; border-radius: 5px; padding: 5px 8px; background: transparent; color: var(--text-dim); font: 800 10px var(--font-display); letter-spacing: 0.04em; cursor: pointer; }
  .viewer-tab.active { background: var(--surface-2); color: var(--text); }
  .viewer-panel { display: none; flex: 1; min-height: 0; overflow-y: auto; }
  .viewer-panel.active { display: block; }
  .output-summary-panel { padding: 14px; }
  .output-summary-line { margin-bottom: 12px; font-size: 14px; line-height: 1.45; font-weight: 750; }
  .operator-detail { padding: 10px 0; border-top: 1px solid rgba(24,52,93,0.62); }
  .operator-detail:first-of-type { border-top: 0; padding-top: 0; }
  .operator-detail-label { margin-bottom: 3px; color: var(--text-dim); font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 800; }
  .operator-detail-value { font-size: 13px; line-height: 1.5; color: var(--text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .output-fact { display: grid; grid-template-columns: 112px minmax(0, 1fr); gap: 10px; padding: 7px 0; border-top: 1px solid rgba(24,52,93,0.62); font-size: 12px; line-height: 1.4; }
  .output-fact-label { color: var(--text-dim); font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 800; }
  .output-viewer-time { font-size: 11px; color: var(--text-dim); font-family: var(--font-mono); flex-shrink: 0; }
  .output-viewer-prompt { padding: 12px 14px; font-size: 11px; line-height: 1.5; color: var(--text-dim); white-space: pre-wrap; word-break: break-word; }
  .output-viewer-content { padding: 14px; font-size: 13px; line-height: 1.6; color: var(--text); white-space: pre-wrap; word-break: break-word; flex: 1; min-height: 0; overflow-y: auto; }
  .output-viewer-usage { padding: 4px 14px 10px; font-size: 10px; color: var(--text-dim); flex-shrink: 0; }
  @media (max-width: 900px) {
    .worker-feed-container { grid-template-columns: 1fr; grid-template-rows: auto minmax(160px, 34%) minmax(0, 1fr); grid-template-areas: "summary" "attempts" "viewer"; }
  }

  /* ── Artifact preview ── */
  .artifacts-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .artifact-chip { font-size: 11px; padding: 4px 9px; border-radius: 5px; background: var(--surface-2); color: var(--text-dim); border: 1px solid var(--border); cursor: pointer; }
  .artifact-chip:hover { border-color: var(--accent); color: var(--text); }
  .artifact-preview { margin-top: 10px; background: #030819; border: 1px solid var(--border); border-radius: 8px; padding: 10px; font-family: var(--font-mono); font-size: 11px; color: var(--text-dim); white-space: pre-wrap; word-break: break-word; display: none; flex: 1; min-height: 0; max-height: none; overflow-y: auto; }
  .verification-panel { margin-top: 16px; flex-shrink: 0; }
  .receipt-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; font-size: 13px; }
  .receipt-pass { color: var(--success); }
  .receipt-fail { color: var(--error); }

  /* ── OPERATOR CONTROL: appears only at gated decision points ── */
  .operator-control {
    border: 1px solid rgba(245, 158, 11, 0.45);
    background: rgba(245, 158, 11, 0.10);
    border-radius: 12px;
    padding: 12px;
    margin-bottom: 12px;
  }
  .operator-control-title { font-size: 13px; font-weight: 800; color: var(--warning); margin-bottom: 4px; }
  .operator-control-copy { color: var(--text); font-size: 13px; line-height: 1.45; margin-bottom: 10px; }
  .operator-control-actions { display: flex; gap: 8px; flex-wrap: wrap; }
  .operator-button {
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 8px 12px;
    font: 800 12px var(--font-body);
    cursor: pointer;
    color: var(--text);
    background: var(--surface);
  }
  .operator-button.primary { border-color: var(--success); background: rgba(16, 185, 129, 0.14); color: var(--success); }
  .operator-button.secondary { border-color: var(--warning); background: rgba(245, 158, 11, 0.12); color: var(--warning); }
  .operator-button.danger { border-color: var(--error); background: rgba(255,79,127,0.12); color: var(--error); }
  .operator-control-status { margin-top: 8px; color: var(--text-dim); font-size: 12px; }

  /* ── HISTORY: compact rows ── */
  .history-list {
    flex: 0 1 60px;
    min-height: 0;
    max-height: 60px;
    overflow-y: auto;
  }
  .history-row {
    display: flex; align-items: center; gap: 12px;
    width: 100%;
    padding: 9px 16px;
    border-bottom: 1px solid var(--border);
    border-left: 0; border-right: 0; border-top: 0;
    background: transparent;
    color: inherit;
    cursor: pointer;
    font-size: 13px;
    font-family: inherit;
    text-align: left;
  }
  .history-row:hover { background: var(--surface); }
  .history-row.selected { background: rgba(110, 168, 255, 0.12); }
  .hist-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); flex-shrink: 0; }
  .hist-dot.active { background: var(--accent); }
  .hist-intent { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
  .hist-stage { font-size: 11px; color: var(--text-dim); font-weight: 600; min-width: 90px; text-align: right; }
  .hist-time { font-size: 11px; color: var(--text-dim); font-family: var(--font-mono); min-width: 70px; text-align: right; }

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
  /* ── Workspace picker ── */
  .workspace-widget {
    display: flex; align-items: center; gap: 8px;
    padding: 7px 12px; border-radius: 999px;
    border: 1px solid rgba(22,201,255,0.28);
    background: linear-gradient(135deg, rgba(22,201,255,0.10), rgba(7,12,31,0.9));
    cursor: pointer; transition: all 0.15s;
    position: relative; min-width: 0; max-width: 180px;
  }
  .workspace-widget:hover { border-color: var(--accent); box-shadow: 0 0 18px rgba(22,201,255,0.12); }
  .workspace-widget.no-workspace { border-color: rgba(245,158,11,0.4); background: linear-gradient(135deg, rgba(245,158,11,0.10), rgba(7,12,31,0.9)); }
  .workspace-icon { font-size: 15px; line-height: 1; flex-shrink: 0; }
  .workspace-copy { min-width: 0; }
  .workspace-label { font: 800 9px/1 var(--font-display); text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-dim); }
  .workspace-name { font: 700 13px/1.2 var(--font-body); color: var(--text); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px; }
  .workspace-widget.no-workspace .workspace-name { color: var(--warning); }
  .workspace-chevron { font-size: 10px; color: var(--text-dim); flex-shrink: 0; }
  .workspace-dropdown {
    position: absolute; top: calc(100% + 6px); right: 0;
    width: min(420px, calc(100vw - 48px));
    max-height: min(440px, calc(100vh - 100px));
    display: none; flex-direction: column;
    background: rgba(5,10,28,0.98); border: 1px solid rgba(22,201,255,0.34);
    border-radius: 14px; overflow: hidden; z-index: 25;
    box-shadow: 0 20px 70px rgba(0,0,0,0.5), 0 0 30px rgba(22,201,255,0.12);
    backdrop-filter: blur(12px);
  }
  .workspace-dropdown.open { display: flex; }
  .workspace-dd-header { padding: 12px 14px 10px; border-bottom: 1px solid var(--border); }
  .workspace-dd-title { font: 800 11px/1 var(--font-display); text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-dim); }
  .workspace-dd-actions { display: flex; gap: 6px; margin-top: 8px; }
  .workspace-dd-btn {
    flex: 1; border: 1px solid var(--border); background: var(--surface-2);
    color: var(--text); border-radius: 8px; padding: 7px 10px;
    font: 700 12px var(--font-body); cursor: pointer; transition: all 0.15s;
    display: flex; align-items: center; justify-content: center; gap: 5px;
  }
  .workspace-dd-btn:hover { border-color: var(--accent); color: var(--accent); }
  .workspace-dd-btn.primary { border-color: var(--accent); background: rgba(22,201,255,0.12); color: var(--accent); }
  .workspace-dd-list { overflow-y: auto; flex: 1; padding: 4px; }
  .workspace-dd-section { font: 800 9px/1 var(--font-display); text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-faint); padding: 8px 10px 4px; }
  .workspace-dd-item {
    display: flex; align-items: center; gap: 8px; width: 100%;
    padding: 8px 10px; border: 0; border-radius: 8px;
    background: transparent; color: var(--text); text-align: left;
    cursor: pointer; font: 13px var(--font-body); transition: background 0.12s;
  }
  .workspace-dd-item:hover { background: rgba(22,201,255,0.08); }
  .workspace-dd-item.active { background: rgba(22,201,255,0.12); }
  .workspace-dd-item .item-folder { font-size: 14px; flex-shrink: 0; opacity: 0.7; }
  .workspace-dd-item .item-copy { flex: 1; min-width: 0; }
  .workspace-dd-item .item-name { font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .workspace-dd-item .item-path { font: 10px var(--font-mono); color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-top: 1px; }
  .workspace-dd-item .item-remove { font-size: 14px; color: var(--text-faint); padding: 2px 6px; border-radius: 4px; flex-shrink: 0; opacity: 0; transition: opacity 0.15s, color 0.15s; }
  .workspace-dd-item:hover .item-remove { opacity: 0.6; }
  .workspace-dd-item .item-remove:hover { opacity: 1; color: var(--error); }
  .workspace-dd-item.missing { opacity: 0.5; }
  .workspace-dd-item.missing .item-name { color: var(--text-faint); }
  .workspace-dd-empty { padding: 20px; text-align: center; color: var(--text-dim); font-size: 13px; }

  /* ── Chat sidebar ── */
  .app-shell { display: flex; flex: 1; min-height: 0; overflow: hidden; }

  .chat-sidebar {
    width: 380px; flex-shrink: 0;
    display: flex; flex-direction: column;
    border-left: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(5,10,28,0.96), rgba(4,8,22,0.98));
    overflow: hidden;
  }
  .chat-header {
    padding: 14px 16px 10px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    display: flex; flex-direction: column; gap: 8px;
  }
  .chat-title-row { display: flex; align-items: center; justify-content: space-between; }
  .chat-title {
    font: 800 13px/1 var(--font-display);
    text-transform: uppercase; letter-spacing: 0.12em; color: var(--accent);
  }
  .chat-session-select {
    background: var(--surface-2); border: 1px solid var(--border); border-radius: 6px;
    color: var(--text); font: 11px var(--font-body); padding: 3px 6px;
    max-width: 140px; cursor: pointer;
  }
  .chat-session-select:hover { border-color: var(--accent); }
  .chat-model-select {
    background: var(--surface-2); border: 1px solid var(--border); border-radius: 6px;
    color: var(--text); font: 11px var(--font-body); padding: 4px 8px;
    width: 100%; cursor: pointer;
  }
  .chat-model-select:hover { border-color: var(--accent); }

  .chat-messages {
    flex: 1; min-height: 0; overflow-y: auto;
    padding: 12px 14px; display: flex; flex-direction: column; gap: 10px;
  }
  .chat-msg {
    max-width: 92%; padding: 9px 12px; border-radius: 12px;
    font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-break: break-word;
  }
  .chat-msg.user {
    align-self: flex-end;
    background: linear-gradient(135deg, var(--accent-strong), var(--accent));
    color: #fff; border-bottom-right-radius: 4px;
  }
  .chat-msg.assistant {
    align-self: flex-start;
    background: var(--surface-2); color: var(--text);
    border: 1px solid var(--border); border-bottom-left-radius: 4px;
  }
  .chat-msg.assistant .msg-model {
    font-size: 9px; color: var(--text-faint); margin-top: 5px; text-transform: uppercase; letter-spacing: 0.06em;
  }
  .chat-msg.error {
    align-self: center; background: rgba(239,68,68,0.12); border: 1px solid rgba(239,68,68,0.3);
    color: var(--error); font-size: 12px; text-align: center;
  }
  .chat-empty {
    text-align: center; color: var(--text-dim); font-size: 13px;
    padding: 40px 16px; line-height: 1.6;
  }
  .chat-empty .chat-empty-icon { font-size: 32px; margin-bottom: 8px; opacity: 0.4; }
  .chat-typing {
    align-self: flex-start; padding: 9px 14px; border-radius: 12px; border-bottom-left-radius: 4px;
    background: var(--surface-2); border: 1px solid var(--border); color: var(--text-dim);
    font-size: 13px;
  }
  .chat-typing .dot { animation: typingDot 1.4s infinite; display: inline-block; }
  .chat-typing .dot:nth-child(2) { animation-delay: 0.2s; }
  .chat-typing .dot:nth-child(3) { animation-delay: 0.4s; }
  @keyframes typingDot { 0%,60%,100% { opacity: 0.3; } 30% { opacity: 1; } }

  .chat-input-area {
    padding: 10px 14px 12px; border-top: 1px solid var(--border);
    flex-shrink: 0; display: flex; flex-direction: column; gap: 8px;
  }
  .chat-composer-row { display: flex; align-items: stretch; gap: 7px; }
  .chat-input {
    flex: 1; width: 100%; min-width: 0; min-height: 44px; max-height: 140px;
    background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px;
    color: var(--text); font: 13px/1.45 var(--font-body); padding: 10px 12px;
    resize: none; outline: none; transition: border-color 0.15s;
  }
  .chat-input:focus { border-color: var(--accent); }
  .chat-input::placeholder { color: var(--text-faint); }
  .chat-mic-btn {
    flex: 0 0 48px; min-height: 44px; border: 1px solid var(--border); border-radius: 10px;
    background: var(--surface-2); color: var(--text-dim); cursor: pointer;
    display: grid; place-items: center; transition: border-color 0.15s, color 0.15s, background 0.15s;
  }
  .chat-mic-btn svg { width: 19px; height: 19px; stroke: currentColor; }
  .chat-mic-btn:hover:not(:disabled), .chat-mic-btn:focus-visible { border-color: var(--accent); color: var(--accent); outline: none; }
  .chat-mic-btn.listening { border-color: var(--error); color: #fff; background: rgba(255,79,127,0.18); }
  .chat-mic-btn:disabled { opacity: 0.48; cursor: not-allowed; }
  .chat-dictation-state { min-height: 14px; font-size: 10px; line-height: 1.35; color: var(--text-faint); }
  .chat-dictation-state.listening { color: var(--error); font-weight: 700; }
  .chat-send-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .chat-send-btn {
    border: 1px solid var(--accent); background: rgba(22,201,255,0.12);
    color: var(--accent); border-radius: 8px; padding: 6px 18px;
    font: 800 12px var(--font-body); cursor: pointer; transition: all 0.15s;
  }
  .chat-send-btn:hover { background: rgba(22,201,255,0.22); }
  .chat-send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .chat-new-btn {
    border: 1px solid var(--border); background: transparent;
    color: var(--text-dim); border-radius: 8px; padding: 6px 14px;
    font: 800 11px var(--font-body); cursor: pointer; transition: all 0.15s;
  }
  .chat-new-btn:hover { border-color: var(--accent); color: var(--accent); }
  .chat-hint { font-size: 10px; color: var(--text-faint); }
  @media (max-width: 900px) {
    .repo-path { display: none; }
    .git-widget { min-width: 210px; grid-template-columns: 24px minmax(92px, 1fr) auto; }
    .git-popover { right: 0; }
    .memory-widget { grid-template-columns: 72px 58px; min-width: 150px; }
    .memory-graph { width: 58px; }
    .chat-sidebar { width: 300px; }
  }

  /* ── Focused workspace V4: now → activity → evidence on demand ── */
  .header { padding: 6px 12px; gap: 10px; }
  .header h1 { font-size: 19px; flex: 0 0 auto; min-width: 0; }
  .header h1 .icon { width: 34px; height: 34px; }
  .header-right { gap: 7px; min-width: 0; flex: 1; justify-content: flex-end; }
  .git-widget { min-width: 0; width: auto; max-width: 120px; grid-template-columns: 24px auto; padding: 5px 7px; gap: 6px; }
  .git-copy { display: none; }
  .git-repo { display: none; }
  .git-branch { margin-top: 0; font-size: 11px; }
  .git-state { font-size: 9px; padding: 3px 6px; }
  .header-run-selector { min-width: 160px; width: min(360px, 31vw); flex: 1 1 240px; position: relative; }
  .header-run-selector .run-selector { margin: 0; }
  .header-run-selector .run-selector-trigger {
    height: var(--header-control-height); padding: 4px 8px; border-radius: var(--header-control-radius);
    grid-template-columns: 7px minmax(0,1fr) auto 14px;
    grid-template-areas: "signal intent stage chevron";
  }
  .header-run-selector .run-signal { width: 6px; height: 20px; }
  .header-run-selector .run-selector-intent { font-size: 11px; }
  .header-run-selector .run-selector-meta, .header-run-selector .run-selector-status { display: none; }
  .header-run-selector .run-selector-stage { font-size: 10px; }
  .header-run-selector .run-selector-dropdown { min-width: 420px; left: auto; }
  .system-widget {
    height: var(--header-control-height); border: 1px solid var(--border); border-radius: var(--header-control-radius); padding: 0 12px;
    color: var(--text-dim); background: rgba(8,14,34,0.8); cursor: pointer;
    font: 800 11px var(--font-body); transition: border-color 0.15s, color 0.15s;
  }
  .system-widget:hover, .system-widget.open { border-color: var(--accent); color: var(--text); }
  .system-popover {
    display: none; position: absolute; right: 0; top: 48px; z-index: 24;
    width: 250px; padding: 12px; border: 1px solid var(--border-bright);
    border-radius: 14px; background: rgba(5,10,28,0.98);
    box-shadow: 0 20px 70px rgba(0,0,0,0.5); backdrop-filter: blur(12px);
  }
  .system-popover.open { display: flex; flex-direction: column; gap: 10px; }
  .system-meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .header > .header-right > .memory-widget { flex: 0 0 auto; }
  .header .workspace-widget,
  .header .git-widget,
  .header .memory-widget { height: var(--header-control-height); border-radius: var(--header-control-radius); padding-top: 0; padding-bottom: 0; }

  .active-card { position: relative; min-height: 0; box-shadow: 0 14px 44px rgba(0,0,0,0.28); }
  .active-top-bar { min-height: 34px; padding: 5px 12px; }
  .active-top-bar-left { gap: 2px; }
  .active-intent, .active-repo { display: none; }
  .active-run-id { order: 2; font-size: 11px; color: var(--text-dim); }
  .active-progress-bar-section { padding: 3px 12px 6px; }
  .progress-segment { height: 6px; }
  .stage-control {
    flex: 1; min-width: 0; border: 0; border-radius: 5px; padding: 2px 1px 3px;
    background: transparent; color: var(--text-dim); cursor: pointer;
    font: 800 10px var(--font-body); text-transform: uppercase; display: flex; flex-direction: column; gap: 3px; align-items: stretch;
  }
  .stage-control .progress-segment { display: block; width: 100%; flex: 0 0 6px; }
  .stage-control:hover, .stage-control.selected { color: var(--text); background: rgba(22,201,255,0.12); }
  .stage-control.current { color: var(--accent); }
  .stage-control.done { color: #9bc6d9; }
  .stage-control.selected { outline: 1px solid rgba(22,201,255,0.55); }
  .run-header-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  .files-button, .files-close, .view-code-button {
    border: 1px solid var(--border); background: var(--surface-2); color: var(--text);
    border-radius: 8px; padding: 7px 11px; cursor: pointer; font: 800 11px var(--font-body);
  }
  .files-button:hover, .files-button[aria-expanded="true"], .files-close:hover, .view-code-button:hover { border-color: var(--accent); color: var(--accent); }
  .files-count { color: var(--text-dim); margin-left: 4px; }

  .focused-workspace { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 7px 10px 9px; gap: 7px; overflow: hidden; }
  .now-card {
    flex: 0 0 auto; display: grid; grid-template-columns: auto minmax(0,1fr) auto;
    gap: 3px 9px; padding: 7px 10px; border: 1px solid var(--border);
    border-left: 3px solid var(--accent); border-radius: var(--panel-radius);
    background: linear-gradient(100deg, rgba(22,201,255,0.09), rgba(143,91,255,0.04), rgba(5,10,27,0.38));
  }
  .now-card.failed, .now-card.stalled { border-left-color: var(--error); }
  .now-card.needs_attention, .now-card.running { border-left-color: var(--warning); }
  .now-card.passed { border-left-color: var(--success); }
  .now-kicker { font: 800 10px var(--font-display); color: var(--text-dim); letter-spacing: .08em; text-transform: uppercase; }
  .now-card > .outcome-badge { grid-column: 3; grid-row: 1; }
  .now-headline { grid-column: 2; grid-row: 1; min-width: 0; font-size: 13px; font-weight: 800; line-height: 1.3; overflow-wrap: anywhere; }
  .now-latest { grid-column: 1 / -1; min-width: 0; font-size: 11px; color: var(--text-dim); line-height: 1.4; overflow-wrap: anywhere; }
  .now-latest strong { color: var(--text); }

  .run-overview {
    flex: 0 0 auto; border: 1px solid rgba(69,239,176,0.34); border-radius: var(--panel-radius);
    background: linear-gradient(110deg, rgba(69,239,176,0.08), rgba(22,201,255,0.05), rgba(5,10,27,0.42));
    overflow: hidden;
  }
  .run-overview-head { display: flex; align-items: center; gap: 10px; padding: 9px 11px; border-bottom: 1px solid var(--border); }
  .run-overview-title { flex: 1; min-width: 0; font-size: 14px; font-weight: 800; overflow-wrap: anywhere; }
  .run-overview-grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 0 16px; padding: 2px 11px 7px; }
  .run-overview-item { min-width: 0; padding: 7px 0; border-bottom: 1px solid rgba(24,52,93,0.48); }
  .run-overview-item.full { grid-column: 1 / -1; }
  .run-overview-item:last-child { border-bottom: 0; }
  .run-overview-label { margin-bottom: 3px; color: var(--text-dim); font-size: 9px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
  .run-overview-value { font-size: 12px; line-height: 1.45; color: var(--text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .run-overview-files { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }
  .run-overview-file { border: 1px solid var(--border); border-radius: 6px; padding: 3px 6px; background: rgba(3,8,24,0.66); color: var(--text-dim); font: 10px/1.3 var(--font-mono); }
  .run-overview-link { border: 1px solid var(--accent); border-radius: 7px; padding: 5px 8px; background: rgba(22,201,255,0.09); color: var(--accent); cursor: pointer; font: 800 10px var(--font-body); }
  .run-overview-link:hover { background: rgba(22,201,255,0.16); }
  .reliability-summary { margin-top: 8px; padding: 8px 9px; border: 1px solid rgba(255,184,77,0.34); border-left: 3px solid var(--warning); border-radius: 7px; background: rgba(255,184,77,0.06); }
  .reliability-summary.safe { border-color: rgba(69,239,176,0.28); border-left-color: var(--success); background: rgba(69,239,176,0.05); }
  .reliability-status { font-size: 11px; font-weight: 800; }
  .reliability-detail { margin-top: 4px; font-size: 11px; line-height: 1.45; color: var(--text-dim); white-space: pre-wrap; overflow-wrap: anywhere; }

  .activity-card {
    flex: 1; min-height: 0; display: flex; flex-direction: column;
    border: 1px solid var(--border); border-radius: var(--panel-radius); background: rgba(8,14,34,0.58); overflow: hidden;
  }
  .activity-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 7px 10px; border-bottom: 1px solid var(--border); }
  .activity-title { font-size: 14px; font-weight: 800; }
  .activity-subtitle { font-size: 11px; color: var(--text-dim); }
  .worker-feed-container {
    padding: 10px; grid-template-columns: minmax(240px, 310px) minmax(0,1fr);
    grid-template-rows: minmax(0,1fr); grid-template-areas: "attempts viewer"; gap: 10px;
  }
  .worker-current-summary { display: none; }
  .worker-list-heading { display: none; }
  .worker-card-list { gap: 8px; }
  .worker-loop-group summary .loop-title,
  .worker-loop-group summary .loop-subtitle { white-space: normal; overflow: visible; text-overflow: clip; overflow-wrap: anywhere; }
  .output-viewer { background: rgba(3,8,24,0.78); }
  .activity-empty { flex: 1; display: grid; place-items: center; padding: 20px; color: var(--text-dim); text-align: center; font-size: 14px; line-height: 1.5; }
  .stage-artifact-links { display: flex; justify-content: center; flex-wrap: wrap; gap: 7px; margin-top: 10px; }
  .stage-artifact-link { border: 1px solid var(--border); border-radius: 7px; padding: 6px 9px; background: var(--surface-2); color: var(--text); cursor: pointer; font: 12px var(--font-body); }
  .verification-inline { flex: 0 0 auto; padding: 0 2px; }
  .verification-inline .verification-panel { margin: 0; }

  .files-drawer {
    display: none; position: absolute; inset: 0 auto 0 0; width: min(920px, 96%); z-index: 18;
    padding: 16px; background: rgba(7,12,31,0.985); border-right: 1px solid var(--border-bright);
    box-shadow: 18px 0 50px rgba(0,0,0,0.46); backdrop-filter: blur(15px);
    flex-direction: column; min-height: 0;
  }
  .files-drawer.open { display: grid; grid-template-columns: minmax(220px, 280px) minmax(0,1fr); grid-template-rows: auto minmax(0,1fr); gap: 12px; }
  .files-drawer-head { grid-column: 1 / -1; }
  .files-drawer-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
  .files-drawer-title { font-size: 16px; font-weight: 800; }
  .files-drawer-copy { margin-top: 2px; font-size: 11px; color: var(--text-dim); }
  .artifact-tree { padding: 4px 8px 4px 0; overflow-y: auto; min-height: 0; border-right: 1px solid var(--border); }
  .artifact-stage { margin-bottom: 10px; }
  .artifact-stage-label { display: flex; justify-content: space-between; gap: 10px; padding: 6px 2px; font-size: 12px; font-weight: 800; }
  .artifact-stage-label span:last-child { color: var(--text-dim); font-size: 10px; font-weight: 500; }
  .artifact-stage-files { display: flex; flex-direction: column; gap: 3px; padding-left: 12px; }
  .artifact-file {
    border: 0; background: transparent; color: var(--text-dim); text-align: left;
    padding: 7px 9px; border-radius: 7px; cursor: pointer; font: 13px var(--font-body);
  }
  .artifact-file:hover, .artifact-file.selected { color: var(--text); background: rgba(255,255,255,0.06); }
  .artifact-preview { margin-top: 0; display: none; flex: 1; }
  .files-drawer .artifact-preview { min-height: 0; margin: 0; font-size: 14px; line-height: 1.55; }
  .files-empty { color: var(--text-dim); font-size: 12px; padding: 12px 2px; }

  .history-section { flex: 0 0 auto; margin-top: 4px; }
  .history-toggle { width: 100%; display: flex; align-items: center; gap: 8px; border: 0; background: transparent; color: #78dfff; cursor: pointer; padding: 3px 0; font: 800 11px var(--font-display); text-transform: uppercase; letter-spacing: .12em; }
  .history-toggle .history-chevron { margin-left: auto; }
  .history-section:not(.open) .history-list { display: none; }
  .history-section.open .history-list { max-height: 120px; }

  .output-card-role, .output-card-summary { font-size: 12px; }
  .viewer-tab { font-size: 12px; }
  .output-viewer-content, .output-viewer-reasoning { font-size: 14px; line-height: 1.65; }
  .output-viewer-prompt { font-size: 13px; }
  .chat-message, .chat-input { font-size: 14px; }

  @media (max-width: 1050px) {
    .header h1 { font-size: 19px; }
    .header h1 .icon { width: 40px; height: 40px; }
    .workspace-label, .git-repo { display: none; }
    .workspace-widget { min-width: 0; max-width: 150px; }
    .git-widget { width: auto; }
    .header-run-selector { width: min(280px, 29vw); }
  }
  @media (max-width: 1280px) {
    .brand-name { display: none; }
    .memory-widget { grid-template-columns: minmax(96px, auto); min-width: 112px; }
    .memory-graph { display: none; }
  }
  @media (max-width: 1180px) {
    .worker-feed-container { grid-template-columns: 1fr; grid-template-rows: minmax(150px,34%) minmax(0,1fr); grid-template-areas: "attempts" "viewer"; }
  }
  @media (max-width: 1180px) and (max-height: 820px) {
    .run-overview { max-height: 46%; overflow-y: auto; overscroll-behavior: contain; }
    .activity-card { min-height: 220px; }
  }
  @media (max-width: 900px) {
    .header-run-selector { min-width: 130px; }
    .workspace-copy { display: none; }
    .workspace-widget { padding: 7px 9px; }
  }
</style>
</head>
<body>

<div class="header">
  <h1>
    <img class="icon" src="/static/devflow-logo.png" alt="DevFlow logo">
    <span class="brand-name">DevFlow Pipeline</span>
  </h1>
  <div class="header-right">
    <div class="header-run-selector" id="header-run-selector" aria-label="Active / Needs Attention"></div>
    <div class="workspace-widget no-workspace" id="workspace-widget" title="Select workspace" role="button" tabindex="0" aria-expanded="false" onclick="toggleWorkspaceDropdown(event)" onkeydown="handleWorkspaceKey(event)">
      <span class="workspace-icon">📁</span>
      <span class="workspace-copy">
        <span class="workspace-label">Workspace</span>
        <span class="workspace-name" id="workspace-name">Not set</span>
      </span>
      <span class="workspace-chevron">▾</span>
      <div class="workspace-dropdown" id="workspace-dropdown" role="dialog" aria-label="Workspace picker"></div>
    </div>
    <div class="git-widget" id="git-widget" title="Git status unavailable" role="button" tabindex="0" aria-expanded="false" onclick="toggleGitDetails(event)" onkeydown="handleGitWidgetKey(event)">
      <span class="git-icon">⑂</span>
      <span class="git-copy">
        <span class="git-repo" id="git-repo">repo</span>
        <span class="git-branch" id="git-branch">branch</span>
      </span>
      <span class="git-state" id="git-state">--</span>
    </div>
    <div class="git-popover" id="git-popover" role="dialog" aria-label="Git status details"></div>
    <span class="repo-path" id="repo-path"></span>
    <div class="memory-widget" id="memory-widget" title="Approximate macOS RAM pressure" aria-label="RAM status">
      <div class="memory-copy">
        <div class="memory-label"><span class="memory-dot"></span>RAM</div>
        <div class="memory-value" id="memory-value">-- GiB free</div>
      </div>
      <svg class="memory-graph" id="memory-graph" viewBox="0 0 78 22" preserveAspectRatio="none" aria-hidden="true">
        <path class="grid" d="M0 11 H78"></path>
        <path class="area" id="memory-area" d="M0 22 L78 22 Z"></path>
        <path class="line" id="memory-line" d=""></path>
      </svg>
    </div>
    <button class="system-widget" id="system-widget" type="button" aria-expanded="false" onclick="toggleSystemDetails()">System</button>
    <div class="system-popover" id="system-popover" role="dialog" aria-label="System status">
      <div class="system-meta">
        <span class="ui-version" title="Status board UI build">UI v4</span>
        <span class="live-indicator"><span class="live-dot"></span>LIVE</span>
      </div>
    </div>
  </div>
</div>

<div class="app-shell">
<div class="content" id="content">
  <div class="empty-state">
    <h3>Waiting for activity</h3>
    <p>No pipeline runs yet. Start a brainstorm in the chat panel to kick off the DevFlow loop.</p>
  </div>
</div>

<aside class="chat-sidebar" id="chat-sidebar">
  <div class="chat-header">
    <div class="chat-title-row">
      <span class="chat-title">Brainstorm</span>
      <select class="chat-session-select" id="chat-session-select" onchange="switchChatSession()" title="Switch session">
        <option value="">New session</option>
      </select>
    </div>
    <select class="chat-model-select" id="chat-model-select" title="Brainstorm model" onchange="persistChatModelSelection()">
      <option value="">Loading models…</option>
    </select>
  </div>
  <div class="chat-messages" id="chat-messages">
    <div class="chat-empty" id="chat-empty">
      <div class="chat-empty-icon">💬</div>
      <div>Start a brainstorm session.</div>
      <div style="font-size:11px;margin-top:4px;">Your conversation feeds directly into the DevFlow pipeline.</div>
    </div>
  </div>
  <div class="chat-input-area">
    <div class="chat-composer-row">
      <textarea class="chat-input" id="chat-input" placeholder="Type or dictate your idea…" rows="2"
        onkeydown="handleChatKey(event)" oninput="autoResizeChatInput(this)"></textarea>
      <button class="chat-mic-btn" id="chat-mic-btn" type="button" aria-label="Start dictation" aria-pressed="false" onclick="toggleChatDictation()">
        <!-- Lucide Mic icon (ISC): https://lucide.dev/icons/mic -->
        <svg viewBox="0 0 24 24" fill="none" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
          <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
          <line x1="12" x2="12" y1="19" y2="22"></line>
        </svg>
      </button>
    </div>
    <div class="chat-dictation-state" id="chat-dictation-state" role="status" aria-live="polite">Checking dictation support…</div>
    <div class="chat-send-row">
      <span class="chat-hint" id="chat-hint">Enter to send · Shift+Enter for newline</span>
      <div style="display:flex;gap:6px;">
        <button class="chat-new-btn" onclick="newChatSession()" title="Start fresh">New</button>
        <button class="chat-send-btn" id="chat-send-btn" onclick="sendChatMessage()">Send</button>
      </div>
    </div>
  </div>
</aside>
</div>

<script>
const STAGE_NAMES = ['idea','definition','spec','planning','planning_judge','assignment','build_judge','verification','human_decision','complete'];
const STAGE_SHORT = ['Idea','Def','Spec','Plan','Judge','Assign','Build','Verify','Decision','Done'];

// This page is an auto-refreshing live feed. Preserve open artifact preview,
// expanded worker loop groups, selected worker output, and scroll position.
let OPEN_ARTIFACT = null;  // { runId, fileName }
let SELECTED_OUTPUT = null; // { runId, entryId }
let USER_SELECTED_OUTPUT = false;
let OUTPUT_TABS = {}; // { entryId: 'summary'|'raw'|'prompt'|'metadata' }
let MEMORY_HISTORY = [];
let LATEST_GIT = null;
let OPEN_WORKER_GROUPS = new Set();
let CLOSED_WORKER_GROUPS = new Set();
let IS_RENDERING = false;
let FOCUSED_RUN_ID = null;
let RUN_SELECTOR_OPEN = false;
let FILES_DRAWER_OPEN = false;
let HISTORY_OPEN = false;
let SELECTED_STAGE_BY_RUN = {};
let WORKER_FEED_DATA = {};  // { runId: [entry, ...] } — JS-accessible feed data for the viewer
let IS_STREAMING = false;  // true when any focused run has a live-streaming worker
let CHAT_AWAITS_FIRST_MESSAGE = false;
try {
  OPEN_WORKER_GROUPS = new Set(JSON.parse(localStorage.getItem('devflow.openWorkerGroups') || '[]'));
} catch (_) {
  OPEN_WORKER_GROUPS = new Set();
}
try {
  CLOSED_WORKER_GROUPS = new Set(JSON.parse(localStorage.getItem('devflow.closedWorkerGroups') || '[]'));
} catch (_) {
  CLOSED_WORKER_GROUPS = new Set();
}
try {
  FOCUSED_RUN_ID = localStorage.getItem('devflow.focusedRunId') || null;
} catch (_) {
  FOCUSED_RUN_ID = null;
}
try {
  FILES_DRAWER_OPEN = localStorage.getItem('devflow.filesDrawerOpen') === 'true';
} catch (_) {
  FILES_DRAWER_OPEN = false;
}
try {
  HISTORY_OPEN = localStorage.getItem('devflow.historyOpen') === 'true';
} catch (_) {
  HISTORY_OPEN = false;
}
try {
  SELECTED_STAGE_BY_RUN = JSON.parse(localStorage.getItem('devflow.selectedStages') || '{}');
} catch (_) {
  SELECTED_STAGE_BY_RUN = {};
}

function saveOpenWorkerGroups() {
  try { localStorage.setItem('devflow.openWorkerGroups', JSON.stringify([...OPEN_WORKER_GROUPS])); } catch (_) {}
}

function saveClosedWorkerGroups() {
  try { localStorage.setItem('devflow.closedWorkerGroups', JSON.stringify([...CLOSED_WORKER_GROUPS])); } catch (_) {}
}

function hasWorkerGroupPreference(groupId) {
  return OPEN_WORKER_GROUPS.has(groupId) || CLOSED_WORKER_GROUPS.has(groupId);
}

function setFocusedRun(runId) {
  FOCUSED_RUN_ID = runId;
  try {
    if (runId) localStorage.setItem('devflow.focusedRunId', runId);
    else localStorage.removeItem('devflow.focusedRunId');
  } catch (_) {}
}

function focusRun(runId) {
  CHAT_AWAITS_FIRST_MESSAGE = false;
  setFocusedRun(runId);
  refresh();
}

function toggleRunSelector() {
  RUN_SELECTOR_OPEN = !RUN_SELECTOR_OPEN;
  const el = document.getElementById('run-selector');
  if (el) el.classList.toggle('open', RUN_SELECTOR_OPEN);
}

function closeRunSelector() {
  RUN_SELECTOR_OPEN = false;
  const el = document.getElementById('run-selector');
  if (el) el.classList.remove('open');
}

function selectRunFromDropdown(runId) {
  closeRunSelector();
  focusRun(runId);
}

function toggleHistory() {
  HISTORY_OPEN = !HISTORY_OPEN;
  try { localStorage.setItem('devflow.historyOpen', String(HISTORY_OPEN)); } catch (_) {}
  const section = document.querySelector('.history-section');
  if (section) section.classList.toggle('open', HISTORY_OPEN);
  const button = section?.querySelector('.history-toggle');
  if (button) button.setAttribute('aria-expanded', String(HISTORY_OPEN));
}

function selectActivityStage(runId, stage) {
  SELECTED_STAGE_BY_RUN[runId] = stage;
  try { localStorage.setItem('devflow.selectedStages', JSON.stringify(SELECTED_STAGE_BY_RUN)); } catch (_) {}
  USER_SELECTED_OUTPUT = false;
  SELECTED_OUTPUT = null;
  refresh();
}

function setFilesDrawerOpen(open) {
  FILES_DRAWER_OPEN = Boolean(open);
  try { localStorage.setItem('devflow.filesDrawerOpen', String(FILES_DRAWER_OPEN)); } catch (_) {}
  document.querySelectorAll('.files-drawer').forEach(drawer => drawer.classList.toggle('open', FILES_DRAWER_OPEN));
  document.querySelectorAll('.files-button').forEach(button => button.setAttribute('aria-expanded', String(FILES_DRAWER_OPEN)));
}

function toggleFilesDrawer() {
  setFilesDrawerOpen(!FILES_DRAWER_OPEN);
}

function closeFilesDrawer() {
  setFilesDrawerOpen(false);
}

function toggleSystemDetails() {
  const widget = document.getElementById('system-widget');
  const popover = document.getElementById('system-popover');
  if (!widget || !popover) return;
  const open = !popover.classList.contains('open');
  popover.classList.toggle('open', open);
  widget.classList.toggle('open', open);
  widget.setAttribute('aria-expanded', String(open));
}

function closeSystemDetails() {
  const widget = document.getElementById('system-widget');
  const popover = document.getElementById('system-popover');
  if (!widget || !popover) return;
  popover.classList.remove('open');
  widget.classList.remove('open');
  widget.setAttribute('aria-expanded', 'false');
}

async function refresh() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    const scrollState = captureScrollState();
    render(data);
    if (OPEN_ARTIFACT) {
      // Rehydrate the selected preview without overriding the operator's
      // explicit drawer choice. A prior Close must remain closed.
      await showArtifact(
        OPEN_ARTIFACT.runId,
        OPEN_ARTIFACT.fileName,
        /*silent*/ true,
        /*openDrawer*/ false,
      );
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
  LATEST_GIT = data || null;
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
    renderGitDetails();
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
  renderGitDetails();
}

function toggleGitDetails(event) {
  if (event) event.stopPropagation();
  const popover = document.getElementById('git-popover');
  const widget = document.getElementById('git-widget');
  if (!popover || !widget) return;
  const opening = !popover.classList.contains('open');
  popover.classList.toggle('open', opening);
  widget.classList.toggle('open', opening);
  widget.setAttribute('aria-expanded', opening ? 'true' : 'false');
  if (opening) renderGitDetails();
}

function closeGitDetails() {
  const popover = document.getElementById('git-popover');
  const widget = document.getElementById('git-widget');
  if (!popover || !widget) return;
  popover.classList.remove('open');
  widget.classList.remove('open');
  widget.setAttribute('aria-expanded', 'false');
}

function handleGitWidgetKey(event) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    toggleGitDetails(event);
  }
}

function renderGitDetails() {
  const popover = document.getElementById('git-popover');
  if (!popover || !popover.classList.contains('open')) return;
  const data = LATEST_GIT;
  if (!data || data.available === false) {
    popover.innerHTML = `<div class="git-empty">Git status is unavailable.</div>`;
    return;
  }
  const changes = data.changes || [];
  const rows = changes.length ? changes.map(change => `
    <div class="git-change-row">
      <span class="git-change-label ${escapeHtml(change.tone || '')}">${escapeHtml(change.label || 'changed')}</span>
      <span class="git-change-path" title="${escapeHtml(change.path || '')}">${escapeHtml(change.path || '')}</span>
      <span class="git-change-code">${escapeHtml(`${change.index || ' '} ${change.worktree || ' '}`)}</span>
    </div>`).join('') : '<div class="git-empty">No working tree changes. This checkout is clean.</div>';
  popover.innerHTML = `
    <div class="git-popover-head">
      <div>
        <div class="git-popover-title">${escapeHtml(data.repo_name || 'Repository')}</div>
        <div class="git-popover-branch">${escapeHtml(data.branch || 'branch')} · ${escapeHtml(data.commit || 'unknown')}</div>
        <div class="git-popover-meta">
          <span class="git-meta-pill">${escapeHtml(data.label || data.state || 'status')}</span>
          <span class="git-meta-pill">${data.staged || 0} staged</span>
          <span class="git-meta-pill">${data.unstaged || 0} unstaged</span>
          <span class="git-meta-pill">${data.untracked || 0} untracked</span>
          <span class="git-meta-pill">${data.ahead || 0} ahead · ${data.behind || 0} behind</span>
        </div>
      </div>
      <button class="git-popover-close" onclick="closeGitDetails()" aria-label="Close Git details">×</button>
    </div>
    <div class="git-change-list">${rows}</div>`;
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
  const workerListScroll = {};
  const viewerPanelScroll = {};
  const runOverviewScroll = {};
  document.querySelectorAll('.worker-feed-container').forEach(container => {
    if (!container.id) return;
    const list = container.querySelector('.worker-card-list');
    const activePanel = container.querySelector('.viewer-panel.active');
    if (list) workerListScroll[container.id] = list.scrollTop;
    if (activePanel) viewerPanelScroll[container.id] = activePanel.scrollTop;
  });
  document.querySelectorAll('.worker-loop-group[data-group-id]').forEach(group => {
    const groupId = group.dataset.groupId;
    if (!groupId) return;
    if (group.open) {
      OPEN_WORKER_GROUPS.add(groupId);
      CLOSED_WORKER_GROUPS.delete(groupId);
    } else if (hasWorkerGroupPreference(groupId)) {
      OPEN_WORKER_GROUPS.delete(groupId);
      CLOSED_WORKER_GROUPS.add(groupId);
    }
  });
  document.querySelectorAll('.run-overview[id]').forEach(overview => {
    runOverviewScroll[overview.id] = overview.scrollTop;
  });
  saveOpenWorkerGroups();
  saveClosedWorkerGroups();
  return {
    pageX: window.scrollX,
    pageY: window.scrollY,
    artifact: OPEN_ARTIFACT ? {
      runId: OPEN_ARTIFACT.runId,
      scrollTop: document.getElementById('preview-' + OPEN_ARTIFACT.runId)?.scrollTop || 0,
    } : null,
    workerListScroll,
    viewerPanelScroll,
    runOverviewScroll,
  };
}

function restoreScrollState(state) {
  if (!state) return;
  const apply = () => {
    if (state.artifact) {
      const preview = document.getElementById('preview-' + state.artifact.runId);
      if (preview) preview.scrollTop = state.artifact.scrollTop;
    }
    Object.entries(state.workerListScroll || {}).forEach(([containerId, scrollTop]) => {
      const container = document.getElementById(containerId);
      const list = container?.querySelector('.worker-card-list');
      if (list) list.scrollTop = scrollTop;
    });
    Object.entries(state.viewerPanelScroll || {}).forEach(([containerId, scrollTop]) => {
      const panel = document.getElementById(containerId)?.querySelector('.viewer-panel.active');
      if (panel) panel.scrollTop = scrollTop;
    });
    Object.entries(state.runOverviewScroll || {}).forEach(([overviewId, scrollTop]) => {
      const overview = document.getElementById(overviewId);
      if (overview) overview.scrollTop = scrollTop;
    });
    window.scrollTo(state.pageX || 0, state.pageY || 0);
  };
  requestAnimationFrame(() => {
    apply();
    setTimeout(apply, 0);
  });
}

function statusRunsForChatSession(runs) {
  return CHAT_AWAITS_FIRST_MESSAGE ? [] : runs;
}

function render(data) {
  IS_RENDERING = true;
  const repoPath = document.getElementById('repo-path');
  if (repoPath) repoPath.textContent = data.repo || '';
  const el = document.getElementById('content');
  const runs = statusRunsForChatSession(data.runs || []);
  if (runs.length === 0) {
    document.getElementById('header-run-selector').innerHTML = '';
    IS_STREAMING = false;
    const message = CHAT_AWAITS_FIRST_MESSAGE
      ? '<h3>New brainstorm</h3><p>Your new project will appear here after your first message.</p>'
      : '<h3>Waiting for activity</h3><p>No pipeline runs yet. Start a brainstorm in the chat panel to kick off the DevFlow loop.</p>';
    el.innerHTML = `<div class="empty-state">${message}</div>`;
    return;
  }

  // Detect whether any focused run has a live-streaming worker so the
  // adaptive refresh loop can poll faster.
  IS_STREAMING = runs.some(r =>
    (r.worker_feed || []).some(e => e.event === 'streaming')
  );

  const liveOrNeedsAttention = runs.filter(r => r.stage !== 'complete');
  const completed = runs.filter(r => r.stage === 'complete');
  const focusedCompleted = completed.find(r => r.run_id === FOCUSED_RUN_ID);
  const active = focusedCompleted
    ? [...liveOrNeedsAttention, focusedCompleted]
    : (liveOrNeedsAttention.length ? liveOrNeedsAttention : []);
  const activeIds = new Set(active.map(r => r.run_id));
  const history = runs.filter(r => !activeIds.has(r.run_id));

  let html = '';
  if (active.length) {
    const orderedActive = [...active].sort((a, b) =>
      (b.run_id || '').localeCompare(a.run_id || '')
    );
    const focusedRun = active.find(r => r.run_id === FOCUSED_RUN_ID) || orderedActive[0];
    if (focusedRun && !FOCUSED_RUN_ID) FOCUSED_RUN_ID = focusedRun.run_id;
    document.getElementById('header-run-selector').innerHTML = renderRunQueue(orderedActive, focusedRun?.run_id || '');
    if (focusedRun) html += renderActive(focusedRun);
  } else {
    document.getElementById('header-run-selector').innerHTML = '';
    html += `<div class="no-active"><h3>No active pipeline</h3><p>All runs are complete. Click a history row below to inspect its files, activity, and evidence.</p></div>`;
  }
  if (history.length) {
    html += `<section class="history-section ${HISTORY_OPEN ? 'open' : ''}">
      <button type="button" class="history-toggle" aria-expanded="${HISTORY_OPEN}" onclick="toggleHistory()">
        <span>History (${history.length})</span><span class="history-chevron">${HISTORY_OPEN ? '▾' : '▸'}</span>
      </button>
      <div class="history-list">${history.map(r => renderHistoryRow(r)).join('')}</div>
    </section>`;
  }
  el.innerHTML = html;
  setFilesDrawerOpen(FILES_DRAWER_OPEN);
  requestAnimationFrame(() => {
    IS_RENDERING = false;
    // After each render, auto-select the most relevant output card so the
    // viewer pane shows useful content without requiring a manual click.
    el.querySelectorAll('.output-viewer').forEach(viewer => {
      const runId = viewer.dataset.runId;
      let targetEntryId = null;
      if (USER_SELECTED_OUTPUT && SELECTED_OUTPUT && SELECTED_OUTPUT.runId === runId) {
        targetEntryId = SELECTED_OUTPUT.entryId;
      } else {
        targetEntryId = viewer.dataset.defaultEntryId;
      }
      if (targetEntryId) {
        const card = el.querySelector(`.output-card[data-entry-id="${targetEntryId}"]`);
        if (card) selectWorkerOutput(card, runId, { preserveUserSelection: !USER_SELECTED_OUTPUT });
      }
    });
  });
}

function renderRunQueue(runs, focusedRunId) {
  const focused = runs.find(r => r.run_id === focusedRunId) || runs[0] || {};
  const triggerStatus = focused.execution_status || 'idle';
  const triggerCurrent = focused.worker_projection?.current;
  const triggerOutcome = triggerCurrent?.outcome || triggerStatus;
  const triggerDisplayStatus = triggerStatus === 'idle' && ['failed', 'needs_attention'].includes(triggerOutcome) ? triggerOutcome : triggerStatus;
  const trigger = `<button type="button" class="run-selector-trigger ${escapeHtml(triggerStatus)}" onclick="toggleRunSelector()" aria-haspopup="listbox" aria-expanded="${RUN_SELECTOR_OPEN}">
    <span class="run-signal"></span>
    <span class="run-selector-intent">${escapeHtml(focused.intent || focused.run_id || 'Select a run')}</span>
    <span class="run-selector-meta">${escapeHtml(focused.run_id || '')}</span>
    <span class="run-selector-stage">${escapeHtml(focused.stage_label || focused.stage || '')}</span>
    <span class="run-selector-status">${escapeHtml(triggerDisplayStatus.replace('_', ' '))}</span>
    <span class="run-selector-chevron">▾</span>
  </button>`;
  const items = runs.map(r => {
    const status = r.execution_status || 'idle';
    const current = r.worker_projection?.current;
    const outcome = current?.outcome || status;
    const displayStatus = status === 'idle' && ['failed', 'needs_attention'].includes(outcome) ? outcome : status;
    return `<button type="button" role="option" class="run-selector-item ${escapeHtml(status)} ${r.run_id === focusedRunId ? 'selected' : ''}" onclick="selectRunFromDropdown('${escapeHtml(r.run_id)}')">
      <span class="run-signal"></span>
      <span class="run-selector-intent">${escapeHtml(r.intent || r.run_id)}</span>
      <span class="run-selector-meta">${escapeHtml(r.run_id)}</span>
      <span class="run-selector-stage">${escapeHtml(r.stage_label || r.stage)}</span>
      <span class="run-selector-status">${escapeHtml(displayStatus.replace('_', ' '))}</span>
    </button>`;
  }).join('');
  return `<div class="run-selector ${RUN_SELECTOR_OPEN ? 'open' : ''}" id="run-selector">${trigger}<div class="run-selector-dropdown" role="listbox" aria-label="Active pipeline runs">${items}</div></div>`;
}

function workerLoopKind(entry) {
  const role = entry.role || '';
  if (['builder', 'judge', 'build_judge_loop'].includes(role)) return 'build';
  if (['planner', 'planning_judge', 'planning_judge_report', 'frontier_bounded_packet_review', 'frontier_orchestrator_replan_gate'].includes(role)) return 'planning';
  if (['operator_control', 'frontier_orchestrator_control', 'packet_1_dispatch'].includes(role)) return 'operator';
  return 'orchestrator';
}

function workerLoopLabel(kind) {
  return {
    build: 'Builder/Judge loop',
    planning: 'Planning loop',
    operator: 'Operator gates',
    orchestrator: 'Orchestrator/control',
  }[kind] || 'Worker loop';
}

function outcomeText(outcome) {
  return {
    failed: 'Failed',
    stalled: 'Stalled',
    cancelled: 'Cancelled',
    needs_attention: 'Needs attention',
    running: 'Running',
    passed: 'Passed',
    completed: 'Finished',
    neutral: 'Recorded',
  }[outcome] || 'Recorded';
}

function humanRole(role) {
  const text = String(role || 'worker').replaceAll('_', ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function stageWorkerKind(stage) {
  if (stage === 'build_judge' || stage === 'verification') return 'build';
  if (stage === 'planning' || stage === 'planning_judge') return 'planning';
  if (stage === 'assignment') return 'operator';
  return 'orchestrator';
}

function groupWorkerLoops(entries) {
  const groups = [];
  let currentByKind = {};
  entries.forEach((entry, index) => {
    const enriched = { ...entry, feedIndex: index, loopKind: workerLoopKind(entry) };
    const role = enriched.role || '';
    const event = enriched.event || '';
    const startsLoop = (role === 'planner' && event === 'started') || (role === 'builder' && event === 'started');
    if (!currentByKind[enriched.loopKind] || startsLoop) {
      const kindCount = groups.filter(g => g.kind === enriched.loopKind).length + 1;
      currentByKind[enriched.loopKind] = { number: groups.length + 1, kindNumber: kindCount, kind: enriched.loopKind, entries: [] };
      groups.push(currentByKind[enriched.loopKind]);
    }
    currentByKind[enriched.loopKind].entries.push(enriched);
  });
  return groups;
}

function workerGroupSummary(group, isCurrentGroup) {
  const roles = [...new Set(group.entries.map(e => e.role || 'worker'))].join(' → ');
  const first = group.entries[0] || {};
  const last = group.entries[group.entries.length - 1] || {};
  return {
    title: `${isCurrentGroup ? 'Current ' : ''}${workerLoopLabel(group.kind)} ${group.kindNumber}`,
    subtitle: `${formatTime(first.timestamp)} → ${formatTime(last.timestamp)} · ${group.entries.length} outputs · ${roles}`,
  };
}

function preferredWorkerRolesForStage(stage) {
  if (stage === 'build_judge') return ['judge', 'builder'];
  if (stage === 'verification') return ['verification', 'test-runner', 'judge', 'builder'];
  if (stage === 'planning_judge' || stage === 'planning') return ['planning_judge', 'planning_judge_report', 'planner'];
  if (stage === 'assignment') return ['frontier_bounded_packet_review', 'frontier_orchestrator_control', 'packet_1_dispatch'];
  return [];
}

function onWorkerGroupToggle(detailsEl) {
  if (IS_RENDERING) return;
  const groupId = detailsEl?.dataset?.groupId;
  if (!groupId) return;
  if (detailsEl.open) {
    OPEN_WORKER_GROUPS.add(groupId);
    CLOSED_WORKER_GROUPS.delete(groupId);
  } else {
    OPEN_WORKER_GROUPS.delete(groupId);
    CLOSED_WORKER_GROUPS.add(groupId);
  }
  saveOpenWorkerGroups();
  saveClosedWorkerGroups();
}

function artifactStage(fileName) {
  const name = String(fileName || '').toLowerCase();
  if (name.includes('brainstorm') || name.includes('intent') || name === 'artifacts.json') return 'Idea';
  if (name.includes('spec')) return 'Specification';
  if (name.includes('plan') || name.includes('packet') || name.includes('assignment')) return 'Plan';
  if (name.includes('build') || name.includes('diff') || name.includes('manifest') || name.includes('workspace')) return 'Build';
  if (name.includes('verif') || name.includes('receipt') || name.includes('test')) return 'Verification';
  return 'Evidence';
}

function renderArtifactTree(runId, artifacts) {
  const order = ['Idea', 'Specification', 'Plan', 'Build', 'Verification', 'Evidence'];
  const groups = Object.fromEntries(order.map(stage => [stage, []]));
  (artifacts || []).forEach(fileName => groups[artifactStage(fileName)].push(fileName));
  return order.filter(stage => groups[stage].length).map(stage => {
    const files = groups[stage].map(fileName => {
      const selected = OPEN_ARTIFACT?.runId === runId && OPEN_ARTIFACT?.fileName === fileName;
      return `<button type="button" class="artifact-file ${selected ? 'selected' : ''}" onclick="showArtifact('${escapeHtml(runId)}','${escapeHtml(fileName)}')">${escapeHtml(fileName)}</button>`;
    }).join('');
    return `<div class="artifact-stage">
      <div class="artifact-stage-label"><span>${stage}</span><span>${groups[stage].length} file${groups[stage].length === 1 ? '' : 's'}</span></div>
      <div class="artifact-stage-files">${files}</div>
    </div>`;
  }).join('');
}

function stageArtifactCandidates(stage, artifacts) {
  const patterns = {
    idea: /brainstorm|intent/i,
    definition: /orient|classification|readiness|intent-summary/i,
    spec: /(^|[-_])spec|spec\.md/i,
    planning: /plan\.md|build-packets|packet/i,
    planning_judge: /planning-judge|review/i,
    assignment: /assignment|packet|execution-control/i,
    build_judge: /build|diff|manifest|judge-decision|workspace/i,
    verification: /verif|receipt|test-result/i,
    human_decision: /human-decision|acceptance|full-pipeline/i,
    complete: /full-pipeline|human-decision|verification|receipt/i,
  };
  const pattern = patterns[stage];
  return pattern ? (artifacts || []).filter(name => pattern.test(name)).slice(0, 8) : [];
}

function renderActive(r) {
  const rawStageIdx = STAGE_NAMES.indexOf(r.stage);
  const stageIdx = rawStageIdx >= 0 ? rawStageIdx : STAGE_NAMES.indexOf('human_decision');
  const selectedStage = SELECTED_STAGE_BY_RUN[r.run_id] || (rawStageIdx >= 0 ? r.stage : 'human_decision');
  const segments = STAGE_NAMES.map((s, i) => {
    let cls = '';
    if (r.stage === 'blocked') cls = i <= stageIdx ? 'blocked' : '';
    else if (i < stageIdx) cls = 'done';
    else if (i === stageIdx) cls = 'current';
    const selected = s === selectedStage;
    return `<button type="button" class="stage-control ${cls} ${selected ? 'selected' : ''}" aria-pressed="${selected}" onclick="selectActivityStage('${escapeHtml(r.run_id)}','${s}')">
      <span class="progress-segment ${cls}"></span><span>${STAGE_SHORT[i]}</span>
    </button>`;
  }).join('');

  // The server owns worker semantics. The browser renders the projection and
  // keeps the append-only evidence available behind explicit detail tabs.
  const projection = r.worker_projection || { entries: [], loops: [], current: null };
  const chronologicalEntries = projection.entries || [];
  const stageEntries = selectedStage === 'complete'
    ? chronologicalEntries
    : chronologicalEntries.filter(entry => (entry.stages || []).includes(selectedStage));
  const matchingGroups = (projection.loops || []).map(group => ({
    ...group,
    entries: (group.entries || []).filter(entry => selectedStage === 'complete' || (entry.stages || []).includes(selectedStage)),
  })).filter(group => group.entries.length);
  const latestGroupId = matchingGroups.length ? matchingGroups[matchingGroups.length - 1].loop_id : '';
  const activeGroupId = projection.current?.loop_id || '';
  matchingGroups.forEach(group => {
    group.is_latest = group.loop_id === latestGroupId;
    group.is_current = group.loop_id === activeGroupId;
    group.event_count = group.entries.length;
  });
  const displayGroups = matchingGroups.slice().reverse();
  const currentLoop = matchingGroups.length ? matchingGroups[matchingGroups.length - 1] : null;
  const viewerId = `viewer-${r.run_id}`;
  const renderOutputCard = (f) => {
    const role = f.role || 'worker';
    const avatarClass = ['builder','judge','planner','planning_judge'].includes(role) ? role : 'default';
    const avatarText = role.slice(0,2).toUpperCase();
    const outcome = f.outcome || 'neutral';
    const isStreaming = f.event === 'streaming';
    const cardClass = isStreaming ? 'output-card streaming' : 'output-card';
    const summaryText = isStreaming ? (f.content ? f.content.slice(-80) + (f.content.length > 80 ? '…' : '') : 'Generating…') : (f.summary || f.event || 'Worker evidence');
    const stateText = isStreaming ? 'LIVE' : (f.event === 'started' && outcome === 'neutral' ? 'Started' : outcomeText(outcome));
    return `<button type="button" class="${cardClass}" data-entry-id="${escapeHtml(f.entry_id)}" data-run-id="${escapeHtml(r.run_id)}" aria-selected="false" aria-controls="${escapeHtml(viewerId)}">
      <span class="output-avatar ${avatarClass}">${avatarText}</span>
      <span class="output-card-role">${escapeHtml(role)}${isStreaming ? '<span class="card-live-dot"></span>' : ''}</span>
      <span class="output-card-summary">${escapeHtml(summaryText)}</span>
      <span class="output-card-time">${formatTime(f.timestamp)}</span>
      <span class="outcome-badge output-card-outcome ${escapeHtml(outcome)}">${escapeHtml(stateText)}</span>
    </button>`;
  };
  const latestGroups = displayGroups.filter(g => Boolean(g.is_latest));
  const previousGroups = displayGroups.filter(g => !g.is_latest);
  const renderLoopGroup = (group) => {
    const groupId = group.loop_id;
    const isCurrentLoop = Boolean(group.is_current);
    const isLatestLoop = Boolean(group.is_latest);
    const isOpen = OPEN_WORKER_GROUPS.has(groupId) || (!hasWorkerGroupPreference(groupId) && isLatestLoop);
    const titlePrefix = isCurrentLoop ? 'Current ' : (isLatestLoop ? 'Latest ' : '');
    const title = `${titlePrefix}${group.label} · Attempt ${group.attempt}`;
    const subtitle = `${formatTime(group.started_at)} → ${formatTime(group.ended_at)} · ${group.event_count} step${group.event_count === 1 ? '' : 's'}`;
    const outcome = group.outcome || 'neutral';
    return `<details class="worker-loop-group ${isCurrentLoop ? 'current-loop' : (isLatestLoop ? 'latest-loop' : '')} ${escapeHtml(group.category)}" data-group-id="${escapeHtml(groupId)}" ${isOpen ? 'open' : ''} ontoggle="onWorkerGroupToggle(this)">
      <summary><span class="loop-title">${escapeHtml(title)}</span><span class="loop-subtitle">${escapeHtml(subtitle)}</span><span class="outcome-badge loop-outcome ${escapeHtml(outcome)}">${escapeHtml(outcomeText(outcome))}</span></summary>
      <div class="worker-loop-items">
        ${(group.entries || []).slice().reverse().map(renderOutputCard).join('')}
      </div>
    </details>`;
  };
  const currentHtml = latestGroups.map(renderLoopGroup).join('');
  const previousCount = previousGroups.length;
  const previousFailed = previousGroups.filter(g => (g.outcome || '') === 'failed').length;
  const previousHtml = previousCount ? `<details class="worker-loop-group previous-loops" id="previous-loops-${escapeHtml(r.run_id)}" data-group-id="previous-loops-${escapeHtml(r.run_id)}" ${OPEN_WORKER_GROUPS.has('previous-loops-' + r.run_id) ? 'open' : ''} ontoggle="onWorkerGroupToggle(this)">
      <summary><span class="loop-title">Previous loops</span><span class="loop-subtitle">${previousCount} previous attempt${previousCount === 1 ? '' : 's'}${previousFailed ? ` · ${previousFailed} failed` : ''}</span>${previousFailed ? '<span class="outcome-badge loop-outcome failed">history</span>' : ''}</summary>
      <div class="worker-loop-items">
        ${previousGroups.map(renderLoopGroup).join('')}
      </div>
    </details>` : '';
  const cardListHtml = displayGroups.length ? `<div class="worker-card-list">
    <div class="worker-list-heading">Attempts &amp; decisions</div>
    ${currentHtml}${previousHtml}
  </div>` : '<span style="color:var(--text-dim);font-size:13px">No model output yet</span>';
  const currentEntries = currentLoop?.entries || [];
  // When a worker is actively streaming, auto-select its live output so the
  // operator sees content in real-time without manual clicking. Otherwise fall
  // back to the latest entry in the current loop.
  const streamingEntry = currentEntries.find(e => e.event === 'streaming');
  const defaultEntryId = streamingEntry?.entry_id
    || (currentEntries.length ? currentEntries[currentEntries.length - 1].entry_id : '')
    || (stageEntries.at(-1)?.entry_id || '');
  const viewerHtml = `<div class="output-viewer" id="${escapeHtml(viewerId)}" data-run-id="${escapeHtml(r.run_id)}" data-default-entry-id="${escapeHtml(defaultEntryId)}" aria-label="Worker evidence">
    <div class="output-viewer-content" style="color:var(--text-dim)">Select an output from the list to view its content.</div>
  </div>`;
  WORKER_FEED_DATA[r.run_id] = chronologicalEntries;
  const currentOutcome = currentLoop?.outcome || 'neutral';
  const currentSummaryHtml = currentLoop ? `<section class="worker-current-summary ${escapeHtml(currentOutcome)}" aria-label="Current loop outcome">
    <div class="worker-current-kicker">Current loop outcome</div>
    <span class="outcome-badge ${escapeHtml(currentOutcome)}">${escapeHtml(outcomeText(currentOutcome))}</span>
    <div class="worker-current-headline">${escapeHtml(currentLoop.summary || currentLoop.label)}</div>
    <div class="worker-current-next"><strong>Next safe action:</strong> ${escapeHtml(currentLoop.next_safe_action || 'Awaiting the next orchestrator decision.')}</div>
  </section>` : `<section class="worker-current-summary neutral" aria-label="Current loop outcome"><div class="worker-current-headline">No worker outcome yet</div><div class="worker-current-next">Worker evidence will appear here when the loop starts.</div></section>`;
  const feedHtml = displayGroups.length ? `${currentSummaryHtml}${cardListHtml}${viewerHtml}` : '';
  const stageArtifacts = stageArtifactCandidates(selectedStage, r.artifacts || []);
  const stagePosition = STAGE_NAMES.indexOf(selectedStage);
  const stageStatus = stagePosition < stageIdx ? 'completed' : stagePosition === stageIdx ? (r.execution_status || 'current') : 'upcoming';
  const stageEmptyHtml = `<div class="activity-empty"><div>
    <strong>No model call was recorded for ${escapeHtml(STAGE_SHORT[Math.max(0, stagePosition)] || selectedStage)}.</strong><br>
    This stage is ${escapeHtml(stageStatus)}. Persisted stage files remain available below.
    ${stageArtifacts.length ? `<div class="stage-artifact-links">${stageArtifacts.map(fileName => `<button type="button" class="stage-artifact-link" onclick="showArtifact('${escapeHtml(r.run_id)}','${escapeHtml(fileName)}')">${escapeHtml(fileName)}</button>`).join('')}</div>` : ''}
  </div></div>`;

  const receipts = (r.receipts || []).map(v => {
    const cls = v.passed === true ? 'receipt-pass' : v.passed === false ? 'receipt-fail' : '';
    const icon = v.passed === true ? '✓' : v.passed === false ? '✗' : '•';
    return `<div class="receipt-row ${cls}">${icon} ${escapeHtml(String(v.verifier || 'verifier'))} — ${escapeHtml(String(v.status || 'unknown'))}</div>`;
  }).join('');
  const receiptsHtml = receipts || '';

  const artifactTreeHtml = renderArtifactTree(r.run_id, r.artifacts || []);
  const preferredCodeArtifact = (r.artifacts || []).find(name => name === 'build-diff.patch')
    || (r.artifacts || []).find(name => /build.*diff|\.patch$/i.test(name))
    || (r.artifacts || []).find(name => /build-manifest/i.test(name))
    || '';
  const viewCodeButton = preferredCodeArtifact
    ? `<button type="button" class="view-code-button" onclick="showArtifact('${escapeHtml(r.run_id)}','${escapeHtml(preferredCodeArtifact)}')">View code</button>`
    : '';
  const operatorControls = renderOperatorControls(r);
  const loopComplete = r.stage === 'complete';
  const nowOutcome = loopComplete ? 'passed' : (currentLoop?.outcome || r.execution_status || 'neutral');
  const nowHeadline = loopComplete ? 'Human decision accepted; the loop is complete.' : (currentLoop?.summary || (
    r.stage === 'idea'
      ? 'The brainstorm is waiting for the next conversation step.'
      : `DevFlow is ready to continue the ${r.stage_label || r.stage} stage.`
  ));
  const nextSafeAction = loopComplete ? 'No action required. Start the next bounded iteration when ready.' : (currentLoop?.next_safe_action || (
    r.stage === 'idea'
      ? 'Continue the brainstorm until the idea is defined enough to produce a spec.'
      : 'Await the next orchestrator decision.'
  ));
  const overview = r.run_overview || {};
  const overviewFiles = (overview.files || []).map(path => `<span class="run-overview-file">${escapeHtml(path)}</span>`).join('');
  const overviewCodeArtifact = overview.code_artifact || preferredCodeArtifact;
  const overviewEvidenceArtifact = (r.artifacts || []).includes(overview.evidence_artifact) ? overview.evidence_artifact : '';
  const reliability = overview.reliability || null;
  const reliabilityArtifact = reliability && (r.artifacts || []).includes(reliability.artifact) ? reliability.artifact : '';
  const reliabilityHtml = reliability ? `<div class="reliability-summary ${reliability.safe ? 'safe' : ''}">
    <div class="reliability-status">Reliability: ${reliability.safe ? 'safe' : 'action required'} · ${escapeHtml(reliability.action || 'unknown action')}</div>
    ${(reliability.breached_metrics || []).length ? `<div class="reliability-detail"><strong>Breached metrics / thresholds</strong>\n${escapeHtml(reliability.breached_metrics.join('\n'))}</div>` : ''}
    ${(reliability.breaches || []).length ? `<div class="reliability-detail"><strong>Breaches</strong>\n${escapeHtml(reliability.breaches.join('\n'))}</div>` : ''}
    ${(reliability.recovery_actions || []).length ? `<div class="reliability-detail"><strong>Recovery / rollback</strong>\n${escapeHtml(reliability.recovery_actions.join('\n'))}</div>` : ''}
    ${reliabilityArtifact ? `<button type="button" class="run-overview-link" onclick="showArtifact('${escapeHtml(r.run_id)}','${escapeHtml(reliabilityArtifact)}')">Open reliability report</button>` : ''}
  </div>` : '';
  const completedOverviewHtml = `<section class="run-overview" id="run-overview-${escapeHtml(r.run_id)}" aria-label="Completed change overview">
    <div class="run-overview-head"><div class="run-overview-title">${escapeHtml(overview.product || r.intent || 'Completed change')}</div><span class="outcome-badge passed">Complete</span></div>
    <div class="run-overview-grid">
      <div class="run-overview-item full"><div class="run-overview-label">Product / change</div><div class="run-overview-value">${escapeHtml(overview.product || r.intent || 'No product intent was recorded.')}</div></div>
      <div class="run-overview-item full"><div class="run-overview-label">Why it was built</div><div class="run-overview-value">${escapeHtml(overview.why || 'No separate product rationale was recorded.')}</div></div>
      <div class="run-overview-item full"><div class="run-overview-label">Scope</div><div class="run-overview-value">${escapeHtml(overview.scope || 'No specification was recorded.')}</div></div>
      <div class="run-overview-item full"><div class="run-overview-label">Files &amp; code</div><div class="run-overview-files">${overviewFiles || '<span class="run-overview-value">No changed files were recorded.</span>'}${overviewCodeArtifact ? `<button type="button" class="run-overview-link" onclick="showArtifact('${escapeHtml(r.run_id)}','${escapeHtml(overviewCodeArtifact)}')">Open code diff</button>` : ''}</div></div>
      <div class="run-overview-item"><div class="run-overview-label">Result</div><div class="run-overview-value">${escapeHtml(overview.result || 'No final result was recorded.')}</div></div>
      <div class="run-overview-item"><div class="run-overview-label">Evidence</div><div class="run-overview-value">${escapeHtml(overview.evidence || 'No verification evidence was recorded.')}</div>${overviewEvidenceArtifact ? `<button type="button" class="run-overview-link" onclick="showArtifact('${escapeHtml(r.run_id)}','${escapeHtml(overviewEvidenceArtifact)}')">Open verification</button>` : ''}${reliabilityHtml}</div>
      <div class="run-overview-item full"><div class="run-overview-label">Next</div><div class="run-overview-value">${escapeHtml(overview.next || nextSafeAction)}</div></div>
    </div>
  </section>`;
  const activityTitle = loopComplete ? 'Detailed work history' : `${STAGE_SHORT[Math.max(0, STAGE_NAMES.indexOf(selectedStage))] || selectedStage} activity`;
  const activitySubtitle = loopComplete
    ? 'Open a stage or worker step when you need the underlying technical evidence.'
    : `${stageEntries.length} matching evidence item${stageEntries.length === 1 ? '' : 's'} · select another stage to inspect it`;

  return `
    <div class="active-card ${r.stage === 'blocked' ? 'blocked' : ''}">
      <div class="active-top-bar">
        <div class="active-top-bar-left">
          <span class="active-run-id">${escapeHtml(r.run_id)}</span>
          <span class="active-intent" style="font-size:18px;font-weight:700">${escapeHtml(r.intent || '(no intent recorded)')}</span>
          ${r.repo ? `<span class="active-repo">📁 ${escapeHtml(r.repo)}</span>` : ''}
        </div>
        <div class="run-header-actions">
          ${viewCodeButton}
          <button type="button" class="files-button" aria-expanded="${FILES_DRAWER_OPEN}" onclick="toggleFilesDrawer()">Files <span class="files-count">${(r.artifacts || []).length}</span></button>
          <span class="stage-badge ${escapeHtml(r.stage)}">${escapeHtml(r.stage_label || r.stage)}</span>
          <span class="execution-status">${escapeHtml(r.execution_status || 'idle')}</span>
        </div>
      </div>
      <div class="active-progress-bar-section">
        <div class="progress-bar">${segments}</div>
      </div>
      <div class="focused-workspace">
        ${operatorControls}
        ${loopComplete ? completedOverviewHtml : `<section class="now-card ${escapeHtml(nowOutcome)}" aria-label="What is happening now">
          <div class="now-kicker">Now</div>
          <span class="outcome-badge ${escapeHtml(nowOutcome)}">${escapeHtml(outcomeText(nowOutcome))}</span>
          <div class="now-headline">${escapeHtml(nowHeadline)}</div>
          <div class="now-latest"><strong>Next safe action:</strong> ${escapeHtml(nextSafeAction)}</div>
        </section>`}
        <section class="activity-card" aria-label="Activity">
          <div class="activity-header">
            <div><div class="activity-title">${escapeHtml(activityTitle)}</div><div class="activity-subtitle">${escapeHtml(activitySubtitle)}</div></div>
          </div>
          ${feedHtml ? `<div class="worker-feed-container" id="feed-container-${escapeHtml(r.run_id)}">${feedHtml}</div>` : stageEmptyHtml}
        </section>
        ${receiptsHtml ? `<div class="verification-inline"><div class="verification-panel"><div class="panel-title">Verification</div>${receiptsHtml}</div></div>` : ''}
      </div>
      <aside class="files-drawer ${FILES_DRAWER_OPEN ? 'open' : ''}" id="files-drawer-${escapeHtml(r.run_id)}" aria-label="Pipeline files">
        <div class="files-drawer-head">
          <div><div class="files-drawer-title">Code &amp; files</div><div class="files-drawer-copy">Built code, stage artifacts, and evidence</div></div>
          <button type="button" class="files-close" aria-label="Close files drawer" onclick="closeFilesDrawer()">Close</button>
        </div>
        <div class="artifact-tree">${artifactTreeHtml || '<div class="files-empty">No artifacts recorded yet.</div>'}</div>
        <div class="artifact-preview" id="preview-${escapeHtml(r.run_id)}"></div>
      </aside>
    </div>`;
}

function renderOperatorControls(r) {
  let html = '';
  const status = r.execution_status || 'idle';
  const packet = (r.artifacts || []).includes('packet-brief-intel-01-loader-contract.md')
    ? 'packet-brief-intel-01-loader-contract.md'
    : 'approved packet';
  if (r.stage === 'assignment') html += `<div class="operator-control" id="operator-control-${escapeHtml(r.run_id)}">
    <div class="operator-control-title">Ready for Builder/Judge?</div>
    <div class="operator-control-copy">Dispatch Packet 1 now, or hold here if you want to redirect before local workers start.</div>
    <div class="operator-control-actions">
      <button class="operator-button primary" onclick="postOperatorAction('${escapeHtml(r.run_id)}','dispatch_packet_1', this)">Yes — Dispatch Packet 1</button>
      <button class="operator-button secondary" onclick="postOperatorAction('${escapeHtml(r.run_id)}','hold_redirect', this)">No — Hold / Redirect</button>
    </div>
    <div class="operator-control-status" id="operator-status-${escapeHtml(r.run_id)}">Approved packet: ${escapeHtml(packet)}</div>
  </div>`;
  if (['running', 'cancelling', 'stalled'].includes(status)) html += `<div class="operator-control" id="runtime-control-${escapeHtml(r.run_id)}">
    <div class="operator-control-title">Run control · ${escapeHtml(status)}</div>
    <div class="operator-control-copy">Preserve all evidence while stopping only this run-owned dispatcher.</div>
    <div class="operator-control-actions">
      <button class="operator-button secondary" onclick="postOperatorAction('${escapeHtml(r.run_id)}','stop_after_step', this)">Stop after current step</button>
      <button class="operator-button danger" onclick="if(confirm('Stop this run now? Partial output will be preserved.')) postOperatorAction('${escapeHtml(r.run_id)}','stop_now', this)">Stop now</button>
      ${r.can_reclaim_lock ? `<button class="operator-button secondary" onclick="postOperatorAction('${escapeHtml(r.run_id)}','reclaim_stale_lock', this)">Reclaim stale lock</button>` : ''}
    </div>
    <div class="operator-control-status" id="operator-status-${escapeHtml(r.run_id)}">The shared model server will remain available.</div>
  </div>`;
  return html;
}

async function postOperatorAction(runId, action, buttonEl) {
  const statusEl = document.getElementById('operator-status-' + runId);
  const original = buttonEl ? buttonEl.textContent : '';
  if (buttonEl) {
    buttonEl.disabled = true;
    buttonEl.textContent = 'Recording...';
  }
  if (statusEl) statusEl.textContent = 'Recording operator action...';
  try {
    const resp = await fetch('/api/operator-action', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: runId, action })
    });
    if (!resp.ok) throw new Error(await resp.text());
    const payload = await resp.json();
    if (statusEl) statusEl.textContent = `Recorded: ${payload.action.label}`;
    await refresh();
  } catch (e) {
    if (statusEl) statusEl.textContent = 'Action failed: ' + e;
  } finally {
    if (buttonEl) {
      buttonEl.disabled = false;
      buttonEl.textContent = original;
    }
  }
}

function selectWorkerOutput(cardEl, runId, options = {}) {
  const entryId = cardEl.dataset.entryId;
  if (!options.preserveUserSelection) SELECTED_OUTPUT = { runId, entryId };
  if (options.isUserAction) USER_SELECTED_OUTPUT = true;
  const container = document.getElementById('feed-container-' + runId);
  if (container) {
    container.querySelectorAll('.output-card').forEach(c => {
      c.classList.remove('selected');
      c.setAttribute('aria-selected', 'false');
    });
  }
  cardEl.classList.add('selected');
  cardEl.setAttribute('aria-selected', 'true');
  const viewer = document.getElementById('viewer-' + runId);
  if (!viewer) return;
  const entries = WORKER_FEED_DATA[runId] || [];
  const entry = entries.find(e => String(e.entry_id) === String(entryId));
  if (!entry) return;
  const role = entry.role || 'worker';
  const outcome = entry.outcome || 'neutral';
  const content = entry.content || '';
  const reasoningContent = entry.reasoning_content || '';
  const userPrompt = entry.user_prompt || '';
  const systemPrompt = entry.system_prompt || '';
  const usage = entry.usage || {};
  const resolvedModel = entry.resolved_model || entry.model || '';
  const resolvedModelRecorded = Boolean(entry.resolved_model_recorded);
  const modelLabel = resolvedModelRecorded
    ? `${resolvedModel}${entry.model && resolvedModel !== entry.model ? ` · routed by ${entry.model}` : ''}`
    : (entry.model ? `Exact served model not recorded · route ${entry.model}` : 'Model not recorded');
  const modelStr = escapeHtml(modelLabel);
  const isStreaming = entry.event === 'streaming';
  const detail = entry.operator_detail || {};
  const eventState = isStreaming ? 'Generating now' : (entry.event === 'started' && outcome === 'neutral' ? 'Started' : outcomeText(outcome));
  const who = resolvedModelRecorded
    ? `${humanRole(role)} using ${resolvedModel}`
    : `${humanRole(role)}; exact served model not recorded${entry.model ? ` (route: ${entry.model})` : ''}`;
  const how = detail.how || `${humanRole(role)} recorded this step${resolvedModel ? ` using ${resolvedModel}` : ''}.`;
  const metadata = JSON.stringify({
    entry_id: entry.entry_id,
    execution_status: entry.execution_status,
    outcome: entry.outcome,
    decision: entry.decision || null,
    category: entry.category,
    role: entry.role,
    model: entry.model,
    resolved_model: resolvedModel,
    resolved_model_recorded: resolvedModelRecorded,
    timestamp: entry.timestamp,
    usage,
    requested_max_tokens: entry.requested_max_tokens || null,
    finish_reason: entry.finish_reason || null,
    token_cap_reached: Boolean(entry.token_cap_reached),
    has_reasoning: Boolean(reasoningContent),
  }, null, 2);
  const nextAction = entry.next_safe_action || 'No separate follow-up was recorded for this step.';
  // Build tabs — add Thinking tab when reasoning content exists.
  const thinkingTab = reasoningContent
    ? `<button type="button" class="viewer-tab" data-output-tab="reasoning" role="tab" aria-selected="false" onclick="setOutputTab(this,'reasoning')">Thinking${isStreaming ? '<span class="card-live-dot"></span>' : ''}</button>`
    : '';
  const reasoningPanel = reasoningContent
    ? `<div class="viewer-panel output-viewer-reasoning" data-viewer-panel="reasoning" role="tabpanel">${escapeHtml(reasoningContent)}</div>`
    : '';
  viewer.innerHTML = `<div class="output-viewer-header">
    <div class="output-viewer-title">
      <div class="output-viewer-role">${escapeHtml(entry.summary || role)}${isStreaming ? '<span class="card-live-dot"></span>' : ''}</div>
      <div class="output-viewer-model">${modelStr}</div>
    </div>
    <span class="outcome-badge ${escapeHtml(outcome)}">${escapeHtml(eventState)}</span>
    <span class="output-viewer-time">${formatTime(entry.timestamp)}</span>
  </div>
  <div class="viewer-tabs" role="tablist" aria-label="Worker evidence views">
    <button type="button" class="viewer-tab" data-output-tab="summary" role="tab" aria-selected="false" onclick="setOutputTab(this,'summary')">Overview</button>
    ${thinkingTab}
    <button type="button" class="viewer-tab" data-output-tab="raw" role="tab" aria-selected="false" onclick="setOutputTab(this,'raw')">${isStreaming ? 'Live output' : 'Technical details'}</button>
    <button type="button" class="viewer-tab" data-output-tab="prompt" role="tab" aria-selected="false" onclick="setOutputTab(this,'prompt')">Prompt &amp; context</button>
    <button type="button" class="viewer-tab" data-output-tab="metadata" role="tab" aria-selected="false" onclick="setOutputTab(this,'metadata')">Metadata</button>
  </div>
  <div class="viewer-panel output-summary-panel active" data-viewer-panel="summary" role="tabpanel">
    <div class="operator-detail"><div class="operator-detail-label">What happened</div><div class="operator-detail-value">${escapeHtml(detail.what || entry.summary || 'Worker evidence was recorded.')}</div></div>
    <div class="operator-detail"><div class="operator-detail-label">Why</div><div class="operator-detail-value">${escapeHtml(detail.why || 'No separate reason was recorded for this step.')}</div></div>
    <div class="operator-detail"><div class="operator-detail-label">How</div><div class="operator-detail-value">${escapeHtml(how)}</div></div>
    <div class="operator-detail"><div class="operator-detail-label">Who</div><div class="operator-detail-value">${escapeHtml(who)}</div></div>
    <div class="operator-detail"><div class="operator-detail-label">When</div><div class="operator-detail-value">${formatTime(entry.timestamp)}</div></div>
    <div class="operator-detail"><div class="operator-detail-label">Evidence</div><div class="operator-detail-value">${escapeHtml(detail.evidence || 'No separate evidence reference was recorded for this step.')}</div></div>
    <div class="operator-detail"><div class="operator-detail-label">Next</div><div class="operator-detail-value">${escapeHtml(nextAction)}</div></div>
  </div>
  ${reasoningPanel}
  <div class="viewer-panel output-viewer-content" data-viewer-panel="raw" role="tabpanel">${escapeHtml(content || (isStreaming ? 'Waiting for model output…' : 'No raw content for this event.'))}</div>
  <div class="viewer-panel output-viewer-prompt" data-viewer-panel="prompt" role="tabpanel"><strong>System context</strong>\\n${escapeHtml(systemPrompt || 'Not recorded')}\\n\\n<strong>User context</strong>\\n${escapeHtml(userPrompt || 'Not recorded')}</div>
  <div class="viewer-panel output-viewer-content" data-viewer-panel="metadata" role="tabpanel">${escapeHtml(metadata)}</div>`;
  viewer.dataset.entryId = entryId;
  // Live work leads with the stream. Finished work leads with plain language.
  // Never override a tab that the operator explicitly selected for this entry.
  const savedTab = OUTPUT_TABS[entryId];
  if (savedTab) {
    activateOutputTab(viewer, savedTab);
  } else if (isStreaming) {
    activateOutputTab(viewer, 'raw');
  } else {
    activateOutputTab(viewer, 'summary');
  }
  // Auto-scroll the active panel to the bottom during streaming so the latest
  // content is always visible without manual scrolling.
  if (isStreaming) {
    requestAnimationFrame(() => {
      const activePanel = viewer.querySelector('.viewer-panel.active');
      if (activePanel) activePanel.scrollTop = activePanel.scrollHeight;
    });
  }
}

function activateOutputTab(viewer, panelName) {
  viewer.querySelectorAll('.viewer-tab').forEach(tab => {
    const active = tab.dataset.outputTab === panelName;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
  });
  viewer.querySelectorAll('[data-viewer-panel]').forEach(panel => {
    panel.classList.toggle('active', panel.dataset.viewerPanel === panelName);
  });
}

function setOutputTab(buttonEl, panelName) {
  const viewer = buttonEl.closest('.output-viewer');
  if (!viewer) return;
  if (viewer.dataset.entryId) OUTPUT_TABS[viewer.dataset.entryId] = panelName;
  activateOutputTab(viewer, panelName);
}

async function showArtifact(runId, fileName, silent=false, openDrawer=true) {
  OPEN_ARTIFACT = { runId, fileName };
  if (openDrawer) setFilesDrawerOpen(true);
  document.querySelectorAll('.artifact-file').forEach(button => {
    button.classList.toggle('selected', button.textContent === fileName);
  });
  const el = document.getElementById('preview-' + runId);
  if (!el) return;  // DOM not ready (e.g. run filtered out)
  el.style.display = 'block';
  if (!silent) el.textContent = 'Loading ' + fileName + '...';
  try {
    const resp = await fetch('/api/artifact?run=' + encodeURIComponent(runId) + '&file=' + encodeURIComponent(fileName));
    const text = await resp.text();
    el.textContent = text;
  } catch (e) {
    el.textContent = 'Failed to load: ' + e;
  }
}

function renderHistoryRow(r) {
  const stageIdx = STAGE_NAMES.indexOf(r.stage);
  const time = (r.events && r.events.length) ? formatTime(r.events[r.events.length - 1].timestamp) : '';
  const dotClass = (r.stage !== 'complete' && r.stage !== 'blocked') ? 'active' : '';
  return `
    <button class="history-row ${r.run_id === FOCUSED_RUN_ID ? 'selected' : ''}" type="button" onclick="focusRun('${escapeHtml(r.run_id)}')" title="Open run ${escapeHtml(r.run_id)}">
      <span class="hist-dot ${dotClass}"></span>
      <span class="hist-intent">${escapeHtml(r.intent || r.run_id)}</span>
      <span class="hist-stage">${escapeHtml(r.stage_label || r.stage)}</span>
      <span class="hist-time">${time}</span>
    </button>`;
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

document.addEventListener('click', event => {
  const card = event.target.closest('.output-card');
  if (card && card.dataset.runId) {
    selectWorkerOutput(card, card.dataset.runId, { isUserAction: true });
    return;
  }
  const selector = document.getElementById('run-selector');
  if (selector && !selector.contains(event.target)) closeRunSelector();
  const systemPopover = document.getElementById('system-popover');
  const systemWidget = document.getElementById('system-widget');
  if (systemPopover && systemWidget && !systemPopover.contains(event.target) && !systemWidget.contains(event.target)) closeSystemDetails();
  const popover = document.getElementById('git-popover');
  const widget = document.getElementById('git-widget');
  if (!popover || !widget) return;
  if (!popover.contains(event.target) && !widget.contains(event.target)) closeGitDetails();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') { closeRunSelector(); closeGitDetails(); closeSystemDetails(); closeFilesDrawer(); }
});

refresh();
refreshGit();
refreshMemory();

// Adaptive refresh: poll every 1s when a worker is actively streaming so the
// operator sees output flowing in near-real-time. When idle, fall back to 3s to
// reduce unnecessary requests.
function adaptiveRefresh() {
  refresh();
  setTimeout(adaptiveRefresh, IS_STREAMING ? 1000 : 3000);
}
setTimeout(adaptiveRefresh, 3000);
setInterval(refreshGit, 3000);
setInterval(refreshMemory, 2000);

// ── Workspace picker logic ──
let WORKSPACE_STATE = { active: null, recent: [], platform: 'unknown' };

async function loadWorkspaceState() {
  try {
    const resp = await fetch('/api/workspace');
    WORKSPACE_STATE = await resp.json();
    updateWorkspaceWidget();
    renderWorkspaceDropdown();
  } catch (e) {
    console.error('Failed to load workspace state', e);
  }
}

function updateWorkspaceWidget() {
  const widget = document.getElementById('workspace-widget');
  const nameEl = document.getElementById('workspace-name');
  if (WORKSPACE_STATE.active && WORKSPACE_STATE.active.exists) {
    widget.classList.remove('no-workspace');
    nameEl.textContent = WORKSPACE_STATE.active.name;
    widget.title = WORKSPACE_STATE.active.path;
  } else if (WORKSPACE_STATE.active && !WORKSPACE_STATE.active.exists) {
    widget.classList.add('no-workspace');
    nameEl.textContent = 'Missing: ' + WORKSPACE_STATE.active.name;
    widget.title = 'Workspace folder not found: ' + WORKSPACE_STATE.active.path;
  } else {
    widget.classList.add('no-workspace');
    nameEl.textContent = 'Not set';
    widget.title = 'Click to select a workspace';
  }
}

function renderWorkspaceDropdown() {
  const dd = document.getElementById('workspace-dropdown');
  const isMac = WORKSPACE_STATE.platform === 'macos';
  const pickBtnLabel = isMac ? '📁 Open Finder…' : '📁 Choose folder…';
  let html = `
    <div class="workspace-dd-header">
      <div class="workspace-dd-title">Workspace</div>
      <div class="workspace-dd-actions">
        <button class="workspace-dd-btn primary" onclick="pickWorkspaceFolder(event)" type="button">${pickBtnLabel}</button>
      </div>
    </div>
    <div class="workspace-dd-list">`;
  const recent = WORKSPACE_STATE.recent || [];
  if (!recent.length) {
    html += `<div class="workspace-dd-empty">No recent workspaces.<br>Pick a folder to get started.</div>`;
  } else {
    html += `<div class="workspace-dd-section">Recent</div>`;
    const activePath = WORKSPACE_STATE.active ? WORKSPACE_STATE.active.path : null;
    recent.forEach(w => {
      const activeClass = w.path === activePath ? ' active' : '';
      const missingClass = w.exists ? '' : ' missing';
      html += `
        <div class="workspace-dd-item${activeClass}${missingClass}" onclick="setWorkspace('${escapeHtml(w.path)}')" title="${escapeHtml(w.path)}">
          <span class="item-folder">📂</span>
          <span class="item-copy">
            <div class="item-name">${escapeHtml(w.name)}</div>
            <div class="item-path">${escapeHtml(w.path)}</div>
          </span>
          <span class="item-remove" onclick="removeWorkspace(event, '${escapeHtml(w.path)}')" title="Remove from recent">✕</span>
        </div>`;
    });
  }
  html += `</div>`;
  dd.innerHTML = html;
}

function toggleWorkspaceDropdown(event) {
  if (event) event.stopPropagation();
  const dd = document.getElementById('workspace-dropdown');
  const widget = document.getElementById('workspace-widget');
  dd.classList.toggle('open');
  widget.setAttribute('aria-expanded', String(dd.classList.contains('open')));
}

function closeWorkspaceDropdown() {
  const dd = document.getElementById('workspace-dropdown');
  const widget = document.getElementById('workspace-widget');
  dd.classList.remove('open');
  widget.setAttribute('aria-expanded', 'false');
}

function handleWorkspaceKey(event) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    toggleWorkspaceDropdown(event);
  }
}

async function pickWorkspaceFolder(event) {
  if (event) event.stopPropagation();
  closeWorkspaceDropdown();
  // Show a loading state on the widget
  const nameEl = document.getElementById('workspace-name');
  const origText = nameEl.textContent;
  nameEl.textContent = 'Opening Finder…';
  try {
    const resp = await fetch('/api/workspace/pick', { method: 'POST' });
    const data = await resp.json();
    if (data.cancelled) {
      nameEl.textContent = origText;
      return;
    }
    WORKSPACE_STATE = { active: data.active ? { path: data.active, name: data.name, exists: true } : null, recent: data.recent || [], platform: WORKSPACE_STATE.platform };
    updateWorkspaceWidget();
    renderWorkspaceDropdown();
    // Full page refresh — the workspace changed, so all data needs reloading
    refresh();
    refreshGit();
    loadChatSessions();
  } catch (e) {
    nameEl.textContent = origText;
    console.error('Failed to pick workspace', e);
  }
}

async function setWorkspace(path) {
  closeWorkspaceDropdown();
  try {
    const resp = await fetch('/api/workspace/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    const data = await resp.json();
    if (!resp.ok) { console.error('setWorkspace failed', data); return; }
    WORKSPACE_STATE = { active: data.active ? { path: data.active, name: data.name, exists: true } : null, recent: data.recent || [], platform: WORKSPACE_STATE.platform };
    updateWorkspaceWidget();
    renderWorkspaceDropdown();
    refresh();
    refreshGit();
    loadChatSessions();
  } catch (e) {
    console.error('Failed to set workspace', e);
  }
}

async function removeWorkspace(event, path) {
  if (event) event.stopPropagation();
  try {
    const resp = await fetch('/api/workspace/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    const data = await resp.json();
    if (data.active === null || data.active === undefined) {
      WORKSPACE_STATE.active = null;
    }
    WORKSPACE_STATE.recent = data.recent || [];
    updateWorkspaceWidget();
    renderWorkspaceDropdown();
  } catch (e) {
    console.error('Failed to remove workspace', e);
  }
}

// Close workspace dropdown when clicking outside
document.addEventListener('click', event => {
  const wsWidget = document.getElementById('workspace-widget');
  if (wsWidget && !wsWidget.contains(event.target)) closeWorkspaceDropdown();
});

// Initialize workspace on load
loadWorkspaceState();

// ── Chat sidebar logic ──
let CHAT_MODELS = [];
let CHAT_SESSIONS = [];
let CHAT_SESSION_ID = typeof localStorage === 'undefined'
  ? null
  : (localStorage.getItem('devflow.chat.session') || null);
let CHAT_RUN_ID = null;
let CHAT_IS_SENDING = false;
let CHAT_RECOGNITION = null;
let CHAT_DICTATION_BASE = '';
let CHAT_DICTATION_LISTENING = false;

function persistChatModelSelection() {
  const value = document.getElementById('chat-model-select').value;
  if (value && typeof localStorage !== 'undefined') localStorage.setItem('devflow.chat.model', value);
}

async function loadChatModels() {
  try {
    const resp = await fetch('/api/chat/models');
    const data = await resp.json();
    CHAT_MODELS = data.models || [];
    const sel = document.getElementById('chat-model-select');
    if (!CHAT_MODELS.length) {
      sel.innerHTML = '<option value="">No models available</option>';
      return;
    }
    sel.innerHTML = CHAT_MODELS.map(m =>
      `<option value="${escapeHtml(m.name)}">${escapeHtml(m.display_name)} (${escapeHtml(m.cost_class)})</option>`
    ).join('');
    const storedModel = typeof localStorage === 'undefined'
      ? null
      : localStorage.getItem('devflow.chat.model');
    const selectedModel = CHAT_MODELS.some(m => m.name === storedModel)
      ? storedModel
      : data.default_model;
    if (selectedModel && CHAT_MODELS.some(m => m.name === selectedModel)) {
      sel.value = selectedModel;
      if (typeof localStorage !== 'undefined') localStorage.setItem('devflow.chat.model', selectedModel);
    }
  } catch (e) {
    console.error('Failed to load chat models', e);
  }
}

async function loadChatSessions() {
  try {
    const resp = await fetch('/api/chat/sessions');
    const data = await resp.json();
    const sessions = data.sessions || [];
    CHAT_SESSIONS = sessions;
    const sel = document.getElementById('chat-session-select');
    sel.innerHTML = '<option value="">+ New session</option>';
    sessions.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.session_id;
      opt.textContent = s.preview || s.session_id;
      sel.appendChild(opt);
    });
    if (CHAT_SESSION_ID && sessions.some(s => s.session_id === CHAT_SESSION_ID)) {
      sel.value = CHAT_SESSION_ID;
      await switchChatSession();
    } else if (CHAT_SESSION_ID) {
      CHAT_SESSION_ID = null;
      try { if (typeof localStorage !== 'undefined') localStorage.removeItem('devflow.chat.session'); } catch (_) {}
    }
  } catch (e) {
    console.error('Failed to load chat sessions', e);
  }
}

async function switchChatSession() {
  const sel = document.getElementById('chat-session-select');
  const sessionId = sel.value;
  if (!sessionId) {
    newChatSession();
    return;
  }
  CHAT_SESSION_ID = sessionId;
  try { if (typeof localStorage !== 'undefined') localStorage.setItem('devflow.chat.session', sessionId); } catch (_) {}
  const session = CHAT_SESSIONS.find(s => s.session_id === sessionId);
  CHAT_RUN_ID = session?.run_id || null;
  CHAT_AWAITS_FIRST_MESSAGE = false;
  if (CHAT_RUN_ID) setFocusedRun(CHAT_RUN_ID);
  try {
    const resp = await fetch('/api/chat/transcript?session=' + encodeURIComponent(sessionId));
    const data = await resp.json();
    CHAT_SESSION_ID = sessionId;
    document.getElementById('chat-model-select').value = data.model || '';
    persistChatModelSelection();
    renderChatMessages(data.messages || []);
    refresh();
  } catch (e) {
    renderChatError('Failed to load session: ' + e.message);
  }
}

function newChatSession() {
  CHAT_SESSION_ID = null;
  try { if (typeof localStorage !== 'undefined') localStorage.removeItem('devflow.chat.session'); } catch (_) {}
  CHAT_RUN_ID = null;
  CHAT_AWAITS_FIRST_MESSAGE = true;
  setFocusedRun(null);
  OPEN_ARTIFACT = null;
  SELECTED_OUTPUT = null;
  USER_SELECTED_OUTPUT = false;
  WORKER_FEED_DATA = {};
  document.getElementById('chat-session-select').value = '';
  renderChatMessages([]);
  render({ runs: [] });
  document.getElementById('chat-input').focus();
}

function renderChatMessages(messages) {
  const container = document.getElementById('chat-messages');
  if (!messages.length) {
    container.innerHTML = `
      <div class="chat-empty" id="chat-empty">
        <div class="chat-empty-icon">💬</div>
        <div>Start a brainstorm session.</div>
        <div style="font-size:11px;margin-top:4px;">Your conversation feeds directly into the DevFlow pipeline.</div>
      </div>`;
    return;
  }
  container.innerHTML = '';
  messages.forEach(msg => container.appendChild(createChatBubble(msg)));
  container.scrollTop = container.scrollHeight;
}

function createChatBubble(msg) {
  const div = document.createElement('div');
  div.className = 'chat-msg ' + (msg.role || 'assistant');
  div.textContent = msg.content || '';
  if (msg.role === 'assistant' && msg.model) {
    const modelLabel = document.createElement('div');
    modelLabel.className = 'msg-model';
    modelLabel.textContent = msg.model;
    div.appendChild(modelLabel);
  }
  return div;
}

function renderChatError(message) {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'chat-msg error';
  div.textContent = message;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function showChatTyping() {
  const container = document.getElementById('chat-messages');
  const empty = document.getElementById('chat-empty');
  if (empty) empty.remove();
  const div = document.createElement('div');
  div.className = 'chat-typing';
  div.id = 'chat-typing-indicator';
  div.innerHTML = '<span class="dot">●</span><span class="dot">●</span><span class="dot">●</span>';
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function removeChatTyping() {
  const indicator = document.getElementById('chat-typing-indicator');
  if (indicator) indicator.remove();
}

function appendUserMessage(text) {
  const container = document.getElementById('chat-messages');
  const empty = document.getElementById('chat-empty');
  if (empty) empty.remove();
  container.appendChild(createChatBubble({ role: 'user', content: text }));
  container.scrollTop = container.scrollHeight;
}

function appendAssistantMessage(msg) {
  const container = document.getElementById('chat-messages');
  container.appendChild(createChatBubble(msg));
  container.scrollTop = container.scrollHeight;
}

function handleChatKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendChatMessage();
  }
}

function setChatDictationState(message, listening=false) {
  const button = document.getElementById('chat-mic-btn');
  const state = document.getElementById('chat-dictation-state');
  if (!button || !state) return;
  CHAT_DICTATION_LISTENING = listening;
  button.classList.toggle('listening', listening);
  button.setAttribute('aria-pressed', String(listening));
  button.setAttribute('aria-label', listening ? 'Stop dictation' : 'Start dictation');
  button.title = listening ? 'Stop dictation' : 'Dictate into the brainstorm composer';
  state.classList.toggle('listening', listening);
  state.textContent = message;
}

function initializeChatDictation() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const button = document.getElementById('chat-mic-btn');
  if (!button) return;
  if (!Recognition) {
    button.disabled = true;
    setChatDictationState('Dictation unavailable in this browser. You can still type your message.');
    button.title = 'Speech dictation is not available in this browser';
    return;
  }
  CHAT_RECOGNITION = new Recognition();
  CHAT_RECOGNITION.continuous = false;
  CHAT_RECOGNITION.interimResults = true;
  CHAT_RECOGNITION.lang = document.documentElement.lang || 'en-US';
  CHAT_RECOGNITION.onstart = () => setChatDictationState('Listening… Speak now; select Stop when finished.', true);
  CHAT_RECOGNITION.onresult = event => {
    const transcript = Array.from(event.results)
      .map(result => result[0]?.transcript || '')
      .join(' ')
      .trim();
    const input = document.getElementById('chat-input');
    input.value = [CHAT_DICTATION_BASE, transcript].filter(Boolean).join(' ');
    autoResizeChatInput(input);
  };
  CHAT_RECOGNITION.onerror = event => {
    const messages = {
      'not-allowed': 'Microphone permission was denied. Enable it in the browser or type your message.',
      'audio-capture': 'No working microphone was found. You can still type your message.',
      'no-speech': 'No speech was detected. Select Mic to try again.',
    };
    setChatDictationState(messages[event.error] || `Dictation stopped: ${event.error || 'unknown error'}.`);
  };
  CHAT_RECOGNITION.onend = () => {
    if (CHAT_DICTATION_LISTENING) setChatDictationState('Dictation ready. Review the text, then send.');
  };
  button.disabled = false;
  button.title = 'Dictate into the brainstorm composer';
  setChatDictationState('Dictation ready. Select Mic and speak.');
}

function toggleChatDictation() {
  if (!CHAT_RECOGNITION) return;
  if (CHAT_DICTATION_LISTENING) {
    CHAT_RECOGNITION.stop();
    setChatDictationState('Dictation ready. Review the text, then send.');
    return;
  }
  CHAT_DICTATION_BASE = document.getElementById('chat-input').value.trim();
  try {
    CHAT_RECOGNITION.start();
  } catch (error) {
    setChatDictationState(`Dictation could not start: ${error.message || error}.`);
  }
}

function autoResizeChatInput(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

async function sendChatMessage() {
  if (CHAT_IS_SENDING) return;
  const input = document.getElementById('chat-input');
  const message = input.value.trim();
  if (!message) return;
  if (CHAT_DICTATION_LISTENING && CHAT_RECOGNITION) CHAT_RECOGNITION.stop();
  const model = document.getElementById('chat-model-select').value;

  CHAT_IS_SENDING = true;
  document.getElementById('chat-send-btn').disabled = true;
  input.value = '';
  input.style.height = 'auto';

  appendUserMessage(message);
  showChatTyping();

  try {
    let resp;
    if (!CHAT_SESSION_ID) {
      // Start a new session with the first message
      resp = await fetch('/api/chat/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ intent: message, model: model || undefined }),
      });
    } else {
      resp = await fetch('/api/chat/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: CHAT_SESSION_ID, message: message, model: model || undefined }),
      });
    }
    const data = await resp.json();
    if (!resp.ok) {
      renderChatError(data.error || data.detail || 'Request failed');
      return;
    }
    if (data.session_id) {
      CHAT_SESSION_ID = data.session_id;
      try { if (typeof localStorage !== 'undefined') localStorage.setItem('devflow.chat.session', data.session_id); } catch (_) {}
      CHAT_RUN_ID = data.run_id || null;
      CHAT_AWAITS_FIRST_MESSAGE = false;
      if (CHAT_RUN_ID) setFocusedRun(CHAT_RUN_ID);
    }
    removeChatTyping();
    if (data.response) {
      appendAssistantMessage(data.response);
    } else {
      appendAssistantMessage(data);
    }
    // Refresh session list to include the new session
    loadChatSessions();
    // Trigger a status board refresh so the new run appears
    refresh();
  } catch (e) {
    removeChatTyping();
    renderChatError('Connection error: ' + e.message);
  } finally {
    CHAT_IS_SENDING = false;
    document.getElementById('chat-send-btn').disabled = false;
    document.getElementById('chat-input').focus();
  }
}

// Initialize chat sidebar on load
loadChatModels();
loadChatSessions();
initializeChatDictation();
document.getElementById('chat-input').focus();
</script>
</body>
</html>
"""
