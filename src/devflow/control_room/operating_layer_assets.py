from __future__ import annotations

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Dev-Flow Operating Layer — project task boards, evidence tracking, and automation">
  <title>Dev-Flow Operating Layer</title>
  <link rel="stylesheet" href="/app.css">
</head>
<body>
  <!-- Skip-to-main link for keyboard/screen reader users -->
  <a href="#main-panel" class="skip-link">Skip to main content</a>

  <div class="app-shell" role="application">
    <!-- Sidebar / navigation landmark -->
    <aside class="sidebar" role="complementary" aria-label="Navigation">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">DF</div>
        <div>
          <strong>Dev-Flow</strong>
          <span>Operating Layer</span>
        </div>
      </div>
      <nav aria-label="Primary" role="navigation">
        <ul>
          <li><a href="#orchestrator" data-action="go-orchestrator" aria-current="page">Overview</a></li>
          <li><a href="#map" data-action="go-map">Map</a></li>
          <li><a href="#lanes" data-action="go-lanes">Workers</a></li>
          <li><a href="#goals" data-action="go-goals">Goals</a></li>
          <li><a href="#specs" data-action="go-specs">Specs</a></li>
          <li><a href="#gates" data-action="go-gates">Progress</a></li>
          <li><a href="#attention" data-action="go-attention">Alerts</a></li>
          <li><a href="#projects" data-action="go-projects">Projects</a></li>
          <li><a href="#inbox" data-action="go-inbox">Inbox</a></li>
          <li><a href="#actions" data-action="go-actions">Actions</a></li>
          <li><a href="#evidence" data-action="go-evidence">Evidence</a></li>
          <li><a href="#promotion" data-action="go-promotion">Review</a></li>
        </ul>
      </nav>
    </aside>

    <!-- Main content landmark -->
    <main id="main-panel" role="main" aria-label="Main content">
      <!-- Command Center / topbar -->
      <header id="command" class="topbar" data-section="command" aria-labelledby="repo-title">
        <div class="topbar-left">
          <p id="repo-label" class="label" hidden>Repository</p>
          <h1 id="repo-title">Loading...</h1>
          <div class="metrics-row" aria-label="Command Center metrics">
            <span id="metrics-heading" class="sr-only">Metrics: total, active, blocked, verify counts</span>
            <span>Total <output id="total-tasks" aria-labelledby="metrics-heading" aria-live="polite" aria-atomic="true">0</output></span>
            <span>Active <output id="active-tasks" aria-labelledby="metrics-heading" aria-live="polite" aria-atomic="true">0</output></span>
            <span class="attention">Blocked <output id="blocked-tasks" aria-labelledby="metrics-heading" aria-live="polite" aria-atomic="true">0</output></span>
            <span class="verify">Verify <output id="verify-tasks" aria-labelledby="metrics-heading" aria-live="polite" aria-atomic="true">0</output></span>
            <span class="metric-action">Next <code id="next-action" aria-label="Next action" tabindex="-1">Loading...</code></span>
          </div>
        </div>
        <div class="topbar-right">
          <div class="filter-control">
            <label class="filter-label" for="global-filter">Filter</label>
            <input id="global-filter" class="filter-input" type="search" placeholder="task, status, worker..." autocomplete="off" aria-describedby="filter-legend">
            <span id="filter-legend" class="sr-only">Filter tasks by name, status, or assigned worker</span>
            <strong id="filter-count" aria-live="polite" aria-atomic="true">All</strong>
          </div>
          <span id="branch-pill" class="pill" aria-label="Current branch">branch</span>
          <span id="tree-pill" class="pill" aria-label="Repository state">state</span>
          <button id="all-projects-button" type="button" title="Show host repository">Host</button>
          <button id="refresh-button" type="button" title="Refresh snapshot">Refresh</button>
        </div>
      </header>

      <!-- Orchestrator stage (live-updating panel) -->
      <section id="orchestrator" class="orchestrator-stage" data-section="orchestrator" aria-label="Orchestrator overview" aria-live="polite" aria-atomic="true">
        <div class="orchestrator-agents" aria-label="Worker activity summary">
          <div class="section-heading">
            <span>Worker Activity</span>
            <output id="agent-progress-count" aria-live="polite" aria-atomic="true">0 workers</output>
          </div>
          <div id="orchestrator-agent-progress" class="agent-progress-list" role="list" aria-label="Worker activity by actual DevFlow worker"></div>
        </div>
        <div class="orchestrator-core">
          <div class="orchestrator-kicker">
            <span id="orchestrator-sync" aria-live="polite" aria-atomic="true">Uplink synced</span>
            <span class="sr-only">DevFlow Orchestrator</span>
            <strong aria-hidden="true">DevFlow Orchestrator</strong>
            <span id="orchestrator-time" aria-live="polite" aria-atomic="true">--</span>
          </div>
          <span class="orchestrator-label">Current Directive</span>
          <h2 id="orchestrator-goal-title">Loading current goal...</h2>
          <p id="orchestrator-directive">Reading operating layer snapshot.</p>
          <div class="orchestrator-command">
            <span>Next Safe Action</span>
            <code id="orchestrator-command" aria-label="Orchestrator next action">Loading...</code>
          </div>
          <div class="mission-feed" aria-label="Recent work feed">
            <div class="section-heading">
              <span>Work Feed</span>
              <output id="mission-feed-count" aria-live="polite" aria-atomic="true">0 updates</output>
            </div>
            <div id="mission-feed-list" class="mission-feed-list" role="list"></div>
          </div>
          <div class="orchestrator-counters" role="group" aria-label="Orchestrator counters">
            <div><span>Queue</span><output id="orchestrator-queue" aria-live="polite" aria-atomic="true">0</output></div>
            <div><span>Ready</span><output id="orchestrator-ready" aria-live="polite" aria-atomic="true">0</output></div>
            <div><span>Blocked</span><output id="orchestrator-blocked" aria-live="polite" aria-atomic="true">0</output></div>
            <div><span>Evidence</span><output id="orchestrator-evidence" aria-live="polite" aria-atomic="true">0</output></div>
          </div>
        </div>
        <div class="orchestrator-health" role="region" aria-label="System health">
          <div class="section-heading">
            <span>System Health</span>
            <output id="orchestrator-health-label" aria-live="polite" aria-atomic="true">Nominal</output>
          </div>
          <div id="orchestrator-health-bars" class="orchestrator-health-bars" role="progressbar" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100" aria-label="Health progress"></div>
          <div class="orchestrator-mini">
            <div><span>Freshness</span><output id="orchestrator-freshness" aria-live="polite" aria-atomic="true">unknown</output></div>
            <div><span>Goal</span><output id="orchestrator-goal-id" aria-live="polite" aria-atomic="true">none</output></div>
          </div>
        </div>
      </section>

      <!-- Operating Map -->
      <section id="map" class="map-strip" data-section="map" aria-label="Operating map">
        <div class="section-heading">
          <span aria-hidden="true">Operating Map</span>
          <output id="map-status" aria-live="polite" aria-atomic="true">Loading</output>
        </div>
        <div id="map-list" class="map-list" role="list" aria-label="Map items"></div>
      </section>

      <!-- Context / scope bar -->
      <section id="context" class="context-bar" aria-label="Current scope" aria-live="polite" aria-atomic="true">
        <div>
          <span id="scope-label">Scope</span>
          <output id="context-title" aria-labelledby="scope-label">All work</output>
          <p id="context-detail" aria-hidden="true">Whole operating layer</p>
        </div>
        <button id="clear-context-button" type="button" aria-label="Clear current scope">Clear</button>
      </section>

      <!-- Action Rail (collapsible panel) -->
      <section id="actions" class="action-strip collapsed" data-section="actions" aria-label="Action rail">
        <button class="section-heading accordion-trigger" type="button" data-toggle-section="actions" aria-expanded="false" aria-controls="action-list" aria-label="Action rail, 0 actions">
          <span>
            <strong class="sr-only" aria-hidden="true">Action Rail</strong>
            Action Rail
          </span>
          <output id="action-count" aria-live="polite" aria-atomic="true">0</output>
        </button>
        <div id="action-list" class="action-list section-body" role="list" aria-label="Action items"></div>
        <div id="action-preview" class="action-preview section-body" aria-live="polite" aria-atomic="true" aria-label="Action preview"></div>
      </section>

      <!-- Question & Blocker Inbox (collapsible panel) -->
      <section id="inbox" class="inbox-strip collapsed" data-section="inbox" aria-label="Question and blocker inbox">
        <button class="section-heading accordion-trigger" type="button" data-toggle-section="inbox" aria-expanded="false" aria-controls="inbox-list" aria-label="Question and blocker inbox, 0 items">
          <span>Question &amp; Blocker Inbox</span>
          <output id="inbox-count" aria-live="polite" aria-atomic="true">0</output>
        </button>
        <div id="inbox-list" class="inbox-list section-body" role="list" aria-label="Inbox items"></div>
      </section>

      <!-- Goal Board (collapsible panel) -->
      <section id="goals" class="goal-strip collapsed" data-section="goals" aria-label="Goal Board">
        <button class="section-heading accordion-trigger" type="button" data-toggle-section="goals" aria-expanded="false" aria-controls="goal-board-list" aria-label="Goal Board, 0 goals">
          <span>Goal Board</span>
          <output id="goal-board-count" aria-live="polite" aria-atomic="true">0</output>
        </button>
        <div id="goal-board-list" class="goal-board-list section-body" role="list" aria-label="Goal items"></div>
      </section>

      <!-- Multi-Project Overview -->
      <section id="projects" class="project-strip expanded" data-section="projects" aria-label="Multi-Project Overview">
        <div class="section-heading">
          <span>Multi-Project Overview</span>
          <output id="project-count" aria-live="polite" aria-atomic="true">0</output>
        </div>
        <div id="project-summary" class="project-summary" role="region" aria-label="Project summary"></div>
        <div id="project-list" class="project-list" role="list" aria-label="Project list"></div>
      </section>

      <!-- Spec Board (collapsible panel) -->
      <section id="specs" class="spec-grid collapsed" data-section="specs" aria-label="Spec Board">
        <button class="section-heading accordion-trigger" type="button" data-toggle-section="specs" aria-expanded="false" aria-controls="spec-list" aria-label="Spec Board, 0 specs">
          <span>Spec Board</span>
          <output id="spec-count" aria-live="polite" aria-atomic="true">0</output>
        </button>
        <div id="spec-list" class="spec-list section-body" role="list" aria-label="Specification items"></div>
      </section>

      <!-- Worker Lanes / Agents + Task Inspector -->
      <section id="lanes" class="workspace" data-section="lanes" aria-label="Worker lanes">
        <div class="agents-canvas">
          <div class="agents-header">
            <div>
              <span class="agents-eyebrow">Workers</span>
              <h3>Worker detail</h3>
            </div>
            <button id="agent-stack-toggle" class="agent-stack-toggle" type="button" aria-expanded="false" aria-label="Expand agent stack" aria-controls="agent-cards">
              <span class="sr-only">Expand agent stack</span>
              Expand
            </button>
            <div class="agent-status-board" role="group" aria-label="Worker status">
              <div><span>Running</span><output id="agent-active-count" aria-live="polite" aria-atomic="true">0</output></div>
              <div><span>Waiting</span><output id="agent-idle-count" aria-live="polite" aria-atomic="true">0</output></div>
              <div><span>Recorded</span><output id="agent-dormant-count" aria-live="polite" aria-atomic="true">0</output></div>
            </div>
          </div>
          <div id="agent-cards" class="agent-cards" role="list" aria-label="Worker detail cards"></div>
          <div class="agent-log-panel" role="region" aria-label="Worker logs">
            <div class="section-heading">
              <span>Worker Logs</span>
              <output id="agent-log-count" aria-live="polite" aria-atomic="true">0 entries</output>
            </div>
            <div id="agent-log-list" class="agent-log-list" role="log" aria-label="Worker log entries" aria-relevant="all"></div>
          </div>
          <div class="lane-board" id="lane-board" role="list" aria-label="Lane board"></div>
        </div>
        <aside id="inspector" class="inspector" aria-label="Task inspector" role="complementary">
          <div class="section-heading">
            <span aria-hidden="true">Task Inspector</span>
            <output id="selected-task-id" aria-live="polite" aria-atomic="true">None</output>
            <strong class="sr-only" role="heading" aria-level="3">Task Inspector</strong>
          </div>
          <h3 id="selected-title">Select a task</h3>
          <dl id="selected-details" aria-label="Task details"></dl>
          <div class="command-box">
            <span>Safer Command</span>
            <code id="selected-command" aria-label="Selected safe action">None</code>
          </div>
          <div class="detail-panel" role="region" aria-label="Evidence detail">
            <div class="section-heading">
              <span aria-hidden="true">Evidence Detail</span>
              <strong class="sr-only">Evidence Detail</strong>
            </div>
            <output id="detail-event-count" class="sr-only" aria-live="polite" aria-atomic="true">0 events</output>
            <div id="detail-summary" class="detail-summary" aria-label="Evidence summary"></div>
            <div id="detail-events" class="detail-events" role="log" aria-label="Evidence event timeline" aria-relevant="all"></div>
          </div>
        </aside>
      </section>

      <!-- Task Progress (collapsible panel) -->
      <section id="gates" class="gate-strip collapsed" data-section="gates" aria-label="Task progress">
        <button class="section-heading accordion-trigger" type="button" data-toggle-section="gates" aria-expanded="false" aria-controls="gate-list" aria-label="Task progress, 0 tasks">
          <span>Task Progress</span>
          <output id="gate-count" aria-live="polite" aria-atomic="true">0</output>
        </button>
        <div class="section-body progress-page">
          <div id="progress-summary-grid" class="progress-summary-grid" aria-label="Task readiness summary"></div>
          <div id="gate-list" class="progress-checklist gate-list" role="list" aria-label="Task readiness checklist"></div>
        </div>
      </section>

      <!-- Attention Strip -->
      <section id="attention" class="attention-strip" data-section="attention" aria-label="Attention strip">
        <div class="section-heading">
          <span aria-hidden="true">Attention Strip</span>
          <output id="attention-count" aria-live="polite" aria-atomic="true">0</output>
        </div>
        <div id="attention-list" class="attention-list" role="list" aria-label="Attention items"></div>
      </section>

      <!-- Ready Review + Questions (collapsible panel) -->
      <section id="promotion" class="desk-grid collapsed" data-section="promotion" aria-label="Ready review">
        <div>
          <button class="section-heading accordion-trigger" type="button" data-toggle-section="promotion" aria-expanded="false" aria-controls="question-list" aria-label="Questions, 0 pending">
            <span>Questions</span>
            <output id="question-count" aria-live="polite" aria-atomic="true">0</output>
          </button>
          <div id="question-list" class="list-stack section-body" role="list" aria-label="Pending questions"></div>
        </div>
        <div>
          <div class="section-heading">
            <span aria-hidden="true">Ready for Review</span>
            <strong class="sr-only" role="heading" aria-level="3">Ready for Review</strong>
          </div>
          <output id="promotion-count" aria-live="polite" aria-atomic="true">0</output>
          <div id="promotion-list" class="list-stack" role="list" aria-label="Ready review items"></div>
        </div>
      </section>

      <!-- Evidence Timeline (collapsible panel) -->
      <section id="evidence" class="evidence-strip collapsed" data-section="evidence" aria-label="Evidence timeline">
        <button class="section-heading accordion-trigger" type="button" data-toggle-section="evidence" aria-expanded="false" aria-controls="evidence-list" aria-label="Evidence timeline, 0 items">
          <span>Evidence Timeline</span>
          <output id="evidence-count" aria-live="polite" aria-atomic="true">0</output>
        </button>
        <div id="evidence-list" class="evidence-list section-body" role="list" aria-label="Evidence items"></div>
      </section>
    </main>
  </div>
  <script src="/app.js"></script>
</body>
</html>
"""


APP_CSS = """:root {
  --bg: #f7f8fa;
  --panel: #ffffff;
  --panel-2: #f1f5f8;
  --text: #172026;
  --muted: #69737d;
  --border: #d7dee5;
  --border-strong: #b8c4cf;
  --teal: #0f766e;
  --teal-soft: #d9f2ef;
  --amber: #b7791f;
  --amber-soft: #fff4d6;
  --red: #b42318;
  --red-soft: #fee4df;
  --indigo: #4f46e5;
  --indigo-soft: #eef2ff;
  --green: #16a34a;
  --green-soft: #dcfce7;
  --type-display: 28px;
  --type-h1: 18px;
  --type-h2: 15px;
  --type-body: 13px;
  --type-caption: 11px;
  --type-mono: 12px;
  --shadow: 0 16px 38px rgba(23, 32, 38, 0.08);
  --font-ui: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --font-mono: "SFMono-Regular", "JetBrains Mono", Consolas, monospace;
  font-family: var(--font-ui);
}

* { box-sizing: border-box; }

.skip-link {
  position: absolute;
  left: 16px;
  top: 12px;
  z-index: 100;
  padding: 8px 10px;
  border-radius: 6px;
  background: #ffffff;
  color: #172026;
  opacity: 0;
  pointer-events: none;
  transform: translateY(-150%);
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.skip-link:focus {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

html {
  max-width: 100%;
  overflow-x: hidden;
}

body {
  margin: 0;
  background:
    radial-gradient(circle at 0 0, rgba(15, 118, 110, 0.08), transparent 26rem),
    linear-gradient(90deg, rgba(16, 24, 32, 0.035) 1px, transparent 1px),
    linear-gradient(180deg, rgba(16, 24, 32, 0.03) 1px, transparent 1px),
    var(--bg);
  background-size: auto, 28px 28px, 28px 28px, auto;
  color: var(--text);
  min-width: 1080px;
  max-width: 100%;
  overflow-x: hidden;
}

.app-shell {
  display: grid;
  grid-template-columns: 236px 1fr;
  grid-template-rows: auto 1fr auto;
  min-height: 100vh;
}

.sidebar {
  background: #101820;
  color: #f8fafc;
  padding: 22px 18px;
  border-right: 1px solid #0b1117;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}

.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 28px;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border: 1px solid #334452;
  border-radius: 6px;
  background: #17232d;
  color: #9ee7dc;
  font-size: 13px;
  font-weight: 800;
  box-shadow: inset 0 0 18px rgba(158, 231, 220, 0.08);
}

.brand span,
.label,
.metric span,
.next-action span,
.command-box span,
.section-heading span {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  text-transform: uppercase;
}

.brand span { color: #91a2af; margin-top: 2px; }

nav { display: grid; gap: 4px; }

nav a {
  color: #c8d3dc;
  text-decoration: none;
  padding: 10px 10px;
  border-radius: 6px;
  border-left: 3px solid transparent;
  font-size: var(--type-body);
  transition: background 0.16s ease, color 0.16s ease, border-color 0.16s ease, transform 0.16s ease;
}

nav a:hover { background: #182633; color: #ffffff; transform: translateX(2px); }

nav a.active {
  background: #1a2a3a;
  color: #ffffff;
  border-left-color: var(--teal);
}

main {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 100vh;
}

#orchestrator { order: 1; }
#command { order: 2; }
#map { order: 3; }
#lanes { order: 4; }
#goals { order: 5; }
#specs { order: 6; }
#gates { order: 7; }
#attention { order: 8; }
#projects { order: 9; }
#inbox { order: 10; }
#promotion { order: 11; }
#actions { order: 12; }
#evidence { order: 13; }
#context { order: 14; }

.page-hidden {
  display: none !important;
}

.topbar,
.orchestrator-stage,
.command-grid,
.map-strip,
.context-bar,
.action-strip,
.goal-strip,
.spec-grid,
.workspace,
.gate-strip,
.attention-strip,
.project-strip,
.inbox-strip,
.desk-grid,
.evidence-strip {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow);
  min-width: 0;
}

.topbar {
  min-height: 94px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 18px;
  min-width: 0;
  position: relative;
  overflow: hidden;
}

.topbar::before {
  content: "";
  position: absolute;
  inset: 0 0 auto;
  height: 3px;
  background: linear-gradient(90deg, var(--teal), var(--indigo), var(--amber));
}

.topbar::after {
  content: "";
  position: absolute;
  inset: auto 16px 12px auto;
  width: 94px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(15, 118, 110, 0.58));
  transform-origin: right center;
  animation: signal-sweep 2.8s ease-in-out infinite;
}

.topbar-left {
  display: grid;
  gap: 10px;
  min-width: 0;
}

h1, h2, p { margin: 0; }

h1 {
  font-size: var(--type-h1);
  line-height: 1.25;
  max-width: 760px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

h2 { font-size: var(--type-h1); line-height: 1.3; margin: 12px 0; }

.topbar-right { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }

.filter-control {
  display: grid;
  grid-template-columns: auto minmax(180px, 260px) auto;
  align-items: center;
  gap: 7px;
  padding: 5px 7px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
}

.filter-control span {
  color: var(--muted);
  font-size: var(--type-caption);
  font-weight: 800;
  text-transform: uppercase;
}

.filter-control input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text);
  font: 700 var(--type-mono) var(--font-mono);
}

.filter-control input::placeholder {
  color: #8a949d;
}

.filter-control:focus-within {
  border-color: var(--teal);
  box-shadow: 0 0 0 3px var(--teal-soft);
}

.filter-control strong {
  min-width: 42px;
  padding: 3px 6px;
  border-radius: 999px;
  background: var(--panel);
  color: var(--teal);
  font-size: var(--type-caption);
  text-align: center;
}

.metrics-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  color: var(--muted);
  font-size: var(--type-caption);
  font-weight: 800;
  text-transform: uppercase;
}

.metrics-row strong {
  color: var(--text);
  font-size: var(--type-h2);
  margin-left: 4px;
}

.metrics-row .attention strong { color: var(--red); }
.metrics-row .verify strong { color: var(--amber); }
.metric-action {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: min(540px, 100%);
  text-transform: none;
}

.pill,
button {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
  color: var(--text);
  font-size: var(--type-mono);
  font-weight: 700;
  min-height: 32px;
  padding: 7px 10px;
}

button { cursor: pointer; background: var(--text); color: #ffffff; border-color: var(--text); }

.command-grid {
  display: grid;
  grid-template-columns: repeat(4, 126px) 1fr;
  gap: 1px;
  overflow: hidden;
}

.metric,
.next-action {
  min-height: 88px;
  padding: 15px;
  border-right: 1px solid var(--border);
  min-width: 0;
}

.metric strong {
  display: block;
  margin-top: 10px;
  font-size: var(--type-display);
  line-height: 1;
}

.metric.attention strong { color: var(--red); }
.metric.verify strong { color: var(--amber); }

code {
  display: block;
  margin-top: 10px;
  padding: 10px;
  background: #101820;
  color: #d8f5ef;
  border-radius: 6px;
  font-family: var(--font-mono);
  font-size: var(--type-mono);
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.metrics-row code {
  display: inline-block;
  max-width: min(560px, 52vw);
  margin: 0;
  padding: 4px 7px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
  box-shadow: 0 0 0 1px rgba(158, 231, 220, 0.12), 0 8px 18px rgba(16, 24, 32, 0.16);
  transition: box-shadow 0.18s ease, transform 0.18s ease;
}

.metrics-row code:focus,
.metrics-row code:hover {
  transform: translateY(-1px);
  box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.34), 0 12px 26px rgba(16, 24, 32, 0.18);
}

.workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 336px;
  flex: 1 1 auto;
  min-height: 560px;
  overflow: hidden;
  border-top-color: var(--border-strong);
}

.lane-board {
  display: grid;
  grid-template-columns: repeat(5, minmax(176px, 1fr));
  gap: 0;
  overflow-x: auto;
}

.lane {
  min-width: 176px;
  border-right: 1px solid var(--border);
  background: #fbfcfd;
}

.lane-header {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #fbfcfd;
  padding: 13px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 3px solid var(--indigo);
}

.lane-header strong { font-size: var(--type-body); }
.lane-header span { color: var(--muted); font-size: var(--type-mono); font-weight: 800; }

.lane:nth-child(1) .lane-header { border-top-color: var(--red); background: var(--red-soft); }
.lane:nth-child(3) .lane-header { border-top-color: var(--amber); background: var(--amber-soft); }
.lane:nth-child(4) .lane-header { border-top-color: var(--green); background: var(--green-soft); }

.task-row {
  display: block;
  width: calc(100% - 20px);
  margin: 10px;
  padding: 11px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  cursor: pointer;
  text-align: left;
  min-height: 0;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, opacity 0.2s ease, transform 0.15s ease;
}

.task-row.dimmed {
  opacity: 0.35;
}

.task-row:hover,
.task-row.selected {
  border-color: var(--teal);
  box-shadow: 0 0 0 3px var(--teal-soft);
}

.task-row:hover { transform: translateY(-1px); }

@keyframes pulse-teal {
  0% { box-shadow: 0 0 0 3px var(--teal-soft); }
  50% { box-shadow: 0 0 0 6px var(--teal-soft); }
  100% { box-shadow: 0 0 0 3px var(--teal-soft); }
}

.task-row.selected {
  animation: pulse-teal 0.6s ease;
}

.task-row strong { display: block; font-size: var(--type-body); line-height: 1.3; }
.task-row p { color: var(--muted); font-size: var(--type-mono); line-height: 1.35; margin-top: 7px; }

.work-status-card,
.event-status-card {
  display: grid;
  gap: 4px;
  margin-top: 8px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-2);
}

.work-status-card span,
.event-status-card span {
  color: var(--muted);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.work-status-card strong,
.event-status-card strong {
  color: var(--text);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.task-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 9px;
}

.task-meta span {
  padding: 3px 6px;
  border-radius: 5px;
  background: var(--panel-2);
  color: var(--muted);
  font-size: var(--type-caption);
  font-weight: 700;
  max-width: 100%;
  min-width: 0;
  overflow-wrap: anywhere;
}

.task-meta span:last-child {
  flex-basis: 100%;
}

.inspector {
  border-left: 1px solid var(--border);
  padding: 16px;
  background: var(--panel);
  min-width: 0;
  transform: translateX(0);
  transition: box-shadow 0.22s ease, transform 0.22s ease;
}

.inspector:focus-within {
  box-shadow: inset 3px 0 0 var(--teal);
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.section-heading strong { font-size: var(--type-mono); color: var(--teal); }

.accordion-trigger strong {
  min-width: 32px;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--teal-soft);
  text-align: center;
}

.accordion-trigger {
  width: 100%;
  min-height: 42px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text);
  cursor: pointer;
}

.accordion-trigger::after {
  content: "›";
  color: var(--muted);
  font-size: 18px;
  line-height: 1;
  transition: transform 0.22s ease;
}

.accordion-trigger:hover span {
  color: var(--text);
}

.accordion-trigger:hover::after {
  transform: translateX(2px);
}

.expanded > .accordion-trigger::after,
.desk-grid.expanded .accordion-trigger::after {
  transform: rotate(90deg);
}

.collapsed > .section-body,
.desk-grid.collapsed .section-body {
  display: none;
}

.goal-strip,
.spec-grid,
.gate-strip,
.inbox-strip,
.action-strip,
.evidence-strip,
.desk-grid {
  overflow: hidden;
  max-height: 54px;
  transition: max-height 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.goal-strip,
.spec-grid,
.gate-strip,
.inbox-strip,
.action-strip,
.evidence-strip,
.desk-grid,
.map-node,
.task-row,
.project-card {
  will-change: transform;
}

.goal-strip.expanded,
.spec-grid.expanded,
.gate-strip.expanded,
.inbox-strip.expanded,
.action-strip.expanded,
.evidence-strip.expanded,
.desk-grid.expanded {
  max-height: 1200px;
}

.project-strip,
.map-strip,
.workspace {
  max-height: none;
}

dl {
  display: grid;
  grid-template-columns: 98px 1fr;
  gap: 8px 10px;
  margin: 0 0 14px;
}

dt { color: var(--muted); font-size: var(--type-mono); font-weight: 700; }
dd { margin: 0; font-size: var(--type-mono); overflow-wrap: anywhere; }

.desk-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
}

.desk-grid > div,
.map-strip,
.context-bar,
.action-strip,
.goal-strip,
.spec-grid,
.gate-strip,
.attention-strip,
.project-strip,
.inbox-strip,
.evidence-strip { padding: 16px; }
.desk-grid > div + div { border-left: 1px solid var(--border); }

.context-bar {
  display: flex;
  max-height: 54px;
  transition: max-height 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.list-stack,
.action-list,
.detail-summary,
.detail-events,
.inbox-list,
.evidence-list {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.action-list {
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}

.map-list {
  display: grid;
  grid-template-columns: repeat(6, minmax(130px, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.context-bar {
  display: none;
}

.context-bar span {
  color: var(--muted);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.context-bar strong {
  display: block;
  margin-top: 3px;
  font-size: 14px;
}

.context-bar p {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.35;
  margin-top: 3px;
  overflow-wrap: anywhere;
}

.context-bar button {
  flex: 0 0 auto;
}

.map-node {
  display: grid;
  align-content: space-between;
  min-height: 116px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 11px;
  color: var(--text);
  text-decoration: none;
  min-width: 0;
  position: relative;
  overflow: hidden;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease, background 0.16s ease;
}

.map-node::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(15, 118, 110, 0.12), transparent 44%);
  opacity: 0;
  transition: opacity 0.18s ease;
}

.map-node:hover {
  border-color: var(--teal);
  box-shadow: 0 0 0 3px var(--teal-soft);
  transform: translateY(-2px);
}

.map-node:hover::before,
.map-node.selected::before {
  opacity: 1;
}

.map-node:focus-visible,
.goal-select:focus-visible,
.task-row:focus-visible,
.project-card:focus-visible,
button:focus-visible {
  outline: 3px solid var(--teal);
  outline-offset: 2px;
}

.map-node.selected {
  border-color: var(--teal);
  background: var(--teal-soft);
}

.map-node.attention {
  border-color: #f2b8ad;
  background: #fffaf8;
}

.map-node.verify {
  border-color: #f1d594;
  background: #fffdf7;
}

.map-node span {
  color: var(--muted);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.map-node strong {
  display: block;
  margin-top: 6px;
  font-size: 22px;
  line-height: 1;
  position: relative;
}

.map-node p {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.35;
  margin-top: 9px;
  overflow-wrap: anywhere;
  position: relative;
}

.action-item {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 10px;
  min-width: 0;
  transition: border-color 0.16s ease, transform 0.16s ease, box-shadow 0.16s ease;
}

.action-item:hover,
.action-item.selected {
  border-color: var(--teal);
  box-shadow: 0 8px 22px rgba(23, 32, 38, 0.08);
  transform: translateY(-1px);
}

.action-item.selected {
  background: linear-gradient(180deg, #fbfffe, var(--teal-soft));
}

.action-item strong {
  display: block;
  font-size: 13px;
}

.action-item .label {
  margin-top: 4px;
}

.action-item code {
  margin-top: 8px;
}

.action-preview {
  margin-top: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 12px;
}

.action-preview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.action-preview-grid > div {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  padding: 8px;
  min-width: 0;
}

.action-preview-grid span {
  display: block;
  color: var(--muted);
  font-size: var(--type-caption);
  font-weight: 800;
  text-transform: uppercase;
}

.action-preview-grid strong {
  display: block;
  margin-top: 4px;
  font-size: var(--type-body);
  overflow-wrap: anywhere;
}

.action-preview p {
  color: var(--muted);
  font-size: var(--type-mono);
  line-height: 1.4;
  margin-top: 8px;
}

.action-execute-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
}

.action-run-button {
  border-color: rgba(15, 118, 110, 0.48);
  background: var(--teal);
  color: #ffffff;
}

.action-run-button[disabled] {
  cursor: wait;
  opacity: 0.72;
}

.action-result {
  margin-top: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  padding: 10px;
}

.action-result strong {
  display: block;
  font-size: var(--type-body);
}

.action-result pre {
  max-height: 220px;
  margin: 8px 0 0;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.detail-panel {
  margin-top: 16px;
  border-top: 1px solid var(--border);
  padding-top: 14px;
}

.detail-item,
.event-item {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 9px;
  min-width: 0;
  font-size: 12px;
}

.detail-item strong,
.event-item strong {
  display: block;
  margin-bottom: 5px;
  font-size: 12px;
}

.detail-item span,
.event-item span {
  color: var(--muted);
  overflow-wrap: anywhere;
}

.inbox-list {
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

.attention-list {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.attention-card {
  display: grid;
  gap: 8px;
  min-width: 0;
  min-height: 104px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  color: var(--text);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.attention-card:hover {
  border-color: var(--teal);
  box-shadow: 0 8px 22px rgba(23, 32, 38, 0.08);
  transform: translateY(-1px);
}

.attention-card.urgent {
  border-color: #f2b8ad;
  background: #fffaf8;
}

.attention-card.ready {
  border-color: #a7e3b8;
  background: #f7fff9;
}

.attention-card.verify {
  border-color: #f1d594;
  background: #fffdf7;
}

.attention-card span {
  color: var(--muted);
  font-size: var(--type-caption);
  font-weight: 800;
  text-transform: uppercase;
}

.attention-card strong {
  display: block;
  font-size: 26px;
  line-height: 1;
}

.attention-card p {
  color: var(--muted);
  font-size: var(--type-mono);
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.goal-board-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.goal-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 12px;
  min-width: 0;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.goal-card:hover,
.spec-card:hover,
.gate-card:hover,
.project-card:hover {
  border-color: var(--border-strong);
  box-shadow: 0 8px 24px rgba(23, 32, 38, 0.07);
}

.goal-card h3 {
  margin: 0 0 9px;
  font-size: 15px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.goal-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin-top: 10px;
}

.goal-metric {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  padding: 8px;
  min-width: 0;
}

.goal-metric span {
  color: var(--muted);
  font-size: 10px;
  font-weight: 800;
  text-transform: uppercase;
}

.goal-metric strong {
  display: block;
  margin-top: 4px;
  font-size: 18px;
}

.goal-section {
  margin-top: 12px;
  display: grid;
  gap: 7px;
}

.goal-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  border-top: 1px solid var(--border);
  padding-top: 8px;
  color: var(--muted);
  font-size: 12px;
}

.goal-select {
  width: 100%;
  color: var(--muted);
  background: transparent;
  border: 0;
  border-top: 1px solid var(--border);
  border-radius: 0;
  padding: 8px 0 0;
  text-align: left;
  cursor: pointer;
}

.goal-select:hover,
.goal-select.selected {
  color: var(--text);
}

.goal-select.selected {
  border-top-color: var(--teal);
}

.goal-row span,
.goal-row strong {
  min-width: 0;
  overflow-wrap: anywhere;
}

.goal-page-card {
  display: grid;
  gap: 14px;
}

.goal-page-top {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(180px, 260px);
  gap: 16px;
  align-items: start;
}

.goal-page-top p {
  color: var(--muted);
  font-size: var(--type-body);
  line-height: 1.45;
}

.goal-progress-summary {
  display: grid;
  gap: 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  padding: 10px;
}

.goal-progress-summary strong {
  font-size: 22px;
}

.goal-progress-summary span {
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.goal-progress-summary i {
  display: block;
  height: 7px;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--teal) var(--goal-progress), var(--border) 0);
}

.goal-page-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);
  gap: 14px;
  align-items: start;
}

.goal-lane-panel,
.goal-next-panel {
  display: grid;
  gap: 10px;
  min-width: 0;
}

.goal-panel-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: var(--muted);
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0;
  text-transform: uppercase;
}

.goal-panel-heading strong {
  color: var(--teal);
}

.goal-lane-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 10px;
}

.goal-lane-row {
  display: grid;
  gap: 7px;
  min-height: 148px;
  border: 1px solid var(--border);
  border-top: 3px solid var(--border-strong);
  border-radius: 6px;
  background: var(--panel);
  padding: 12px;
}

.goal-lane-row.done { border-top-color: var(--green); }
.goal-lane-row.ready { border-top-color: var(--teal); }
.goal-lane-row.blocked { border-top-color: var(--red); }

.goal-lane-row span,
.goal-lane-row small,
.goal-lane-row em,
.goal-lane-row p {
  min-width: 0;
  overflow-wrap: anywhere;
}

.goal-lane-row span,
.goal-lane-row small,
.goal-lane-row em {
  color: var(--muted);
  font-size: 11px;
  font-style: normal;
  font-weight: 800;
  text-transform: uppercase;
}

.goal-lane-row strong {
  color: var(--text);
  font-size: 14px;
  line-height: 1.25;
}

.goal-lane-row p {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
}

.goal-next-panel code {
  display: block;
  overflow-wrap: anywhere;
}

.goal-mini-list {
  display: grid;
  gap: 7px;
}

.goal-mini-list > span {
  color: var(--muted);
  font-size: 11px;
  font-weight: 900;
  text-transform: uppercase;
}

.goal-mini-row {
  display: grid;
  gap: 4px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  padding: 9px;
}

.inbox-item {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 11px;
  min-width: 0;
  transition: border-color 0.16s ease, transform 0.16s ease;
}

.inbox-item:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
}

.inbox-item.urgent {
  border-color: #f2b8ad;
  background: #fffaf8;
}

.inbox-item strong {
  display: block;
  font-size: 13px;
  line-height: 1.3;
}

.inbox-item p {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
  margin-top: 7px;
  overflow-wrap: anywhere;
}

.spec-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.spec-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 12px;
  min-width: 0;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.spec-card h3 {
  margin: 0 0 8px;
  font-size: 14px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.spec-slices {
  display: grid;
  gap: 6px;
  margin-top: 10px;
}

.spec-references {
  display: grid;
  gap: 6px;
  margin-top: 10px;
}

.spec-reference {
  display: grid;
  gap: 3px;
  border-top: 1px solid var(--border);
  padding-top: 7px;
  color: var(--muted);
  font-size: var(--type-mono);
  min-width: 0;
}

.spec-reference strong,
.spec-reference span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.spec-reference strong {
  color: var(--text);
  font-size: var(--type-body);
}

.spec-reference-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.spec-reference-meta span {
  padding: 2px 6px;
  border-radius: 999px;
  background: var(--panel-2);
  font-size: var(--type-caption);
  font-weight: 800;
  text-transform: uppercase;
}

.spec-reference-meta .missing {
  background: var(--red-soft);
  color: var(--red);
}

.spec-slice,
.gate-item {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  border-top: 1px solid var(--border);
  padding-top: 7px;
  color: var(--muted);
  font-size: 12px;
}

.spec-slice span,
.gate-item span {
  min-width: 0;
  overflow-wrap: anywhere;
}

.spec-slice strong,
.gate-item strong {
  flex: 0 0 auto;
}

.gate-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.gate-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 11px;
}

.progress-page {
  display: grid;
  gap: 14px;
  margin-top: 12px;
}

.progress-summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.progress-summary-card {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 12px;
}

.progress-summary-card span {
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.progress-summary-card strong {
  display: block;
  margin-top: 4px;
  color: var(--text);
  font-size: 24px;
}

.progress-checklist {
  grid-template-columns: 1fr;
}

.progress-task-row {
  display: grid;
  grid-template-columns: minmax(180px, 0.8fr) minmax(0, 1.2fr) minmax(190px, 0.8fr);
  gap: 14px;
  align-items: start;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 14px;
}

.progress-task-row.ready { border-left: 4px solid var(--green); }
.progress-task-row.blocked { border-left: 4px solid var(--red); }
.progress-task-row.active { border-left: 4px solid var(--teal); }
.progress-task-row.waiting { border-left: 4px solid var(--amber); }

.progress-task-main,
.progress-next-panel {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.progress-task-main strong {
  color: var(--text);
  font-size: 15px;
  overflow-wrap: anywhere;
}

.progress-task-main span,
.progress-next-panel span {
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.progress-task-main p,
.progress-next-panel p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.progress-step-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  min-width: 0;
}

.progress-step {
  display: grid;
  gap: 6px;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  padding: 10px;
}

.progress-step i {
  display: block;
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--border-strong);
}

.progress-step.done i { background: var(--green); }
.progress-step.current i { background: var(--teal); }
.progress-step.pending i { background: var(--border-strong); }
.progress-step.skipped i {
  background: var(--muted);
  opacity: 0.55;
}

.progress-step strong {
  color: var(--text);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.progress-step small {
  color: var(--muted);
  font-size: 11px;
}

.progress-next-panel code {
  display: block;
  max-width: 100%;
  white-space: pre-wrap;
  word-break: break-word;
}

.project-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.project-stat {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 10px;
  min-width: 0;
}

.project-stat span {
  color: var(--muted);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}

.project-stat strong {
  display: block;
  margin-top: 6px;
  font-size: 20px;
}

.project-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.project-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fbfcfd;
  padding: 11px;
  min-width: 0;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.project-card:hover,
.project-card.selected {
  border-color: var(--teal);
  box-shadow: 0 0 0 3px var(--teal-soft);
}

.project-card.missing {
  cursor: default;
}

.project-card h3 {
  margin: 0 0 8px;
  font-size: 14px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.project-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding-top: 7px;
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 12px;
}

.project-row span,
.project-row strong {
  min-width: 0;
  overflow-wrap: anywhere;
}

.gate-steps {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 4px;
  margin-top: 9px;
}

.gate-dot {
  height: 6px;
  border-radius: 999px;
  background: var(--border);
}

.gate-dot.done { background: var(--teal); }

.list-item,
.evidence-item {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px;
  background: #fbfcfd;
  font-size: 12px;
}

@keyframes signal-sweep {
  0%, 100% { transform: scaleX(0.28); opacity: 0.25; }
  50% { transform: scaleX(1); opacity: 0.8; }
}

.list-item strong,
.evidence-item strong {
  display: block;
  margin-bottom: 5px;
  font-size: 13px;
}

.empty {
  color: var(--muted);
  font-size: 13px;
  padding: 12px 0;
}

@media (max-width: 900px) {
  body { min-width: 0; }
  .app-shell { grid-template-columns: 1fr; }
  .sidebar { display: none; }
  main { padding: 14px; width: 100%; overflow: hidden; }
  .topbar {
    display: grid;
    gap: 12px;
    align-items: start;
    width: 100%;
  }
  .topbar h1 {
    max-width: 100%;
    white-space: normal;
    word-break: break-word;
    overflow-wrap: anywhere;
    overflow: visible;
    text-overflow: clip;
    font-size: 17px;
  }
  .topbar-right { flex-wrap: wrap; min-width: 0; }
  .command-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .next-action { grid-column: 1 / -1; }
  .next-action code { max-width: 100%; overflow-x: hidden; }
  .metric,
  .next-action { border-right: 0; border-bottom: 1px solid var(--border); }
  .context-bar { align-items: start; }
  .map-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .action-list { grid-template-columns: 1fr; }
  .action-preview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .attention-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .inbox-list { grid-template-columns: 1fr; }
  .goal-board-list { grid-template-columns: 1fr; }
  .goal-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .spec-list { grid-template-columns: 1fr; }
  .project-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .project-list { grid-template-columns: 1fr; }
  .spec-slice,
  .goal-row,
  .gate-item,
  .project-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
  }
  .spec-slice strong,
  .goal-row strong,
  .gate-item strong,
  .project-row strong {
    justify-self: start;
  }
  .workspace { grid-template-columns: 1fr; }
  .lane-board { grid-template-columns: 1fr; overflow-x: visible; }
  .inspector { border-left: 0; border-top: 1px solid var(--border); }
  .desk-grid { grid-template-columns: 1fr; }
  .desk-grid > div + div { border-left: 0; border-top: 1px solid var(--border); }
}

/* Dopamine-rich mission-control skin inspired by the Hermes operating room. */
:root {
  --bg: #070711;
  --panel: rgba(25, 24, 42, 0.78);
  --panel-2: rgba(45, 39, 67, 0.72);
  --panel-3: rgba(78, 62, 109, 0.28);
  --text: #fbf8ff;
  --muted: #9ba2bb;
  --border: rgba(168, 156, 222, 0.18);
  --border-strong: rgba(133, 238, 218, 0.48);
  --teal: #66f0d1;
  --teal-soft: rgba(102, 240, 209, 0.13);
  --amber: #ffd46d;
  --amber-soft: rgba(255, 212, 109, 0.14);
  --red: #ff6fa8;
  --red-soft: rgba(255, 111, 168, 0.14);
  --indigo: #a580ff;
  --indigo-soft: rgba(165, 128, 255, 0.16);
  --green: #79f2b2;
  --green-soft: rgba(121, 242, 178, 0.12);
  --cyan: #8fd8ff;
  --pink: #ea70d8;
  --shadow: 0 28px 70px rgba(0, 0, 0, 0.38), inset 0 1px 0 rgba(255, 255, 255, 0.04);
  --glow: 0 0 28px rgba(102, 240, 209, 0.16), 0 0 60px rgba(165, 128, 255, 0.12);
  --type-display: 40px;
  --type-h1: 42px;
  --type-h2: 18px;
  --type-body: 13px;
  --type-caption: 10px;
  --type-mono: 11px;
  --font-ui: "Avenir Next", "Manrope", "SF Pro Display", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "Berkeley Mono", "SFMono-Regular", "JetBrains Mono", Consolas, monospace;
}

html {
  background: var(--bg);
  scroll-behavior: smooth;
}

body {
  position: relative;
  min-width: 0;
  background:
    radial-gradient(circle at 10% 8%, rgba(111, 59, 190, 0.48), transparent 24rem),
    radial-gradient(circle at 92% 76%, rgba(78, 164, 207, 0.28), transparent 30rem),
    radial-gradient(circle at 52% 38%, rgba(18, 22, 39, 0.92), transparent 34rem),
    linear-gradient(135deg, #090814 0%, #101122 48%, #071016 100%);
  color: var(--text);
  text-rendering: geometricPrecision;
}

body::before,
body::after {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
}

body::before {
  z-index: 0;
  background:
    radial-gradient(circle, rgba(255, 255, 255, 0.18) 0 1px, transparent 1px),
    linear-gradient(90deg, rgba(168, 156, 222, 0.05) 1px, transparent 1px),
    linear-gradient(180deg, rgba(168, 156, 222, 0.04) 1px, transparent 1px);
  background-size: 36px 36px, 72px 72px, 72px 72px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.86), rgba(0, 0, 0, 0.18) 74%, transparent);
  opacity: 0.34;
}

body::after {
  z-index: 0;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.05), transparent 18%),
    repeating-linear-gradient(180deg, rgba(255, 255, 255, 0.025) 0 1px, transparent 1px 4px);
  mix-blend-mode: screen;
  opacity: 0.18;
}

* {
  scrollbar-color: rgba(143, 216, 255, 0.45) rgba(255, 255, 255, 0.04);
}

::selection {
  background: rgba(102, 240, 209, 0.28);
  color: #ffffff;
}

.app-shell {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: auto 1fr;
  min-height: 100vh;
}

.sidebar {
  position: sticky;
  top: 0;
  z-index: 10;
  height: auto;
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr);
  align-items: center;
  gap: 18px;
  padding: 12px 34px;
  overflow: visible;
  background:
    linear-gradient(180deg, rgba(12, 12, 25, 0.88), rgba(12, 12, 25, 0.58)),
    rgba(12, 12, 25, 0.72);
  border-right: 0;
  border-bottom: 1px solid rgba(168, 156, 222, 0.15);
  box-shadow: 0 14px 45px rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(22px);
}

.brand {
  min-width: 0;
  margin-bottom: 0;
  color: var(--text);
}

.brand strong {
  display: block;
  font-size: 20px;
  line-height: 1;
  color: #ffffff;
}

.brand span,
.label,
.metric span,
.next-action span,
.command-box span,
.section-heading span,
.section-heading output {
  color: var(--muted);
  font-size: var(--type-caption);
  font-weight: 900;
  letter-spacing: 0;
  text-transform: uppercase;
}

.brand span {
  color: rgba(197, 203, 229, 0.72);
  font-family: var(--font-mono);
}

.brand-mark {
  position: relative;
  width: 34px;
  height: 34px;
  border: 1px solid rgba(143, 216, 255, 0.42);
  border-radius: 50%;
  background:
    radial-gradient(circle at 50% 50%, rgba(102, 240, 209, 0.92) 0 4px, transparent 5px),
    conic-gradient(from 160deg, #a580ff, #66f0d1, #8fd8ff, #a580ff);
  color: transparent;
  box-shadow: 0 0 18px rgba(102, 240, 209, 0.42), inset 0 0 0 8px rgba(8, 8, 18, 0.92);
}

.brand-mark::after {
  content: "";
  position: absolute;
  inset: 7px;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 50%;
}

nav {
  justify-self: center;
  display: flex;
  max-width: min(1020px, 82vw);
  gap: 2px;
  padding: 5px;
  overflow-x: auto;
  border: 1px solid rgba(168, 156, 222, 0.15);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.045);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06), 0 16px 32px rgba(0, 0, 0, 0.25);
}

nav ul {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}

nav li {
  flex: 0 0 auto;
}

nav a {
  flex: 0 0 auto;
  padding: 8px 14px;
  border: 0;
  border-radius: 999px;
  color: rgba(232, 232, 246, 0.76);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  line-height: 1;
  text-transform: uppercase;
  transition: background 0.18s ease, color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

nav a:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #ffffff;
  transform: translateY(-1px);
}

nav a.active {
  background: #f4f2ff;
  color: #19142d;
  border-left-color: transparent;
  box-shadow: 0 0 22px rgba(255, 255, 255, 0.22);
}

main {
  width: min(1320px, calc(100vw - 48px));
  margin: 0 auto;
  padding: 18px 0 72px;
  gap: 18px;
}

h1,
h2,
h3,
p {
  margin: 0;
}

h1 {
  max-width: min(760px, 100%);
  color: #ffffff;
  font-size: var(--type-h1);
  font-weight: 760;
  line-height: 0.98;
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  text-shadow: 0 0 24px rgba(255, 255, 255, 0.12);
}

h2 {
  color: #ffffff;
  font-size: var(--type-h2);
  line-height: 1.2;
}

.topbar,
.orchestrator-stage,
.map-strip,
.context-bar,
.action-strip,
.goal-strip,
.spec-grid,
.workspace,
.gate-strip,
.attention-strip,
.project-strip,
.inbox-strip,
.desk-grid,
.evidence-strip {
  position: relative;
  overflow: hidden;
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.075), rgba(255, 255, 255, 0.025)),
    linear-gradient(90deg, rgba(91, 68, 142, 0.2), rgba(23, 35, 56, 0.36)),
    var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: var(--shadow);
  backdrop-filter: blur(18px);
}

.topbar {
  min-height: 0;
  align-items: stretch;
  padding: 16px 18px;
  gap: 16px;
  background:
    radial-gradient(circle at 5% 0%, rgba(118, 78, 211, 0.48), transparent 20rem),
    radial-gradient(circle at 82% 24%, rgba(62, 151, 190, 0.25), transparent 24rem),
    linear-gradient(135deg, rgba(39, 30, 66, 0.72), rgba(17, 20, 36, 0.8)),
    var(--panel);
}

.topbar::before {
  inset: 0 0 auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--teal), var(--indigo), var(--pink), transparent);
  box-shadow: 0 0 22px rgba(102, 240, 209, 0.4);
}

.topbar::after {
  inset: auto 0 0;
  width: 100%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(143, 216, 255, 0.7), transparent);
  animation: signal-sweep-wide 4s ease-in-out infinite;
}

.orchestrator-stage {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr) 300px;
  gap: 0;
  min-height: min(570px, calc(100vh - 104px));
  border-top-color: rgba(102, 240, 209, 0.68);
  background:
    radial-gradient(circle at 8% 24%, rgba(165, 128, 255, 0.3), transparent 22rem),
    radial-gradient(circle at 88% 18%, rgba(102, 240, 209, 0.13), transparent 22rem),
    linear-gradient(135deg, rgba(33, 27, 55, 0.82), rgba(13, 15, 28, 0.84)),
    var(--panel);
}

.orchestrator-agents,
.orchestrator-core,
.orchestrator-health {
  position: relative;
  min-width: 0;
  padding: 22px;
}

.orchestrator-agents {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 14px;
  min-height: 0;
  border-right: 1px solid rgba(168, 156, 222, 0.12);
  overflow: hidden;
}

.agent-progress-list {
  display: grid;
  align-content: start;
  gap: 10px;
  min-height: 0;
}

.agent-progress-row {
  --agent-accent: var(--cyan);
  --agent-glow: rgba(143, 216, 255, 0.24);
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 10px 12px;
  align-items: center;
  width: 100%;
  min-height: 78px;
  padding: 12px;
  border: 1px solid rgba(168, 156, 222, 0.13);
  border-left: 2px solid var(--agent-accent);
  border-radius: 8px;
  background:
    radial-gradient(circle at 88% 20%, var(--agent-glow), transparent 7rem),
    rgba(255, 255, 255, 0.04);
  color: inherit;
  text-align: left;
}

.agent-progress-row.active { --agent-accent: var(--teal); --agent-glow: rgba(102, 240, 209, 0.2); }
.agent-progress-row.idle { --agent-accent: var(--amber); --agent-glow: rgba(255, 212, 109, 0.16); }
.agent-progress-row.blocked { --agent-accent: var(--red); --agent-glow: rgba(255, 111, 168, 0.2); }
.agent-progress-row.complete { --agent-accent: var(--green); --agent-glow: rgba(121, 242, 178, 0.18); }

.agent-progress-code {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.07);
  color: var(--agent-accent);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  box-shadow: 0 0 18px var(--agent-glow), inset 0 0 0 1px rgba(255, 255, 255, 0.07);
}

.agent-progress-main {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.agent-progress-top,
.agent-progress-meta {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
}

.agent-progress-top strong {
  color: #ffffff;
  font-size: 13px;
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.agent-progress-top em,
.agent-progress-meta {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 9px;
  font-style: normal;
  font-weight: 900;
  text-transform: uppercase;
}

.agent-progress-top em {
  flex: 0 0 auto;
  color: var(--agent-accent);
}

.agent-progress-track {
  position: relative;
  height: 9px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}

.agent-progress-track i {
  display: block;
  width: var(--progress, 0%);
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--agent-accent), rgba(255, 255, 255, 0.82));
  box-shadow: 0 0 16px var(--agent-glow);
}

.agent-progress-meta span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.orchestrator-core {
  display: grid;
  align-content: center;
  gap: 14px;
}

.orchestrator-kicker {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 14px;
  align-items: center;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(168, 156, 222, 0.12);
}

.orchestrator-kicker span,
.orchestrator-kicker strong,
.orchestrator-label,
.orchestrator-command span,
.mission-feed .section-heading span,
.mission-feed .section-heading output,
.orchestrator-counters span,
.orchestrator-mini span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 900;
  text-transform: uppercase;
}

.orchestrator-kicker span:first-child,
.orchestrator-label {
  color: var(--teal);
}

.orchestrator-kicker strong {
  color: rgba(245, 244, 255, 0.76);
}

.orchestrator-core h2 {
  color: #ffffff;
  font-size: 30px;
  line-height: 1.08;
  overflow-wrap: anywhere;
}

.orchestrator-core p {
  max-width: 760px;
  color: rgba(224, 225, 246, 0.72);
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.orchestrator-command {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 12px;
  border: 1px solid rgba(168, 156, 222, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
}

.orchestrator-command code {
  margin-top: 0;
}

.mission-feed {
  position: relative;
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 12px;
  overflow: hidden;
  border: 1px solid rgba(168, 156, 222, 0.13);
  border-radius: 8px;
  background:
    linear-gradient(135deg, rgba(102, 240, 209, 0.08), transparent 33%),
    rgba(255, 255, 255, 0.035);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045);
}

.mission-feed::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.075), transparent);
  opacity: 0;
  transform: translateX(-70%);
  transition: opacity 220ms ease, transform 700ms ease;
}

.mission-feed:hover::before {
  opacity: 1;
  transform: translateX(70%);
}

.mission-feed .section-heading {
  position: relative;
  z-index: 1;
  margin-bottom: 0;
}

.mission-feed-list {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 7px;
  max-height: 218px;
  min-height: 78px;
  overflow: auto;
  padding-right: 2px;
}

.mission-feed-item {
  --feed-accent: var(--teal);
  --feed-glow: rgba(102, 240, 209, 0.24);
  position: relative;
  display: grid;
  grid-template-columns: 72px minmax(0, 0.78fr) minmax(0, 1.35fr) minmax(90px, 0.62fr);
  gap: 10px;
  align-items: center;
  min-height: 52px;
  padding: 9px 10px 9px 12px;
  overflow: hidden;
  color: inherit;
  text-align: left;
  border: 1px solid rgba(168, 156, 222, 0.1);
  border-left-color: color-mix(in srgb, var(--feed-accent), transparent 18%);
  border-radius: 8px;
  background:
    radial-gradient(circle at 0% 50%, var(--feed-glow), transparent 36%),
    rgba(16, 18, 34, 0.72);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045);
  cursor: pointer;
  transition: transform 160ms ease, border-color 160ms ease, background 160ms ease, box-shadow 160ms ease;
}

.mission-feed-item:hover,
.mission-feed-item:focus-visible {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--feed-accent), transparent 36%);
  box-shadow: 0 0 22px var(--feed-glow), inset 0 1px 0 rgba(255, 255, 255, 0.08);
}

.mission-feed-item::after {
  content: "";
  position: absolute;
  inset: auto 10px 7px 12px;
  height: 1px;
  background: linear-gradient(90deg, var(--feed-accent), transparent);
  opacity: 0.48;
}

.mission-feed-item.urgent { --feed-accent: var(--red); --feed-glow: rgba(255, 111, 168, 0.24); }
.mission-feed-item.ready { --feed-accent: var(--teal); --feed-glow: rgba(102, 240, 209, 0.24); }
.mission-feed-item.verify { --feed-accent: var(--amber); --feed-glow: rgba(255, 212, 109, 0.22); }
.mission-feed-item.evidence { --feed-accent: var(--blue); --feed-glow: rgba(125, 207, 255, 0.22); }
.mission-feed-item.done { --feed-accent: var(--indigo); --feed-glow: rgba(165, 128, 255, 0.22); }

.feed-label,
.feed-command {
  min-width: 0;
  color: var(--feed-accent);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 900;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.feed-title,
.feed-detail,
.feed-command {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feed-title {
  color: #ffffff;
  font-size: 12px;
  font-weight: 900;
}

.feed-detail {
  color: rgba(224, 225, 246, 0.68);
  font-size: 11px;
}

.feed-command {
  justify-self: end;
  max-width: 100%;
  padding: 4px 7px;
  color: rgba(245, 244, 255, 0.84);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.055);
}

.mission-feed-list .empty {
  display: grid;
  min-height: 76px;
  place-items: center;
  text-align: center;
}

.orchestrator-counters {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid rgba(168, 156, 222, 0.12);
  border-radius: 8px;
}

.orchestrator-counters div {
  padding: 12px;
  background: rgba(255, 255, 255, 0.035);
}

.orchestrator-counters output {
  display: block;
  margin-top: 5px;
  color: #ffffff;
  font-size: 22px;
}

.orchestrator-health {
  display: grid;
  align-content: center;
  gap: 16px;
  border-left: 1px solid rgba(168, 156, 222, 0.12);
}

.orchestrator-health-bars {
  display: grid;
  gap: 12px;
}

.health-row {
  display: grid;
  grid-template-columns: 74px minmax(0, 1fr) 42px;
  gap: 10px;
  align-items: center;
}

.health-row span,
.health-row strong {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 900;
  text-transform: uppercase;
}

.health-row div {
  height: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}

.health-row i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--row-accent, var(--teal));
  box-shadow: 0 0 12px var(--row-glow, rgba(102, 240, 209, 0.34));
}

.health-row.teal { --row-accent: var(--teal); --row-glow: rgba(102, 240, 209, 0.36); }
.health-row.gold { --row-accent: var(--amber); --row-glow: rgba(255, 212, 109, 0.36); }
.health-row.pink { --row-accent: var(--red); --row-glow: rgba(255, 111, 168, 0.36); }
.health-row.violet { --row-accent: var(--indigo); --row-glow: rgba(165, 128, 255, 0.36); }

.orchestrator-mini {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  overflow: hidden;
  border: 1px solid rgba(168, 156, 222, 0.12);
  border-radius: 8px;
}

.orchestrator-mini div {
  min-width: 0;
  padding: 12px;
  background: rgba(255, 255, 255, 0.04);
}

.orchestrator-mini output {
  display: block;
  margin-top: 5px;
  color: #ffffff;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.topbar-left {
  flex: 1 1 auto;
  align-content: space-between;
  gap: 20px;
}

.topbar-left .label {
  color: var(--cyan);
}

.topbar-right {
  flex: 0 0 292px;
  align-content: start;
  align-items: stretch;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(94px, 126px)) minmax(280px, 1fr);
  gap: 10px;
  color: var(--muted);
}

.metrics-row > span {
  display: grid;
  min-height: 70px;
  align-content: center;
  padding: 11px 12px;
  border: 1px solid rgba(168, 156, 222, 0.17);
  border-top-color: rgba(102, 240, 209, 0.72);
  border-radius: 8px;
  background:
    radial-gradient(circle at 82% 20%, rgba(143, 216, 255, 0.16), transparent 4rem),
    rgba(255, 255, 255, 0.055);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05), 0 12px 26px rgba(0, 0, 0, 0.18);
}

.metrics-row > span:nth-child(3) {
  border-top-color: rgba(255, 111, 168, 0.82);
}

.metrics-row > span:nth-child(4) {
  border-top-color: rgba(255, 212, 109, 0.86);
}

.metrics-row strong {
  display: block;
  margin: 5px 0 0;
  color: #ffffff;
  font-size: 24px;
  line-height: 1;
}

.metric-action {
  min-width: 0;
  text-transform: uppercase;
  border-top-color: rgba(165, 128, 255, 0.82) !important;
}

.metrics-row code {
  max-width: 100%;
  margin-top: 5px;
  padding: 5px 8px;
  color: var(--teal);
  background: rgba(5, 8, 14, 0.58);
  border: 1px solid rgba(102, 240, 209, 0.14);
  border-radius: 6px;
  box-shadow: none;
}

.pill,
button {
  border: 1px solid rgba(168, 156, 222, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.07);
  color: rgba(245, 244, 255, 0.9);
  font-family: var(--font-mono);
  font-size: var(--type-mono);
  font-weight: 900;
  min-height: 32px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045);
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease, background 0.18s ease;
}

button {
  cursor: pointer;
}

button:hover {
  transform: translateY(-1px);
  border-color: rgba(102, 240, 209, 0.38);
  box-shadow: var(--glow);
}

.filter-control {
  width: 100%;
  grid-template-columns: auto minmax(0, 1fr) auto;
  padding: 6px 8px;
  border-color: rgba(143, 216, 255, 0.22);
  border-radius: 999px;
  background: rgba(5, 8, 14, 0.5);
}

.filter-control input {
  color: #ffffff;
  font: 900 var(--type-mono) var(--font-mono);
}

.filter-control input::placeholder {
  color: rgba(197, 203, 229, 0.48);
}

.filter-control:focus-within {
  border-color: var(--teal);
  box-shadow: 0 0 0 3px rgba(102, 240, 209, 0.12), 0 0 26px rgba(102, 240, 209, 0.16);
}

.filter-control strong {
  min-width: 44px;
  background: rgba(102, 240, 209, 0.12);
  color: var(--teal);
}

.section-heading strong,
.section-heading output,
.accordion-trigger strong {
  color: var(--teal);
}

.accordion-trigger {
  color: var(--text);
}

.accordion-trigger strong {
  background: rgba(102, 240, 209, 0.12);
}

.accordion-trigger::after {
  color: rgba(245, 244, 255, 0.58);
}

.desk-grid > div,
.map-strip,
.context-bar,
.action-strip,
.goal-strip,
.spec-grid,
.gate-strip,
.attention-strip,
.project-strip,
.inbox-strip,
.evidence-strip {
  padding: 18px;
}

.map-strip::before,
.workspace::before,
.attention-strip::before,
.project-strip::before,
.goal-strip::before,
.spec-grid::before,
.gate-strip::before,
.action-strip::before,
.inbox-strip::before,
.evidence-strip::before,
.desk-grid::before {
  content: "";
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  background: linear-gradient(90deg, rgba(102, 240, 209, 0.75), rgba(165, 128, 255, 0.44), transparent);
  opacity: 0.85;
}

.map-list {
  grid-template-columns: repeat(6, minmax(128px, 1fr));
  gap: 10px;
}

.map-node,
.task-row,
.work-status-card,
.event-status-card,
.action-item,
.attention-card,
.goal-card,
.spec-card,
.gate-card,
.progress-summary-card,
.progress-task-row,
.progress-step,
.project-card,
.project-stat,
.list-item,
.evidence-item,
.inbox-item,
.detail-item,
.event-item,
.goal-metric,
.action-preview,
.action-preview-grid > div {
  border: 1px solid rgba(168, 156, 222, 0.16);
  border-radius: 8px;
  background:
    radial-gradient(circle at 88% 16%, rgba(143, 216, 255, 0.12), transparent 5rem),
    linear-gradient(135deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0.025)),
    rgba(18, 18, 32, 0.62);
  color: var(--text);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045);
}

.map-node {
  min-height: 122px;
  padding: 13px;
  border-top-color: rgba(102, 240, 209, 0.72);
}

.map-node::before {
  background: radial-gradient(circle at 18% 12%, rgba(102, 240, 209, 0.2), transparent 4.5rem);
}

.map-node:hover,
.map-node.selected,
.task-row:hover,
.task-row.selected,
.project-card:hover,
.project-card.selected,
.action-item:hover,
.action-item.selected,
.attention-card:hover {
  border-color: rgba(102, 240, 209, 0.62);
  box-shadow: var(--glow), inset 0 1px 0 rgba(255, 255, 255, 0.08);
  transform: translateY(-2px);
}

.map-node.selected {
  background:
    radial-gradient(circle at 88% 16%, rgba(102, 240, 209, 0.22), transparent 5rem),
    linear-gradient(135deg, rgba(102, 240, 209, 0.12), rgba(165, 128, 255, 0.08)),
    rgba(18, 18, 32, 0.76);
}

.map-node.attention,
.attention-card.urgent,
.inbox-item.urgent {
  border-color: rgba(255, 111, 168, 0.48);
  border-top-color: rgba(255, 111, 168, 0.88);
  background:
    radial-gradient(circle at 88% 16%, rgba(255, 111, 168, 0.18), transparent 5rem),
    linear-gradient(135deg, rgba(255, 111, 168, 0.09), rgba(255, 255, 255, 0.025)),
    rgba(18, 18, 32, 0.64);
}

.map-node.verify,
.attention-card.verify,
.attention-card.ready {
  border-color: rgba(255, 212, 109, 0.42);
  border-top-color: rgba(255, 212, 109, 0.88);
  background:
    radial-gradient(circle at 88% 16%, rgba(255, 212, 109, 0.16), transparent 5rem),
    linear-gradient(135deg, rgba(255, 212, 109, 0.08), rgba(255, 255, 255, 0.025)),
    rgba(18, 18, 32, 0.64);
}

.map-node span,
.attention-card span,
.project-stat span,
.goal-metric span,
.action-preview-grid span {
  color: var(--muted);
  font-family: var(--font-mono);
}

.map-node strong {
  color: #ffffff;
  font-size: 28px;
}

.map-node p,
.task-row p,
.attention-card p,
.inbox-item p,
.action-preview p,
.empty {
  color: rgba(197, 203, 229, 0.68);
}

.workspace {
  grid-template-columns: minmax(0, 1fr) 350px;
  min-height: 600px;
  border-top-color: rgba(102, 240, 209, 0.52);
}

.agents-canvas {
  display: grid;
  gap: 16px;
  align-content: start;
  min-width: 0;
  padding: 18px;
  overflow: hidden;
}

.workspace.agents-collapsed {
  grid-template-columns: 1fr;
  min-height: 0;
}

.workspace.agents-collapsed .inspector,
.agents-canvas.collapsed .agent-cards,
.agents-canvas.collapsed .agent-log-panel,
.agents-canvas.collapsed .lane-board {
  display: none;
}

.agents-canvas.collapsed {
  padding: 14px 18px;
}

.agents-canvas.collapsed .agents-header {
  align-items: center;
}

.agents-canvas.collapsed .agents-header h2 {
  font-size: 22px;
}

.agents-canvas.collapsed .agent-status-board {
  max-width: 360px;
}

.agents-header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}

.agents-eyebrow {
  display: block;
  color: var(--cyan);
  font-family: var(--font-mono);
  font-size: var(--type-caption);
  font-weight: 900;
  text-transform: uppercase;
}

.agents-header h2 {
  margin-top: 6px;
  font-size: 38px;
  line-height: 0.96;
}

.agent-status-board {
  display: grid;
  grid-template-columns: repeat(3, minmax(86px, 1fr));
  min-width: min(100%, 360px);
  border: 1px solid rgba(168, 156, 222, 0.16);
  border-radius: 8px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.055);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.agent-status-board div {
  min-height: 58px;
  padding: 10px 13px;
  border-right: 1px solid rgba(168, 156, 222, 0.12);
}

.agent-status-board div:last-child {
  border-right: 0;
}

.agent-status-board span {
  display: block;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: var(--type-caption);
  font-weight: 900;
  text-transform: uppercase;
}

.agent-status-board strong {
  display: block;
  margin-top: 5px;
  color: #ffffff;
  font-size: 24px;
  line-height: 1;
}

.agent-status-board div:nth-child(1) strong { color: var(--teal); }
.agent-status-board div:nth-child(2) strong { color: var(--amber); }
.agent-status-board div:nth-child(3) strong { color: rgba(255, 255, 255, 0.74); }

.agent-stack-toggle {
  min-width: 92px;
  border-color: rgba(102, 240, 209, 0.28);
  background: rgba(102, 240, 209, 0.08);
  color: var(--teal);
}

.agent-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: 12px;
  min-width: 0;
}

.agent-card {
  position: relative;
  display: grid;
  gap: 12px;
  align-content: start;
  min-height: 214px;
  padding: 15px;
  border-radius: 8px;
  text-align: left;
  overflow: hidden;
  background:
    radial-gradient(circle at 86% 18%, rgba(143, 216, 255, 0.16), transparent 5rem),
    linear-gradient(150deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.02)),
    rgba(18, 18, 32, 0.68);
}

.agent-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: var(--agent-accent, var(--teal));
  box-shadow: 0 0 18px var(--agent-glow, rgba(102, 240, 209, 0.32));
}

.agent-card::after {
  content: "";
  position: absolute;
  right: 18px;
  top: 102px;
  width: 15px;
  height: 15px;
  border-radius: 50%;
  background: var(--agent-accent, var(--teal));
  box-shadow: 0 0 18px var(--agent-glow, rgba(102, 240, 209, 0.34));
  opacity: 0.92;
  animation: agent-breathe 2.8s ease-in-out infinite;
}

.agent-card.idle::after {
  opacity: 0.38;
  animation-duration: 5.2s;
}

.agent-card.pink { --agent-accent: var(--red); --agent-glow: rgba(255, 111, 168, 0.38); }
.agent-card.violet { --agent-accent: var(--indigo); --agent-glow: rgba(165, 128, 255, 0.38); }
.agent-card.gold { --agent-accent: var(--amber); --agent-glow: rgba(255, 212, 109, 0.36); }
.agent-card.mint { --agent-accent: var(--green); --agent-glow: rgba(121, 242, 178, 0.34); }
.agent-card.blue { --agent-accent: var(--cyan); --agent-glow: rgba(143, 216, 255, 0.34); }

.agent-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.agent-card-top span,
.agent-card-top strong,
.agent-card small,
.agent-card-metrics span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 8px;
  font-style: normal;
  font-weight: 900;
  text-transform: uppercase;
}

.agent-card-top span {
  padding: 4px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}

.agent-card-top strong {
  color: rgba(255, 255, 255, 0.74);
}

.agent-card h3 {
  margin: 0;
  color: #ffffff;
  font-size: 18px;
  line-height: 1.15;
}

.agent-card p {
  min-height: 44px;
  color: rgba(224, 225, 246, 0.66);
  font-size: 11px;
  line-height: 1.35;
}

.agent-spark {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  align-items: end;
  gap: 3px;
  height: 22px;
}

.agent-spark span {
  display: block;
  height: calc(var(--spark) * 1%);
  min-height: 3px;
  border-radius: 999px 999px 2px 2px;
  background: linear-gradient(180deg, var(--agent-accent, var(--teal)), rgba(255, 255, 255, 0.08));
  box-shadow: 0 0 8px var(--agent-glow, rgba(102, 240, 209, 0.18));
}

.agent-card-metrics {
  display: grid;
  grid-template-columns: 0.8fr 0.9fr 1.2fr;
  gap: 8px;
  min-width: 0;
}

.agent-card-metrics div {
  min-width: 0;
}

.agent-card-metrics strong {
  display: block;
  color: var(--agent-accent, var(--teal));
  font-size: 13px;
  line-height: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-card small {
  display: block;
  min-width: 0;
  padding-top: 8px;
  border-top: 1px solid rgba(168, 156, 222, 0.12);
  color: rgba(224, 225, 246, 0.7);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-log-panel {
  min-width: 0;
  padding: 14px;
  border: 1px solid rgba(168, 156, 222, 0.16);
  border-radius: 8px;
  background:
    radial-gradient(circle at 86% 12%, rgba(143, 216, 255, 0.12), transparent 12rem),
    rgba(255, 255, 255, 0.045);
}

.agent-log-list {
  display: grid;
  gap: 1px;
  margin-top: 10px;
  overflow: hidden;
  border-radius: 6px;
}

.agent-log-row {
  display: grid;
  grid-template-columns: 68px 96px minmax(0, 1fr) 130px;
  gap: 12px;
  align-items: center;
  min-height: 34px;
  padding: 8px 10px;
  border: 0;
  border-radius: 0;
  background: rgba(255, 255, 255, 0.035);
  text-align: left;
}

.agent-log-row:hover {
  background: rgba(102, 240, 209, 0.08);
}

.agent-log-row span,
.agent-log-row em {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 9px;
  font-style: normal;
  font-weight: 900;
  text-transform: uppercase;
}

.agent-log-row strong {
  color: var(--indigo);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-log-row p {
  color: rgba(245, 244, 255, 0.84);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-log-row em {
  justify-self: end;
  max-width: 130px;
  color: var(--teal);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lane-board {
  gap: 1px;
  min-height: 260px;
  border: 1px solid rgba(168, 156, 222, 0.13);
  border-radius: 8px;
  background: rgba(168, 156, 222, 0.08);
  overflow: hidden;
}

.lane {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.012)),
    rgba(9, 9, 18, 0.36);
  border-right-color: rgba(168, 156, 222, 0.12);
}

.lane:last-child {
  border-right: 0;
}

.lane-header {
  top: 0;
  min-height: 58px;
  padding: 14px;
  background: rgba(12, 12, 24, 0.72);
  border-bottom-color: rgba(168, 156, 222, 0.14);
  border-top-color: var(--indigo);
  backdrop-filter: blur(12px);
}

.lane:nth-child(1) .lane-header {
  border-top-color: var(--red);
  background: rgba(255, 111, 168, 0.1);
}

.lane:nth-child(3) .lane-header {
  border-top-color: var(--amber);
  background: rgba(255, 212, 109, 0.09);
}

.lane:nth-child(4) .lane-header {
  border-top-color: var(--green);
  background: rgba(121, 242, 178, 0.09);
}

.lane-header strong {
  color: #ffffff;
}

.lane-header span {
  color: var(--teal);
}

.task-row {
  width: calc(100% - 18px);
  margin: 9px;
  padding: 12px;
  text-align: left;
}

@keyframes agent-breathe {
  0%, 100% { transform: scale(0.86); opacity: 0.62; }
  50% { transform: scale(1.08); opacity: 1; }
}

@keyframes pulse-teal {
  0% { box-shadow: 0 0 0 0 rgba(102, 240, 209, 0.22); }
  50% { box-shadow: 0 0 0 7px rgba(102, 240, 209, 0.07), var(--glow); }
  100% { box-shadow: 0 0 0 0 rgba(102, 240, 209, 0), var(--glow); }
}

.task-row strong,
.work-status-card strong,
.event-status-card strong,
.action-item strong,
.inbox-item strong,
.list-item strong,
.evidence-item strong,
.detail-item strong,
.event-item strong,
.project-card h3,
.goal-card h3,
.spec-card h3 {
  color: #ffffff;
}

.task-meta span,
.work-status-card span,
.event-status-card span,
.spec-reference-meta span {
  color: rgba(221, 221, 245, 0.72);
  background: rgba(255, 255, 255, 0.065);
  border: 1px solid rgba(168, 156, 222, 0.11);
  border-radius: 999px;
}

.inspector {
  background:
    radial-gradient(circle at 88% 16%, rgba(165, 128, 255, 0.14), transparent 13rem),
    rgba(10, 10, 19, 0.38);
  border-left-color: rgba(168, 156, 222, 0.14);
  padding: 18px;
}

.inspector:focus-within {
  box-shadow: inset 2px 0 0 rgba(102, 240, 209, 0.75);
}

dl {
  grid-template-columns: 88px minmax(0, 1fr);
}

dt {
  color: var(--muted);
  font-family: var(--font-mono);
}

dd {
  color: rgba(245, 244, 255, 0.86);
}

code {
  border: 1px solid rgba(102, 240, 209, 0.12);
  border-radius: 6px;
  background: rgba(5, 8, 14, 0.58);
  color: #8ef4d9;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.035);
}

.detail-panel,
.desk-grid > div + div,
.goal-row,
.spec-slice,
.gate-item,
.project-row,
.spec-reference {
  border-color: rgba(168, 156, 222, 0.13);
}

.goal-strip,
.spec-grid,
.gate-strip,
.inbox-strip,
.action-strip,
.evidence-strip,
.desk-grid {
  max-height: 56px;
}

.goal-strip.expanded,
.spec-grid.expanded,
.gate-strip.expanded,
.inbox-strip.expanded,
.action-strip.expanded,
.evidence-strip.expanded,
.desk-grid.expanded {
  max-height: 1280px;
}

body[data-page="goals"] .goal-strip.expanded {
  max-height: none;
}

body[data-page="gates"] .gate-strip.expanded {
  max-height: none;
}

body[data-page="goals"] .goal-board-list {
  grid-template-columns: 1fr;
}

.attention-list {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.attention-card strong {
  color: #ffffff;
  font-size: 30px;
}

.project-summary,
.project-list,
.goal-board-list,
.spec-list,
.gate-list,
.progress-summary-grid,
.progress-step-grid,
.inbox-list,
.action-list,
.list-stack,
.detail-summary,
.detail-events,
.evidence-list {
  gap: 10px;
}

.project-stat strong,
.goal-metric strong,
.progress-summary-card strong,
.progress-step strong,
.progress-task-main strong {
  color: #ffffff;
}

.project-card.missing {
  opacity: 0.58;
}

.action-item.selected {
  background:
    radial-gradient(circle at 88% 16%, rgba(102, 240, 209, 0.16), transparent 5rem),
    linear-gradient(135deg, rgba(102, 240, 209, 0.1), rgba(165, 128, 255, 0.07)),
    rgba(18, 18, 32, 0.72);
}

.spec-reference-meta .missing {
  background: rgba(255, 111, 168, 0.14);
  color: var(--red);
}

.library-shell {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.library-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-width: 0;
}

.library-hero span {
  display: block;
  color: var(--cyan);
  font-family: var(--font-mono);
  font-size: var(--type-caption);
  font-weight: 900;
  text-transform: uppercase;
}

.library-hero h2 {
  margin-top: 5px;
  color: #ffffff;
  font-size: 38px;
  line-height: 0.96;
}

.library-hero p {
  color: rgba(224, 225, 246, 0.68);
  font-size: 13px;
}

.library-new-doc {
  min-width: 104px;
  border-color: rgba(165, 128, 255, 0.34);
  background: rgba(255, 255, 255, 0.055);
}

.library-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.library-stats div,
.library-sidebar,
.library-reader {
  border: 1px solid rgba(168, 156, 222, 0.16);
  border-radius: 8px;
  background:
    radial-gradient(circle at 86% 14%, rgba(143, 216, 255, 0.13), transparent 9rem),
    linear-gradient(150deg, rgba(255, 255, 255, 0.075), rgba(255, 255, 255, 0.02)),
    rgba(18, 18, 32, 0.66);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.045);
}

.library-stats div {
  min-height: 86px;
  padding: 13px;
  border-top-color: rgba(102, 240, 209, 0.66);
}

.library-stats div:nth-child(2) {
  border-top-color: rgba(143, 216, 255, 0.7);
}

.library-stats div:nth-child(3) {
  border-top-color: rgba(165, 128, 255, 0.7);
}

.library-stats div:nth-child(4) {
  border-top-color: rgba(121, 242, 178, 0.7);
}

.library-stats span,
.library-stats small,
.library-reader-top span,
.library-reader-top strong,
.library-reader-meta span,
.library-doc span,
.library-doc small,
.library-slice span,
.library-slice small {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 9px;
  font-weight: 900;
  text-transform: uppercase;
}

.library-stats strong {
  display: block;
  margin-top: 6px;
  color: #ffffff;
  font-size: 26px;
  line-height: 1.05;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.library-stats small {
  display: block;
  margin-top: 5px;
}

.library-workspace {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr);
  gap: 14px;
  min-width: 0;
}

.library-sidebar {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  min-width: 0;
  padding: 12px;
}

.library-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.library-chips span {
  padding: 6px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.07);
  color: rgba(224, 225, 246, 0.72);
  font-family: var(--font-mono);
  font-size: 8px;
  font-weight: 900;
  text-transform: uppercase;
}

.library-chips span:first-child {
  background: #f4f2ff;
  color: #19142d;
}

.library-doc-list {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.library-doc {
  display: grid;
  gap: 4px;
  width: 100%;
  min-height: 72px;
  padding: 10px;
  border-radius: 8px;
  text-align: left;
  background:
    radial-gradient(circle at 90% 18%, rgba(165, 128, 255, 0.12), transparent 5rem),
    rgba(255, 255, 255, 0.045);
}

.library-doc.selected {
  border-color: rgba(102, 240, 209, 0.55);
  background:
    radial-gradient(circle at 90% 18%, rgba(102, 240, 209, 0.18), transparent 5rem),
    rgba(255, 255, 255, 0.07);
}

.library-doc strong {
  color: #ffffff;
  font-size: 12px;
  line-height: 1.25;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.library-reader {
  min-height: 330px;
  padding: 20px;
  min-width: 0;
}

.library-reader-top,
.library-reader-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
}

.library-reader-top strong {
  color: var(--teal);
}

.library-reader h3 {
  margin: 20px 0 10px;
  color: #ffffff;
  font-size: 28px;
  line-height: 1.05;
}

.library-reader p {
  color: rgba(224, 225, 246, 0.7);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.library-reader-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 18px;
}

.library-reader-meta div {
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(168, 156, 222, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
}

.library-reader-meta strong {
  display: block;
  margin-top: 5px;
  color: #ffffff;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.library-slice-map {
  display: grid;
  gap: 8px;
  margin-top: 18px;
}

.library-slice {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  min-height: 42px;
  padding: 9px 10px;
  border-left: 2px solid var(--teal);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.045);
}

.library-slice.blocked {
  border-left-color: var(--red);
}

.library-slice strong {
  color: #ffffff;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.library-reader code {
  margin-top: 18px;
}

.gate-dot {
  height: 7px;
  background: rgba(255, 255, 255, 0.12);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

.gate-dot.done {
  background: var(--teal);
  box-shadow: 0 0 12px rgba(102, 240, 209, 0.5);
}

.map-node:focus-visible,
.goal-select:focus-visible,
.task-row:focus-visible,
.project-card:focus-visible,
button:focus-visible,
.metrics-row code:focus,
nav a:focus-visible {
  outline: 2px solid var(--teal);
  outline-offset: 3px;
}

@keyframes signal-sweep-wide {
  0%, 100% { transform: translateX(-30%) scaleX(0.24); opacity: 0.2; }
  50% { transform: translateX(30%) scaleX(0.72); opacity: 0.9; }
}

@media (max-width: 1040px) {
  .sidebar {
    grid-template-columns: 1fr;
    justify-items: start;
    gap: 10px;
    padding: 12px 18px;
  }

  nav {
    justify-self: stretch;
    max-width: 100%;
  }

  main {
    width: min(100% - 28px, 1168px);
    padding-top: 28px;
  }

  .topbar {
    display: grid;
  }

  .topbar-right {
    flex: 1 1 auto;
    justify-content: start;
  }

  .metrics-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .metric-action {
    grid-column: 1 / -1;
  }

  .orchestrator-stage {
    grid-template-columns: 220px minmax(0, 1fr);
  }

  .orchestrator-health {
    grid-column: 1 / -1;
    border-left: 0;
    border-top: 1px solid rgba(168, 156, 222, 0.12);
  }
}

@media (max-width: 900px) {
  .sidebar {
    display: grid;
  }

  nav li:nth-child(n+8) {
    display: inline-flex;
  }

  main {
    width: min(100% - 24px, 680px);
    padding: 20px 0 44px;
  }

  h1 {
    font-size: 34px;
  }

  .topbar h1 {
    font-size: 34px;
  }

  .topbar {
    min-height: 0;
    padding: 22px;
  }

  .topbar-right {
    min-width: 0;
  }

  .filter-control {
    min-width: min(100%, 280px);
  }

  .map-list,
  .attention-list,
  .project-summary,
  .library-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .workspace {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .orchestrator-stage {
    grid-template-columns: 1fr;
  }

  .orchestrator-core {
    order: 1;
  }

  .orchestrator-agents {
    order: 2;
  }

  .orchestrator-health {
    order: 3;
  }

  .orchestrator-agents {
    min-height: 220px;
    border-right: 0;
    border-bottom: 1px solid rgba(168, 156, 222, 0.12);
  }

  .orchestrator-core,
  .orchestrator-health {
    border-left: 0;
  }

  .mission-feed-item {
    grid-template-columns: 68px minmax(0, 0.85fr) minmax(0, 1.15fr);
  }

  .feed-command {
    grid-column: 2 / -1;
    justify-self: start;
  }

  .agents-header {
    display: grid;
    align-items: start;
  }

  .agent-status-board {
    min-width: 0;
    width: 100%;
  }

  .lane-board {
    grid-template-columns: 1fr;
    overflow-x: visible;
  }

  .goal-page-top,
  .goal-page-layout {
    grid-template-columns: 1fr;
  }

  .goal-lane-grid {
    grid-template-columns: 1fr;
  }

  .progress-summary-grid,
  .progress-task-row,
  .progress-step-grid {
    grid-template-columns: 1fr;
  }

  .lane {
    border-right: 0;
    border-bottom: 1px solid rgba(168, 156, 222, 0.12);
  }

  .inspector {
    border-left: 0;
    border-top: 1px solid rgba(168, 156, 222, 0.14);
  }

  .library-workspace {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .sidebar {
    padding: 10px 12px;
  }

  .brand strong {
    font-size: 18px;
  }

  nav {
    border-radius: 8px;
    padding: 4px;
  }

  nav a {
    padding: 8px 10px;
  }

  main {
    width: min(100% - 18px, 520px);
    gap: 12px;
  }

  h1 {
    font-size: 30px;
  }

  .topbar h1 {
    font-size: 30px;
  }

  .metrics-row,
  .map-list,
  .attention-list,
  .project-summary,
  .library-stats,
  .library-reader-meta,
  .agent-cards,
  .action-preview-grid,
  .goal-metrics {
    grid-template-columns: 1fr;
  }

  .agents-header h2 {
    font-size: 30px;
  }

  .agents-canvas {
    padding: 16px;
  }

  .agent-card {
    min-height: 196px;
  }

  .agent-log-row {
    grid-template-columns: 1fr;
    gap: 5px;
    align-items: start;
  }

  .agent-log-row em {
    justify-self: start;
    max-width: 100%;
  }

  .library-hero {
    display: grid;
    align-items: start;
  }

  .library-hero h2 {
    font-size: 30px;
  }

  .library-reader {
    padding: 16px;
  }

  .library-reader h3 {
    font-size: 24px;
  }

  .library-slice {
    grid-template-columns: 1fr;
    gap: 5px;
    align-items: start;
  }

  .orchestrator-agents,
  .orchestrator-core,
  .orchestrator-health {
    padding: 16px;
  }

  .orchestrator-core h2 {
    font-size: 24px;
  }

  .orchestrator-kicker,
  .orchestrator-counters,
  .orchestrator-mini {
    grid-template-columns: 1fr;
  }

  .mission-feed-item {
    grid-template-columns: 64px minmax(0, 1fr);
    gap: 4px 8px;
    align-items: start;
    min-height: 76px;
  }

  .feed-label {
    grid-column: 1;
    grid-row: 1 / span 3;
  }

  .feed-title {
    grid-column: 2;
    grid-row: 1;
  }

  .feed-detail {
    grid-column: 2;
    grid-row: 2;
    white-space: normal;
    line-height: 1.25;
  }

  .feed-command {
    grid-column: 2;
    grid-row: 3;
    justify-self: start;
  }

  .health-row {
    grid-template-columns: 62px minmax(0, 1fr) 38px;
  }

  .topbar,
  .desk-grid > div,
  .map-strip,
  .action-strip,
  .goal-strip,
  .spec-grid,
  .gate-strip,
  .attention-strip,
  .project-strip,
  .inbox-strip,
  .evidence-strip,
  .inspector {
    padding: 16px;
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    scroll-behavior: auto !important;
    transition-duration: 0.001ms !important;
  }
}
"""


APP_JS = """let snapshot = null;
let selectedTaskId = null;
let selectedGoalSelection = null;
let selectedMapNode = null;
let selectedProjectId = null;
let selectedProjectName = null;
let selectedProjectPathStatus = null;
let selectedActionCommand = null;
let actionRunState = null;
let selectedSpecDocumentKey = null;
let agentsExpanded = false;
let globalFilter = "";
let currentPage = "orchestrator";

const laneLimit = ["blocked", "running", "needs_verification", "ready_to_promote", "new"];
const pageSections = {
  orchestrator: ["orchestrator", "command"],
  map: ["command", "map", "context"],
  lanes: ["command", "lanes", "context"],
  goals: ["command", "goals", "context"],
  specs: ["command", "specs"],
  gates: ["command", "gates", "context"],
  attention: ["command", "attention", "inbox"],
  inbox: ["command", "inbox", "attention"],
  projects: ["command", "projects"],
  actions: ["command", "actions", "context"],
  evidence: ["command", "evidence", "context"],
  promotion: ["command", "promotion", "context"],
};
const pageNames = {
  orchestrator: "Overview",
  map: "Map",
  lanes: "Workers",
  goals: "Goals",
  specs: "Specs",
  gates: "Progress",
  attention: "Alerts",
  inbox: "Inbox",
  projects: "Projects",
  actions: "Actions",
  evidence: "Evidence",
  promotion: "Review",
};
const sectionState = {
  actions: "collapsed",
  inbox: "collapsed",
  goals: "collapsed",
  specs: "collapsed",
  gates: "collapsed",
  promotion: "collapsed",
  evidence: "collapsed",
};

async function loadSnapshot(projectId = selectedProjectId) {
  const url = projectId ? `/api/snapshot?project=${encodeURIComponent(projectId)}` : "/api/snapshot";
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ error: "Snapshot unavailable" }));
    selectedProjectId = null;
    selectedProjectName = null;
    selectedProjectPathStatus = null;
    throw new Error(payload.error || "Snapshot unavailable");
  }
  snapshot = await response.json();
  if (selectedTaskId && !taskById(selectedTaskId)) selectedTaskId = null;
  if (selectedGoalSelection && !goalSelectionPayload()) selectedGoalSelection = null;
  selectedTaskId = selectedTaskId || snapshot.focus_task_id || firstVisibleTaskId();
  render();
}

function byId(id) {
  return document.getElementById(id);
}

function taskById(id) {
  return snapshot.tasks.find((task) => task.id === id);
}

function goalById(goalId) {
  return (snapshot.goal_board || []).find((goal) => goal.goal_id === goalId);
}

function goalSelectionPayload() {
  if (!selectedGoalSelection) return null;
  const goal = goalById(selectedGoalSelection.goalId);
  if (!goal) return null;
  if (selectedGoalSelection.type === "goal") return { type: "goal", goal, item: goal };
  const batches = [
    ...(goal.parallel_batches || []),
    ...(goal.worker_batches || []),
    ...(goal.verification_batches || []),
  ];
  if (selectedGoalSelection.type === "batch") {
    const batch = batches.find((item) => item.batch_id === selectedGoalSelection.id);
    return batch ? { type: "batch", goal, item: batch } : null;
  }
  const lane = (goal.lanes || []).find((item) => item.slice_id === selectedGoalSelection.id);
  return lane ? { type: "lane", goal, item: lane } : null;
}

function selectedGoalTaskIds() {
  const payload = goalSelectionPayload();
  if (!payload) return [];
  if (payload.type === "goal") {
    return Array.from(new Set((payload.goal.lanes || []).flatMap((lane) => lane.linked_task_ids || [])));
  }
  return Array.from(new Set([...(payload.item.task_ids || []), ...(payload.item.linked_task_ids || [])]));
}

function selectedGoalTasks() {
  const ids = new Set(selectedGoalTaskIds());
  return snapshot.tasks.filter((task) => ids.has(task.id));
}

function selectedGoalGateReceipts() {
  const ids = new Set(selectedGoalTaskIds());
  return filterGateReceipts(snapshot.gate_receipts.filter((gate) => ids.has(gate.task_id)));
}

function selectedGoalEvidence() {
  const ids = new Set(selectedGoalTaskIds());
  return snapshot.evidence.filter((item) => ids.has(item.task_id));
}

function scopedFocusTaskId() {
  const tasks = visibleTasksForMapScope();
  return tasks.length ? tasks[0].id : null;
}

function visibleTasksForMapScope() {
  let tasks = snapshot.tasks;
  if (selectedMapNode === "workers") return applyGlobalTaskFilter(snapshot.tasks.filter((task) => laneLimit.includes(task.lane)));
  if (selectedMapNode === "gates") {
    const ids = new Set(visibleGateReceipts().map((gate) => gate.task_id));
    tasks = snapshot.tasks.filter((task) => ids.has(task.id));
    return applyGlobalTaskFilter(tasks);
  }
  if (selectedMapNode === "promotion") {
    const ids = new Set(snapshot.promotion_desk.map((item) => item.task_id));
    tasks = snapshot.tasks.filter((task) => ids.has(task.id));
    return applyGlobalTaskFilter(tasks);
  }
  if (selectedMapNode === "inbox") {
    const ids = new Set((snapshot.inbox || []).map((item) => item.task_id).filter(Boolean));
    tasks = snapshot.tasks.filter((task) => ids.has(task.id));
    return applyGlobalTaskFilter(tasks);
  }
  return applyGlobalTaskFilter(tasks);
}

function applyGlobalTaskFilter(tasks) {
  if (!globalFilter.trim()) return tasks;
  return tasks.filter((task) => taskMatchesFilter(task, globalFilter));
}

function taskMatchesFilter(task, query) {
  const haystack = [
    task.id,
    task.title,
    task.status,
    task.display_status,
    task.lane,
    task.worker,
    task.workspace,
    task.verification_status,
    task.latest,
    task.log_path,
    task.result_path,
  ].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes(query.trim().toLowerCase());
}

function filteredTaskIds() {
  return new Set(applyGlobalTaskFilter(snapshot.tasks).map((task) => task.id));
}

function filterGateReceipts(gates) {
  if (!globalFilter.trim()) return gates;
  const ids = filteredTaskIds();
  return gates.filter((gate) => ids.has(gate.task_id));
}

function visibleGateReceipts() {
  const selectedIds = selectedGoalTaskIds();
  const selectedSet = new Set(selectedIds);
  if (selectedIds.length) {
    return filterGateReceipts(snapshot.gate_receipts.filter((gate) => selectedSet.has(gate.task_id)));
  }
  if (selectedMapNode === "gates") return filterGateReceipts(snapshot.gate_receipts);
  if (selectedMapNode === "promotion") {
    const ids = new Set(snapshot.promotion_desk.map((item) => item.task_id));
    return filterGateReceipts(snapshot.gate_receipts.filter((gate) => ids.has(gate.task_id)));
  }
  return filterGateReceipts(snapshot.gate_receipts);
}

function visibleEvidence() {
  const selectedIds = selectedGoalTaskIds();
  const selectedSet = new Set(selectedIds);
  if (selectedIds.length) return snapshot.evidence.filter((item) => selectedSet.has(item.task_id));
  if (["workers", "gates", "promotion", "inbox"].includes(selectedMapNode)) {
    const ids = new Set(visibleTasksForMapScope().map((task) => task.id));
    return snapshot.evidence.filter((item) => ids.has(item.task_id));
  }
  return (snapshot.evidence || []);
}

function firstVisibleTaskId() {
  const visible = new Set(laneLimit);
  const task = applyGlobalTaskFilter(snapshot.tasks).find((item) => visible.has(item.lane));
  return task ? task.id : null;
}

function repoLabel(path) {
  const parts = String(path || "").split("/").filter(Boolean);
  return parts[parts.length - 1] || path || "Repository";
}

function render() {
  if (!snapshot) return;
  currentPage = normalizePage(currentPage);
  byId("repo-label").textContent = selectedProjectId ? "Selected Project" : "Repository";
  byId("repo-title").textContent = repoLabel(snapshot.project.root);
  byId("repo-title").title = snapshot.project.root;
  byId("branch-pill").textContent = `branch ${snapshot.project.branch || "unknown"}`;
  byId("tree-pill").textContent = snapshot.project.working_tree === "clean"
    ? "all systems operational"
    : `tree ${snapshot.project.working_tree || "unknown"}`;
  byId("total-tasks").textContent = snapshot.health.total_tasks;
  byId("active-tasks").textContent = snapshot.health.active_tasks;
  byId("blocked-tasks").textContent = snapshot.health.blocked_tasks;
  byId("verify-tasks").textContent = snapshot.health.needs_verification;
  byId("next-action").textContent = (snapshot.next_action && snapshot.next_action.command) || "None";
  renderOrchestrator();
  renderGlobalFilterState();
  renderOperatingMap();
  renderContextBar();
  renderLanes();
  renderInspector();
  renderActions();
  renderGoalBoard();
  renderSpecs();
  renderGates();
  renderProjects();
  renderInbox();
  renderQuestions();
  renderPromotion();
  renderEvidence();
  renderAttention();
  applySectionState();
  applyPageVisibility();
  updateActiveNav(currentSection());
}

function renderOperatingMap() {
  const nodes = operatingMapNodes();
  byId("map-status").textContent = selectedMapNode ? `Scoped: ${selectedMapNode}` : mapStatus(nodes);
  const list = byId("map-list");
  list.innerHTML = "";
  nodes.forEach((node) => {
    const anchor = document.createElement("a");
    anchor.className = `map-node ${node.tone} ${selectedMapNode === node.key ? "selected" : ""}`;
    anchor.href = node.href;
    anchor.setAttribute("aria-label", `${node.label}: ${node.value}, ${node.detail}`);
    anchor.setAttribute("aria-current", selectedMapNode === node.key ? "true" : "false");
    anchor.innerHTML = `
      <span>${escapeHtml(node.label)}</span>
      <strong>${escapeHtml(node.value)}</strong>
      <p>${escapeHtml(node.detail)}</p>
    `;
    anchor.addEventListener("click", (event) => {
      event.preventDefault();
      selectedMapNode = selectedMapNode === node.key ? null : node.key;
      selectedGoalSelection = null;
      selectedTaskId = scopedFocusTaskId() || selectedTaskId;
      render();
      document.querySelector(node.href)?.scrollIntoView({ block: "start" });
    });
    list.appendChild(anchor);
  });
}

function renderOrchestrator() {
  const goal = currentOrchestratorGoal();
  const readyBatches = goal
    ? (goal.ready_parallel_batch_count || 0)
      + (goal.ready_worker_batch_count || 0)
      + (goal.ready_verification_batch_count || 0)
    : 0;
  const blocked = goal ? (goal.blocked_lane_count || 0) : snapshot.health.blocked_tasks;
  const queue = goal ? goal.total_slices : snapshot.health.total_tasks;
  const directive = goal
    ? goal.next_action || snapshot.next_action.reason || "No current directive"
    : snapshot.next_action.reason || "No current goal is projected yet";
  const command = goal && goal.next_action ? goal.next_action : snapshot.next_action.command || "None";
  byId("orchestrator-goal-title").textContent = goal ? goal.title : repoLabel(snapshot.project.root);
  byId("orchestrator-directive").textContent = directive;
  byId("orchestrator-command").textContent = command;
  byId("orchestrator-queue").textContent = queue || 0;
  byId("orchestrator-ready").textContent = readyBatches;
  byId("orchestrator-blocked").textContent = blocked || 0;
  byId("orchestrator-evidence").textContent = visibleEvidence().length;
  byId("orchestrator-goal-id").textContent = goal ? goal.goal_id : "none";
  byId("orchestrator-freshness").textContent = (snapshot.freshness && snapshot.freshness.status) ? snapshot.freshness.status : "unknown";
  byId("orchestrator-sync").textContent = (snapshot.warnings && snapshot.warnings.length) ? "Needs review" : "Uplink synced";
  byId("orchestrator-time").textContent = shortTime(snapshot.generated_at);
  byId("orchestrator-health-label").textContent = blocked ? "Attention" : readyBatches ? "Ready" : "Nominal";
  renderOrchestratorAgentProgress(goal);
  renderOrchestratorHealthBars(goal);
  renderMissionFeed(goal);
}

function currentOrchestratorGoal() {
  const selected = goalSelectionPayload();
  if (selected) return selected.goal;
  const enrichGoal = (goal) => {
    if (!goal) return null;
    const card = (snapshot.goals || []).find((item) => item.goal_id === goal.goal_id);
    if (card && (!goal.title || goal.title === goal.goal_id)) return { ...goal, title: card.title || goal.title };
    return goal;
  };
  if (snapshot.focus_goal_id) {
    const focus = goalById(snapshot.focus_goal_id);
    if (focus) return enrichGoal(focus);
    const focusCard = (snapshot.goals || []).find((item) => item.goal_id === snapshot.focus_goal_id);
    if (focusCard) return focusCard;
  }
  return enrichGoal((snapshot.goal_board || [])[0]) || (snapshot.goals || [])[0] || null;
}

function renderOrchestratorAgentProgress(goal) {
  const list = byId("orchestrator-agent-progress");
  const count = byId("agent-progress-count");
  if (!list || !count) return;
  const summaries = snapshot.worker_activity || [];
  count.textContent = `${summaries.length} ${summaries.length === 1 ? "worker" : "workers"}`;
  list.innerHTML = "";
  summaries.forEach((agent) => {
    const progress = agent.verified_percent || 0;
    const state = agent.state_class || "idle";
    const outputVolume = agent.recent_output_count || 0;
    const row = document.createElement("button");
    row.type = "button";
    row.className = `agent-progress-row ${state}`;
    row.setAttribute("role", "listitem");
    row.setAttribute("aria-label", `${agent.name}: ${agent.state}, ${progress}% complete, ${agent.task_count} tasks, ${outputVolume} recent outputs`);
    row.innerHTML = `
      <span class="agent-progress-code">${escapeHtml(agent.code)}</span>
      <span class="agent-progress-main">
        <span class="agent-progress-top">
          <strong>${escapeHtml(agent.name)}</strong>
          <em>${escapeHtml(agent.state)}</em>
        </span>
        <span class="agent-progress-track" aria-hidden="true"><i style="--progress:${progress}%"></i></span>
        <span class="agent-progress-meta">
          <span>${progress}% complete</span>
          <span>${agent.task_count} tasks</span>
          <span>${outputVolume} output</span>
        </span>
      </span>
    `;
    row.addEventListener("click", () => {
      selectedMapNode = "workers";
      selectedGoalSelection = null;
      selectedTaskId = agent.first_task_id || selectedTaskId;
      agentsExpanded = true;
      render();
      byId("lanes")?.scrollIntoView({ block: "start" });
    });
    list.appendChild(row);
  });
}

function agentProgressState(agent, tasks) {
  if (agent.laneName === "blocked" && tasks.length) return "blocked";
  if (tasks.some((task) => isFailedTask(task))) return "blocked";
  if (tasks.length && tasks.every((task) => isVerifiedOrReadyTask(task))) return "complete";
  if (agent.state === "Running") return "active";
  return "idle";
}

function agentProgressPercent(agent, tasks) {
  if (!tasks.length) return 0;
  const complete = tasks.filter((task) => isVerifiedOrReadyTask(task)).length;
  const running = tasks.filter((task) => laneLimit.includes(task.lane) && task.lane !== "closed").length;
  const eventBoost = Math.min(20, tasks.reduce((total, task) => total + ((task.detail && task.detail.recent_events) ? task.detail.recent_events.length : 0), 0) * 2);
  return Math.max(12, Math.min(100, Math.round((complete / tasks.length) * 76 + (running ? 18 : 8) + eventBoost)));
}

function normalizedWorker(worker) {
  const value = String(worker || "").trim();
  if (!value || value === "unassigned" || value === "unknown") return null;
  return value;
}

function workerProfile(worker) {
  const profiles = {
    shell: {
      code: "SH",
      name: "Shell worker",
      description: "Runs the command DevFlow was given inside the task workspace.",
      tone: "violet",
    },
    "devflow-manual-codex-worker": {
      code: "CDX",
      name: "Manual Codex worker",
      description: "A human-launched Codex handoff that writes task evidence back to DevFlow.",
      tone: "blue",
    },
    "qwopus-implementer": {
      code: "QWO",
      name: "Qwopus implementer",
      description: "Local Ollama worker evidence for implementation proposals.",
      tone: "mint",
    },
    "qwen-planner": {
      code: "QWN",
      name: "Local Qwen planner",
      description: "Local Ollama planning output captured as evidence.",
      tone: "gold",
    },
    "gemma-reviewer": {
      code: "GEM",
      name: "Gemma reviewer",
      description: "Local Ollama review output captured as evidence.",
      tone: "pink",
    },
  };
  return profiles[worker] || {
    code: workerCode(worker),
    name: plainWorkerName(worker),
    description: "DevFlow worker evidence grouped by the worker id recorded on tasks.",
    tone: "blue",
  };
}

function workerCode(worker) {
  return String(worker || "wrk")
    .split(/[^a-zA-Z0-9]+/)
    .filter(Boolean)
    .map((part) => part[0])
    .join("")
    .slice(0, 3)
    .toUpperCase() || "WRK";
}

function plainWorkerName(worker) {
  return String(worker || "worker")
    .split(/[-_]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function workerState(tasks, activeTasks) {
  const openTasks = tasks.filter((task) => String(task.lane || "").toLowerCase() !== "closed");
  if (activeTasks.length) return "Running";
  if (openTasks.some((task) => task.lane === "blocked" || isFailedTask(task))) return "Needs attention";
  if (openTasks.some((task) => ["new", "needs_verification", "ready_to_promote"].includes(task.lane))) return "Waiting";
  return "Recorded";
}

function stateClassForWorkerState(state) {
  if (state === "Running") return "active";
  if (state === "Needs attention") return "blocked";
  if (state === "Recorded") return "complete";
  return "idle";
}

function isFailedTask(task) {
  return String(task.verification_status || "").toLowerCase().includes("fail")
    || String(task.display_status || "").toLowerCase().includes("failed");
}

function isVerifiedOrReadyTask(task) {
  return String(task.verification_status || "").toLowerCase().includes("pass")
    || Boolean(task.promotion_ready || task.merge_ready)
    || String(task.lane || "").toLowerCase() === "closed";
}

function renderOrchestratorHealthBars(goal) {
  const bars = byId("orchestrator-health-bars");
  if (!bars) return;
  bars.innerHTML = "";
  const total = Math.max(1, snapshot.health.total_tasks || 1);
  const active = Math.round((snapshot.health.active_tasks / total) * 100);
  const verify = Math.round((snapshot.health.needs_verification / total) * 100);
  const blocked = Math.round((snapshot.health.blocked_tasks / total) * 100);
  const goalReady = goal ? Math.min(100, Math.round(((goal.ready_parallel_lane_count || 0) / Math.max(1, goal.total_slices || 1)) * 100)) : 0;
  [
    ["Active", active, "teal"],
    ["Verify", verify, "gold"],
    ["Blocked", blocked, "pink"],
    ["Goal ready", goalReady, "violet"],
  ].forEach(([label, value, tone]) => {
    const row = document.createElement("div");
    row.className = `health-row ${tone}`;
    row.innerHTML = `<span>${escapeHtml(label)}</span><div><i style="width:${value}%"></i></div><strong>${value}%</strong>`;
    bars.appendChild(row);
  });
}

function renderMissionFeed(goal) {
  const list = byId("mission-feed-list");
  const count = byId("mission-feed-count");
  if (!list || !count) return;
  const items = snapshot.mission_feed || [];
  count.textContent = `${items.length} ${items.length === 1 ? "update" : "updates"}`;
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = `<div class="empty">No mission-critical output yet</div>`;
    return;
  }
  items.forEach((item) => {
    const button = document.createElement("button");
    const feedLabel = plainFeedLabel(item);
    const feedDetail = plainFeedDetail(item);
    button.type = "button";
    button.className = `mission-feed-item ${item.tone || "event"}`;
    button.setAttribute("role", "listitem");
    button.setAttribute("aria-label", `${feedLabel}: ${item.title}. ${feedDetail}`);
    button.innerHTML = `
      <span class="feed-label">${escapeHtml(feedLabel)}</span>
      <strong class="feed-title">${escapeHtml(item.title)}</strong>
      <span class="feed-detail">${escapeHtml(feedDetail)}</span>
      <span class="feed-command">${escapeHtml(item.command || "inspect")}</span>
    `;
    button.addEventListener("click", () => handleMissionFeedItem(item));
    list.appendChild(button);
  });
}

function plainFeedLabel(item) {
  return plainDisplayText(item.label || "Work update");
}

function plainFeedDetail(item) {
  const detail = String(item.detail || "");
  const labels = {
    task_cleanup_applied: "Task cleanup was applied.",
    task_cleanup_previewed: "Task cleanup preview was recorded.",
    task_created: "Task entered the queue.",
    task_closed: "Task was closed and kept as evidence.",
    verification_passed: "Verification passed.",
    verification_failed: "Verification failed.",
    worker_finished: "Worker output was recorded.",
    worker_failed: "Worker failed. Inspect the worker log.",
  };
  if (labels[detail]) return labels[detail];
  if (/^[a-z0-9]+(?:_[a-z0-9]+)+$/.test(detail)) return plainDisplayText(detail);
  return detail || "Work evidence was recorded.";
}

function handleMissionFeedItem(item) {
  const taskId = item.task_id || item.taskId;
  if (taskId && taskById(taskId)) {
    selectedTaskId = taskId;
    selectedGoalSelection = null;
    agentsExpanded = true;
    setCurrentPage("lanes", { updateHash: true });
    return;
  }
  byId("orchestrator-command")?.focus?.();
  setCurrentPage("orchestrator", { updateHash: true });
}

function renderGlobalFilterState() {
  const count = applyGlobalTaskFilter(snapshot.tasks).length;
  if (byId("global-filter").value !== globalFilter) byId("global-filter").value = globalFilter;
  byId("filter-count").textContent = globalFilter.trim() ? `${count}/${snapshot.tasks.length}` : "All";
}

function operatingMapNodes() {
  const goals = snapshot.goal_board || [];
  const readyGoalBatches = goals.reduce((total, goal) => total
    + (goal.ready_parallel_batch_count || 0)
    + (goal.ready_worker_batch_count || 0)
    + (goal.ready_verification_batch_count || 0), 0);
  const blockedGoalLanes = goals.reduce((total, goal) => total + (goal.blocked_lane_count || 0), 0);
  const activeLaneCount = snapshot.lanes.filter((lane) => lane.task_ids.length > 0).length;
  const filteredWorkerTasks = applyGlobalTaskFilter(snapshot.tasks.filter((task) => laneLimit.includes(task.lane)));
  const gateOpen = snapshot.gate_receipts.filter((gate) => gate.next_gate !== "closed").length;
  const projectSummary = snapshot.multi_project;
  return [
    {
      key: "goals",
      label: "Goals",
      value: String(goals.length),
      detail: readyGoalBatches ? `${readyGoalBatches} ready batches` : `${blockedGoalLanes} blocked lanes`,
      href: "#goals",
      tone: readyGoalBatches ? "verify" : blockedGoalLanes ? "attention" : "",
    },
    {
      key: "inbox",
      label: "Inbox",
      value: String((snapshot.inbox || []).length),
      detail: (snapshot.inbox || []).length ? "human attention" : "clear",
      href: "#inbox",
      tone: (snapshot.inbox || []).length ? "attention" : "",
    },
    {
      key: "workers",
      label: "Workers",
      value: globalFilter.trim() ? String(filteredWorkerTasks.length) : String(snapshot.health.active_tasks),
      detail: globalFilter.trim() ? "filter matches" : `${activeLaneCount} active lanes`,
      href: "#lanes",
      tone: snapshot.health.blocked_tasks ? "attention" : "",
    },
    {
      key: "gates",
      label: "Progress",
      value: String(snapshot.gate_receipts.length),
      detail: gateOpen ? `${gateOpen} open` : "all closed",
      href: "#gates",
      tone: gateOpen ? "verify" : "",
    },
    {
      key: "promotion",
      label: "Review",
      value: String(snapshot.promotion_desk.length),
      detail: snapshot.promotion_desk.length ? "ready review" : "none ready",
      href: "#promotion",
      tone: snapshot.promotion_desk.length ? "verify" : "",
    },
    {
      key: "projects",
      label: "Projects",
      value: projectSummary ? String(projectSummary.active_projects) : "0",
      detail: projectSummary ? `${projectSummary.total_projects} registered` : "registry off",
      href: "#projects",
      tone: projectSummary && projectSummary.missing_projects ? "attention" : "",
    },
  ];
}

function mapStatus(nodes) {
  const attention = nodes.filter((node) => node.tone === "attention").length;
  const verify = nodes.filter((node) => node.tone === "verify").length;
  if (attention) return `${attention} attention`;
  if (verify) return `${verify} ready`;
  return "Clear";
}

function renderContextBar() {
  const context = currentContext();
  byId("context-title").textContent = context.title;
  byId("context-detail").textContent = context.detail;
  byId("clear-context-button").disabled = !context.active;
  byId("clear-context-button").setAttribute("aria-disabled", context.active ? "false" : "true");
}

function currentContext() {
  const goalSelection = goalSelectionPayload();
  if (goalSelection) {
    return {
      active: true,
      title: selectionTitle(goalSelection),
      detail: `${selectedGoalTaskIds().length} linked tasks / ${goalSelection.type} scope`,
    };
  }
  if (selectedMapNode) {
    return {
      active: true,
      title: `Operating Map: ${mapNodeLabel(selectedMapNode)}`,
      detail: mapScopeDetail(selectedMapNode),
    };
  }
  return {
    active: false,
    title: "All work",
    detail: "Whole operating layer",
  };
}

function mapNodeLabel(key) {
  const node = operatingMapNodes().find((item) => item.key === key);
  return node ? node.label : key;
}

function mapScopeDetail(key) {
  if (key === "gates") return `${visibleGateReceipts().length} task readiness receipts`;
  if (key === "workers") return `${visibleTasksForMapScope().length} worker-lane tasks`;
  if (key === "promotion") return `${snapshot.promotion_desk.length} tasks ready for review`;
  if (key === "inbox") return `${(snapshot.inbox || []).length} inbox items`;
  if (key === "goals") return `${(snapshot.goal_board || []).length} goals`;
  if (key === "projects") return snapshot.multi_project ? `${snapshot.multi_project.total_projects} registered projects` : "project registry unavailable";
  return "Scoped view";
}

function clearContext() {
  selectedMapNode = null;
  selectedGoalSelection = null;
  selectedTaskId = snapshot.focus_task_id || firstVisibleTaskId();
  render();
}

function renderLanes() {
  const board = byId("lane-board");
  board.innerHTML = "";
  const selectedTaskIds = selectedGoalTaskIds();
  const selectedTaskSet = new Set(selectedTaskIds);
  const scopedTaskIds = new Set(visibleTasksForMapScope().map((task) => task.id));
  const filteredIds = filteredTaskIds();
  const hasMapTaskScope = ["workers", "gates", "promotion", "inbox"].includes(selectedMapNode);
  const visibleLaneTasks = [];
  snapshot.lanes
    .filter((lane) => laneLimit.includes(lane.name))
    .forEach((lane) => {
      const column = document.createElement("section");
      column.className = "lane";
      let taskIds = selectedTaskIds.length ? lane.task_ids.filter((taskId) => selectedTaskSet.has(taskId)) : lane.task_ids;
      if (hasMapTaskScope) taskIds = taskIds.filter((taskId) => scopedTaskIds.has(taskId));
      taskIds = taskIds.filter((taskId) => filteredIds.has(taskId));
      column.innerHTML = `<div class="lane-header"><strong>${lane.label}</strong><span>${taskIds.length}</span></div>`;
      taskIds.forEach((taskId) => {
        const task = taskById(taskId);
        if (!task) return;
        visibleLaneTasks.push(task);
        column.appendChild(taskRow(task, selectedTaskIds.length > 0));
      });
      if (!taskIds.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.style.padding = "12px";
        empty.textContent = globalFilter.trim()
          ? "No filter matches"
          : selectedTaskIds.length || hasMapTaskScope
            ? "No scoped tasks"
            : "None";
        column.appendChild(empty);
      }
      board.appendChild(column);
    });
  renderAgentCollective(visibleLaneTasks, agentActivityScopeTasks());
}

function agentActivityScopeTasks() {
  if (selectedGoalSelection) return selectedGoalTasks();
  if (["gates", "promotion", "inbox"].includes(selectedMapNode)) return visibleTasksForMapScope();
  return applyGlobalTaskFilter(snapshot.tasks);
}

function renderAgentCollective(activeLaneTasks, activityTasks) {
  const canvas = document.querySelector(".agents-canvas");
  const workspace = byId("lanes");
  if (canvas) {
    canvas.classList.toggle("expanded", agentsExpanded);
    canvas.classList.toggle("collapsed", !agentsExpanded);
  }
  if (workspace) {
    workspace.classList.toggle("agents-collapsed", !agentsExpanded);
    workspace.classList.toggle("agents-expanded", agentsExpanded);
  }
  const toggle = byId("agent-stack-toggle");
  if (toggle) {
    toggle.textContent = agentsExpanded ? "Collapse" : "Expand";
    toggle.setAttribute("aria-expanded", agentsExpanded ? "true" : "false");
  }
  const summaries = agentSummaries(activeLaneTasks, activityTasks);
  const activeAgents = summaries.filter((agent) => agent.status === "Running").length;
  const idleAgents = summaries.filter((agent) => agent.status === "Waiting").length;
  const dormantAgents = summaries.filter((agent) => !["Running", "Waiting"].includes(agent.status)).length;
  byId("agent-active-count").textContent = activeAgents;
  byId("agent-idle-count").textContent = idleAgents;
  byId("agent-dormant-count").textContent = dormantAgents;

  const cards = byId("agent-cards");
  cards.innerHTML = "";
  summaries.forEach((agent) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `agent-card ${agent.tone} ${agent.taskCount ? "has-work" : "idle"}`;
    card.setAttribute("aria-label", `${agent.name}: ${agent.taskCount} tasks, ${agent.successRate}% verified or ready`);
    card.innerHTML = `
      <div class="agent-card-top">
        <span>${escapeHtml(agent.code)}</span>
        <strong>${escapeHtml(agent.state)}</strong>
      </div>
      <h3>${escapeHtml(agent.name)}</h3>
      <p>${escapeHtml(agent.description)}</p>
      <div class="agent-spark" aria-hidden="true">
        ${agent.spark.map((value) => `<span style="--spark:${value}"></span>`).join("")}
      </div>
      <div class="agent-card-metrics">
        <div><strong>${agent.taskCount}</strong><span>tasks</span></div>
        <div><strong>${agent.successRate}%</strong><span>verified</span></div>
        <div><strong>${escapeHtml(agent.worker)}</strong><span>worker</span></div>
      </div>
      <small>${escapeHtml(agent.latest)}</small>
    `;
    card.addEventListener("click", () => {
      selectedMapNode = "workers";
      selectedGoalSelection = null;
      selectedTaskId = agent.firstTaskId || selectedTaskId;
      render();
      byId("lanes")?.scrollIntoView({ block: "start" });
    });
    cards.appendChild(card);
  });
  renderAgentLog(activityTasks);
}

function agentSummaries(activeLaneTasks, activityTasks) {
  const activeIds = new Set(activeLaneTasks.map((task) => task.id));
  const grouped = new Map();
  activityTasks.forEach((task) => {
    const worker = normalizedWorker(task.worker);
    if (!worker) return;
    if (!grouped.has(worker)) grouped.set(worker, []);
    grouped.get(worker).push(task);
  });
  const workerSummaries = Array.from(grouped.entries()).map(([worker, tasks], index) => {
    const profile = workerProfile(worker);
    const activeTasks = tasks.filter((task) => activeIds.has(task.id));
    const failed = tasks.filter((task) => isFailedTask(task)).length;
    const verified = tasks.filter((task) => isVerifiedOrReadyTask(task)).length;
    const successRate = tasks.length ? Math.round((verified / tasks.length) * 100) : 0;
    const latestTask = activeTasks.find((task) => task.latest) || tasks.find((task) => task.latest) || tasks[0];
    const state = workerState(tasks, activeTasks);
    return {
      ...profile,
      laneName: `worker:${worker}`,
      state,
      status: state,
      stateClass: stateClassForWorkerState(state),
      taskCount: tasks.length,
      successRate,
      verified,
      worker,
      tasks,
      firstTaskId: activeTasks[0] ? activeTasks[0].id : tasks[0] ? tasks[0].id : null,
      latest: latestTask ? `${latestTask.id}: ${plainTaskStatusLine(latestTask)}` : "No task evidence yet",
      spark: sparkValues(tasks.length, verified, failed, index),
    };
  });
  if (workerSummaries.length) {
    return workerSummaries
      .sort((a, b) => Number(b.status === "Running") - Number(a.status === "Running") || b.taskCount - a.taskCount)
      .slice(0, 6);
  }
  return statusBucketSummaries(activeLaneTasks, activityTasks);
}

function statusBucketSummaries(activeLaneTasks, activityTasks) {
  const activeTaskByLane = new Map();
  laneLimit.forEach((laneName) => activeTaskByLane.set(laneName, []));
  activeLaneTasks.forEach((task) => {
    if (activeTaskByLane.has(task.lane)) activeTaskByLane.get(task.lane).push(task);
  });
  return laneLimit.map((laneName, index) => {
    const laneTasks = activeTaskByLane.get(laneName) || [];
    const profile = agentProfile(laneName);
    const profileTasks = profileActivityTasks(laneName, laneTasks, activityTasks);
    const failed = profileTasks.filter((task) => isFailedTask(task)).length;
    const verified = profileTasks.filter((task) => isVerifiedOrReadyTask(task)).length;
    const successRate = profileTasks.length ? Math.round((verified / profileTasks.length) * 100) : 0;
    const latestTask = profileTasks.find((task) => task.latest) || profileTasks[0];
    const state = laneTasks.length ? "Waiting" : profileTasks.length ? "Recorded" : "No tasks";
    return {
      ...profile,
      laneName,
      state,
      status: state,
      stateClass: stateClassForWorkerState(state),
      taskCount: profileTasks.length,
      successRate,
      verified,
      firstTaskId: laneTasks[0] ? laneTasks[0].id : profileTasks[0] ? profileTasks[0].id : null,
      latest: latestTask ? `${latestTask.id}: ${plainTaskStatusLine(latestTask)}` : profile.emptyDetail,
      spark: sparkValues(profileTasks.length, verified, failed, index),
      tasks: profileTasks,
    };
  });
}

function profileActivityTasks(laneName, laneTasks, activityTasks) {
  const matches = activityTasks.filter((task) => {
    if (task.lane === laneName) return true;
    if (laneName === "running") return Boolean(task.worker) && task.worker !== "unassigned";
    if (laneName === "needs_verification") return task.verification_status && task.verification_status !== "missing";
    if (laneName === "ready_to_promote") return Boolean(task.promotion_ready || task.merge_ready);
    if (laneName === "blocked") {
      const text = `${task.status} ${task.display_status} ${task.latest}`.toLowerCase();
      return text.includes("block") || text.includes("human");
    }
    return false;
  });
  return uniqueTasks([...laneTasks, ...matches]);
}

function uniqueTasks(tasks) {
  const seen = new Set();
  return tasks.filter((task) => {
    if (!task || seen.has(task.id)) return false;
    seen.add(task.id);
    return true;
  });
}

function agentProfile(laneName) {
  const profiles = {
    blocked: {
      code: "BLK",
      name: "Needs user input",
      description: "Tasks blocked by a question, failed evidence, or a human decision.",
      emptyState: "No tasks",
      emptyDetail: "No blocked tasks",
      tone: "pink",
      worker: "not assigned",
    },
    running: {
      code: "WRK",
      name: "Work running",
      description: "Tasks currently being worked on inside DevFlow workspaces.",
      emptyState: "No tasks",
      emptyDetail: "No running work",
      tone: "violet",
      worker: "assigned worker",
    },
    needs_verification: {
      code: "VER",
      name: "Needs verification",
      description: "Tasks waiting for a verification command or fresh proof.",
      emptyState: "No tasks",
      emptyDetail: "No tasks need verification",
      tone: "gold",
      worker: "verification",
    },
    ready_to_promote: {
      code: "REV",
      name: "Ready for review",
      description: "Verified work waiting for a review preview and human approval.",
      emptyState: "No tasks",
      emptyDetail: "No work is ready for review",
      tone: "mint",
      worker: "human approval",
    },
    new: {
      code: "NEW",
      name: "Not started",
      description: "Fresh tasks waiting for assignment, context, or a first run.",
      emptyState: "No tasks",
      emptyDetail: "No new tasks",
      tone: "blue",
      worker: "not assigned",
    },
  };
  return profiles[laneName] || {
    code: laneName.slice(0, 3).toUpperCase(),
    name: plainWorkerName(laneName),
    description: "Task status bucket.",
    emptyState: "No tasks",
    emptyDetail: "No activity",
    tone: "blue",
    worker: "not assigned",
  };
}

function dominantWorker(tasks) {
  const counts = new Map();
  tasks.forEach((task) => {
    const worker = task.worker || "unknown";
    counts.set(worker, (counts.get(worker) || 0) + 1);
  });
  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] || null;
}

function sparkValues(taskCount, verified, failed, offset) {
  return Array.from({ length: 7 }, (_, index) => {
    const base = taskCount ? 34 + Math.min(42, taskCount * 7) : 14;
    const signal = verified * 6 - failed * 8 + ((index + offset) % 4) * 9;
    return Math.max(12, Math.min(92, base + signal));
  });
}

function renderAgentLog(tasks) {
  const rows = agentActivityRows(tasks);
  byId("agent-log-count").textContent = `${rows.length} ${rows.length === 1 ? "entry" : "entries"}`;
  const log = byId("agent-log-list");
  log.innerHTML = "";
  if (!rows.length) {
    log.innerHTML = `<div class="empty">No recent worker activity in this scope</div>`;
    return;
  }
  rows.forEach((row) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "agent-log-row";
    item.innerHTML = `
      <span>${escapeHtml(row.time)}</span>
      <strong>${escapeHtml(row.agent)}</strong>
      <p>${escapeHtml(row.task)}</p>
      <em>${escapeHtml(row.status)}</em>
    `;
    item.addEventListener("click", () => {
      selectedTaskId = row.taskId;
      selectedGoalSelection = null;
      selectedMapNode = null;
      render();
    });
    log.appendChild(item);
  });
}

function plainTaskStatusLabel(task) {
  const lane = String(task.lane || "").toLowerCase();
  if (lane === "blocked") return "Needs attention";
  if (lane === "running") return "Worker active";
  if (lane === "needs_verification") return "Verification next";
  if (lane === "ready_to_promote") return "Ready for review";
  if (lane === "new") return "Ready to start";
  if (lane === "closed") return "Closed";
  return "Task state";
}

function plainTaskStatusLine(task) {
  const lane = String(task.lane || "").toLowerCase();
  const status = String(task.status || task.display_status || "").toLowerCase();
  const verification = String(task.verification_status || "").toLowerCase();
  if (lane === "closed" || status.includes("closed")) return "Closed for evidence. No active worker is needed.";
  if (lane === "blocked" || status.includes("blocked")) return "Human input or repair is needed before work continues.";
  if (lane === "running" || status.includes("running")) return "A worker is running in the isolated workspace.";
  if (lane === "needs_verification") return "Worker output is recorded. Verification is the next gate.";
  if (lane === "ready_to_promote") return "Verification passed. Review and promotion preview are next.";
  if (verification.includes("fail")) return "Verification failed. Inspect the verify log before continuing.";
  if (verification.includes("pass")) return "Verification passed. Review readiness is available.";
  if (lane === "new" || status === "new") return "Task is queued and ready for a worker command.";
  return plainDisplayText(task.display_status || task.status || task.latest || "Task evidence recorded.");
}

function plainEventLabel(eventName) {
  const labels = {
    task_created: "Task created",
    task_updated: "Task updated",
    task_closed: "Task closed",
    worker_started: "Worker started",
    worker_finished: "Worker finished",
    worker_failed: "Worker failed",
    verification_started: "Verification started",
    verification_passed: "Verification passed",
    verification_failed: "Verification failed",
    task_verified: "Task verified",
    task_promoted: "Task promoted",
    patch_applied: "Patch applied",
  };
  return labels[eventName] || plainDisplayText(eventName || "event recorded");
}

function plainEventSummary(event, task) {
  const eventName = String(event.event || "");
  const labels = {
    task_created: "Task entered the queue and is ready for assignment.",
    task_updated: "Task state changed. Inspect task details for evidence.",
    task_closed: "Task was closed and kept as evidence.",
    worker_started: "Worker execution started in the task workspace.",
    worker_finished: "Worker output was recorded for review.",
    worker_failed: "Worker failed. Inspect the worker log before retrying.",
    verification_started: "Verification started for this task.",
    verification_passed: "Verification passed and review can continue.",
    verification_failed: "Verification failed. Inspect the verify log.",
    task_verified: "Verification passed and evidence is recorded.",
    task_promoted: "Task was promoted after human approval.",
    patch_applied: "Patch evidence was applied to the isolated workspace.",
  };
  if (labels[eventName]) return labels[eventName];
  return plainTaskStatusLine(task);
}

function plainDisplayText(value) {
  return String(value || "recorded")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\\s+/g, " ")
    .trim()
    .replace(/^./, (letter) => letter.toUpperCase());
}

function agentActivityRows(tasks) {
  const rows = [];
  tasks.forEach((task) => {
    const events = task.detail && task.detail.recent_events ? task.detail.recent_events : [];
    if (!events.length) {
      rows.push({
        taskId: task.id,
        time: "latest",
        agent: task.worker || laneAgentName(task.lane),
        task: task.title,
        status: plainTaskStatusLine(task),
        timestamp: "",
      });
      return;
    }
    events.slice(-2).forEach((event) => {
      rows.push({
        taskId: task.id,
        time: shortTime(event.timestamp),
        agent: task.worker || laneAgentName(task.lane),
        task: `${task.id} - ${task.title}`,
        status: plainEventSummary(event, task),
        timestamp: event.timestamp || "",
      });
    });
  });
  return rows
    .sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)))
    .slice(0, 7);
}

function laneAgentName(laneName) {
  return agentProfile(laneName).name;
}

function shortTime(timestamp) {
  if (!timestamp) return "latest";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "latest";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function taskRow(task, isGoalFiltered = false) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = `task-row ${task.id === selectedTaskId ? "selected" : ""} ${isGoalFiltered ? "goal-filtered" : ""}`;
  row.innerHTML = `
    <strong>${task.id} - ${escapeHtml(task.title)}</strong>
    <div class="work-status-card">
      <span>${escapeHtml(plainTaskStatusLabel(task))}</span>
      <strong>${escapeHtml(plainTaskStatusLine(task))}</strong>
    </div>
    <div class="task-meta">
      <span>${escapeHtml(task.worker)}</span>
      <span>${escapeHtml(task.verification_status)}</span>
      <span>${escapeHtml(task.display_status)}</span>
    </div>
  `;
  row.addEventListener("click", () => {
    selectedTaskId = task.id;
    selectedGoalSelection = null;
    selectedMapNode = null;
    render();
  });
  return row;
}

function renderInspector() {
  const selection = goalSelectionPayload();
  if (selection) {
    renderGoalInspector(selection);
    return;
  }
  const task = taskById(selectedTaskId);
  byId("selected-task-id").textContent = task ? task.id : "None";
  byId("selected-title").textContent = task ? task.title : "Select a task";
  byId("selected-command").textContent = task && task.next_action ? task.next_action.command || "None" : "None";
  const details = byId("selected-details");
  details.innerHTML = "";
  renderTaskDetail(task);
  if (!task) return;
  [
    ["Status", task.display_status],
    ["Worker", task.worker],
    ["Verify", task.verification_status],
    ["Workspace", task.workspace],
    ["Log", task.log_path || "None"],
    ["Result", task.result_path || "None"],
  ].forEach(([key, value]) => {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key;
    dd.textContent = value;
    details.append(dt, dd);
  });
}

function renderGoalInspector(selection) {
  const goal = selection.goal;
  const item = selection.item;
  const linkedTasks = selectedGoalTasks();
  const gates = selectedGoalGateReceipts();
  const evidence = selectedGoalEvidence();
  byId("selected-task-id").textContent = selection.type === "goal" ? goal.goal_id : item.batch_id || item.slice_id;
  byId("selected-title").textContent = selectionTitle(selection);
  byId("selected-command").textContent = firstActionCommand(item) || goal.next_action || "None";
  const details = byId("selected-details");
  details.innerHTML = "";
  const rows = selectionRows(selection);
  rows.forEach(([key, value]) => {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key;
    dd.textContent = value;
    details.append(dt, dd);
  });
  const summary = byId("detail-summary");
  const events = byId("detail-events");
  summary.innerHTML = "";
  events.innerHTML = "";
  byId("detail-event-count").textContent = linkedTasks.length + gates.length + evidence.length;
  [
    ["Recommendation", item.recommendation || item.reason || goal.next_action || "None"],
    ["Commands", commandList(item).join("\\n") || "None"],
    ["Blockers", (item.blockers || []).join("\\n") || "None"],
    ["Shared files", (item.shared_files || []).join("\\n") || "None"],
    ["Linked tasks", linkedTasks.map((task) => `${task.id} - ${task.display_status}`).join("\\n") || "None"],
    ["Task progress", gates.map(gateSummary).join("\\n") || "No linked task progress"],
    ["Evidence", evidence.map(evidenceSummary).join("\\n") || "No linked evidence"],
  ].forEach(([label, value]) => {
    const detail = document.createElement("div");
    detail.className = "detail-item";
    detail.innerHTML = `<strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span>`;
    summary.appendChild(detail);
  });
  if (!linkedTasks.length) {
    events.innerHTML = `<div class="empty">No linked task evidence yet</div>`;
    return;
  }
  linkedTasks.slice(0, 5).forEach((task) => {
    const event = document.createElement("div");
    event.className = "event-item";
    const preview = task.detail && task.detail.result_preview
      ? task.detail.result_preview
      : task.latest || task.display_status;
    event.innerHTML = `
      <strong>${escapeHtml(task.id)} evidence</strong>
      <span>${escapeHtml(preview || "No evidence preview")}</span>
    `;
    events.appendChild(event);
  });
}

function selectionTitle(selection) {
  if (selection.type === "goal") return `${selection.goal.goal_id} - ${selection.goal.title}`;
  if (selection.type === "batch") return `${selection.item.batch_id} - ${selection.item.kind} batch`;
  return `${selection.item.slice_id} - ${selection.item.title}`;
}

function selectionRows(selection) {
  const item = selection.item;
  if (selection.type === "goal") {
    return [
      ["Type", "Goal"],
      ["State", item.loop_state],
      ["Slices", String(item.total_slices)],
      ["Ready", String(item.ready_parallel_lane_count)],
      ["Blocked", String(item.blocked_lane_count)],
    ];
  }
  if (selection.type === "batch") {
    return [
      ["Type", `${item.kind} batch`],
      ["Lanes", (item.lane_ids || []).join(", ") || "None"],
      ["Tasks", (item.task_ids || []).join(", ") || "None"],
      ["Commands", String(item.command_count)],
      ["Scope", item.verification_scope || "None"],
    ];
  }
  return [
    ["Type", "Goal slice"],
    ["State", item.lane_state],
    ["Risk", item.risk],
    ["Mode", item.execution_mode],
    ["Blocks", (item.blockers || []).join(", ") || "None"],
    ["Tasks", (item.linked_task_ids || []).join(", ") || "None"],
  ];
}

function firstActionCommand(item) {
  const actions = item && item.actions ? item.actions : [];
  return actions.length ? actions[0].command : item.command || null;
}

function commandList(item) {
  const commands = [
    ...((item.actions || []).map((action) => action.command)),
    ...(item.commands || []),
    item.command,
  ].filter(Boolean);
  return Array.from(new Set(commands));
}

function gateSummary(gate) {
  const complete = ["intake", "worker_evidence", "verification", "promotion_readiness", "human_decision"]
    .filter((step) => gate[step]).length;
  return `${gate.task_id}: ${complete}/5 required steps done, next ${plainNextStep(gate.next_gate)}`;
}

function plainNextStep(nextGate) {
  const labels = {
    run_worker: "run a worker",
    verify: "verify the task",
    verification: "verify the task",
    promotion_preview: "prepare review preview",
    promotion_readiness: "prepare review",
    human_decision: "human review",
    closed: "closed",
  };
  return labels[nextGate] || String(nextGate || "unknown").replaceAll("_", " ");
}

function evidenceSummary(item) {
  return `${item.task_id}: ${item.log_path || item.result_path || item.verification_log_path || item.verification_command || "evidence"}`;
}

function renderTaskDetail(task) {
  const summary = byId("detail-summary");
  const events = byId("detail-events");
  summary.innerHTML = "";
  events.innerHTML = "";
  byId("detail-event-count").textContent = task && task.detail ? task.detail.recent_events.length : 0;
  if (!task || !task.detail) {
    summary.innerHTML = `<div class="empty">Select a task</div>`;
    return;
  }
  const detail = task.detail;
  [
    ["Verification", verificationLabel(detail.verification)],
    ["Worker log", detail.latest_worker_line || "None"],
    ["Verify log", detail.latest_verification_line || "None"],
    ["Result", detail.result_preview || "None"],
    ["Evidence", detail.evidence_paths.length ? detail.evidence_paths.join("\\n") : "None"],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "detail-item";
    item.innerHTML = `<strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span>`;
    summary.appendChild(item);
  });
  if (!detail.recent_events.length) {
    events.innerHTML = `<div class="empty">No events</div>`;
  } else {
    detail.recent_events.forEach((event) => {
      const item = document.createElement("div");
      item.className = "event-item";
      item.innerHTML = `
        <strong>${escapeHtml(plainEventLabel(event.event))}</strong>
        <span class="event-status-card">
          <span>${escapeHtml(shortTime(event.timestamp))}</span>
          <strong>${escapeHtml(plainEventSummary(event, task))}</strong>
        </span>
      `;
      events.appendChild(item);
    });
  }
}

function verificationLabel(verification) {
  if (!verification) return "missing";
  if (verification.exit_code === null || verification.exit_code === undefined) return verification.status;
  return `${verification.status} / exit ${verification.exit_code}`;
}

function renderActions() {
  const task = taskById(selectedTaskId);
  const selection = goalSelectionPayload();
  const scopedActions = mapScopedActions();
  const actions = selection
    ? selection.item.actions || []
    : selectedMapNode && scopedActions.length
      ? scopedActions
      : task
        ? task.actions || []
        : snapshot.action_rail || [];
  byId("action-count").textContent = actions.length;
  const list = byId("action-list");
  const preview = byId("action-preview");
  list.innerHTML = "";
  preview.innerHTML = "";
  if (!sectionExpanded("actions")) return;
  if (!actions.length) {
    list.innerHTML = `<div class="empty">None</div>`;
    renderActionPreview(null);
    return;
  }
  const visibleActions = actions.slice(0, 8);
  if (!visibleActions.some((action) => action.command === selectedActionCommand)) {
    selectedActionCommand = visibleActions[0].command;
  }
  visibleActions.forEach((action) => {
    const item = document.createElement("button");
    item.type = "button";
    const selected = action.command === selectedActionCommand;
    item.className = `action-item ${selected ? "selected" : ""}`;
    item.setAttribute("aria-pressed", selected ? "true" : "false");
    item.setAttribute("aria-label", `Preview ${action.label}`);
    const safety = action.supervisor_may_auto_run ? "read-only" : "approval required";
    item.innerHTML = `
      <strong>${escapeHtml(action.label)}</strong>
      <span class="label">${escapeHtml(safety)} / ${escapeHtml(action.safety_class)}</span>
      <code>${escapeHtml(action.command)}</code>
    `;
    item.addEventListener("click", () => {
      selectedActionCommand = action.command;
      renderActions();
    });
    list.appendChild(item);
  });
  renderActionPreview(visibleActions.find((action) => action.command === selectedActionCommand) || visibleActions[0]);
}

function renderActionPreview(action) {
  const preview = byId("action-preview");
  preview.innerHTML = "";
  if (!action) {
    preview.innerHTML = `<div class="empty">Select an action to inspect command safety</div>`;
    return;
  }
  const mayAutoRun = action.supervisor_may_auto_run ? "Supervisor read-only safe" : "Human approval required";
  const approval = action.requires_human_approval ? "approval required" : "no approval required";
  const isRunning = actionRunState && actionRunState.command === action.command && actionRunState.status === "running";
  const actionResult = actionRunState && actionRunState.command === action.command ? actionRunState : null;
  const executeLabel = action.supervisor_may_auto_run ? "Execute read-only command" : "Approval required in CLI";
  const resultMarkup = actionResult && actionResult.status !== "running"
    ? renderActionResult(actionResult)
    : "";
  preview.innerHTML = `
    <div class="section-heading">
      <span>Command Preview</span>
      <strong>${escapeHtml(action.scope || "scope")}</strong>
    </div>
    <div class="action-preview-grid">
      <div>
        <span>Label</span>
        <strong>${escapeHtml(action.label)}</strong>
      </div>
      <div>
        <span>Safety</span>
        <strong>${escapeHtml(action.safety_class)}</strong>
      </div>
      <div>
        <span>Execution</span>
        <strong>${escapeHtml(mayAutoRun)}</strong>
      </div>
      <div>
        <span>Approval</span>
        <strong>${escapeHtml(approval)}</strong>
      </div>
    </div>
    <code>${escapeHtml(action.command)}</code>
    <p>${escapeHtml(action.reason || "This command is supervisor-classified as safe for this local control layer.")}</p>
    <div class="action-execute-row">
      <button type="button" class="action-run-button" data-run-action ${action.supervisor_may_auto_run && !isRunning ? "" : "disabled"}>
        ${escapeHtml(isRunning ? "Running..." : executeLabel)}
      </button>
      <span class="label">${escapeHtml(action.supervisor_may_auto_run ? "Runs locally through Dev-Flow guardrails" : "Use the trusted CLI after explicit approval")}</span>
    </div>
    ${isRunning ? '<div class="action-result"><strong>Running command...</strong></div>' : resultMarkup}
  `;
  const runButton = preview.querySelector("[data-run-action]");
  if (runButton && action.supervisor_may_auto_run) {
    runButton.addEventListener("click", () => executeAction(action));
  }
}

function renderActionResult(result) {
  if (result.status === "blocked") {
    return `
      <div class="action-result">
        <strong>Approval gate</strong>
        <p>${escapeHtml(result.message || "This command requires human approval and was not executed.")}</p>
      </div>
    `;
  }
  if (result.status === "error") {
    return `
      <div class="action-result">
        <strong>Command error</strong>
        <p>${escapeHtml(result.message || "The command could not be executed.")}</p>
      </div>
    `;
  }
  const payload = result.payload || {};
  const output = [payload.stdout, payload.stderr].filter(Boolean).join("\\n");
  const status = payload.timed_out ? "Timed out" : `Exit ${payload.exit_code}`;
  return `
    <div class="action-result">
      <strong>${escapeHtml(status)}</strong>
      ${payload.output_truncated ? "<p>Output was truncated.</p>" : ""}
      <pre>${escapeHtml(output || "No output")}</pre>
    </div>
  `;
}

async function executeAction(action) {
  actionRunState = { command: action.command, status: "running" };
  renderActionPreview(action);
  try {
    const response = await fetch("/api/actions/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: action.command, project: selectedProjectId }),
    });
    const payload = await response.json().catch(() => ({ error: "Action unavailable" }));
    if (!response.ok && payload.executed === false) {
      actionRunState = {
        command: action.command,
        status: "blocked",
        message: payload.message || payload.error || "Action requires approval",
        payload,
      };
    } else if (!response.ok) {
      actionRunState = {
        command: action.command,
        status: "error",
        message: payload.error || payload.stderr || "Action failed",
        payload,
      };
    } else {
      actionRunState = { command: action.command, status: "complete", payload };
    }
  } catch (error) {
    actionRunState = {
      command: action.command,
      status: "error",
      message: error instanceof Error ? error.message : "Action failed",
    };
  }
  renderActionPreview(action);
}

function mapScopedActions() {
  if (selectedMapNode === "goals") return (snapshot.goal_board || []).flatMap((goal) => goal.actions || []).slice(0, 8);
  if (selectedMapNode === "inbox") return (snapshot.inbox || []).map((item) => item.action).filter(Boolean).slice(0, 8);
  if (selectedMapNode === "projects") return snapshot.action_rail || [];
  if (selectedMapNode === "promotion") {
    return snapshot.promotion_desk.map((item) => ({
      label: "Review preview",
      command: item.command,
      scope: "task",
      safety_class: "pure_read_only",
      requires_human_approval: false,
      supervisor_may_auto_run: true,
      reason: null,
    })).slice(0, 8);
  }
  if (selectedMapNode === "gates" || selectedMapNode === "workers") {
    return visibleTasksForMapScope().flatMap((task) => task.actions || []).slice(0, 8);
  }
  return [];
}

function renderGoalBoard() {
  const goals = snapshot.goal_board || [];
  byId("goal-board-count").textContent = goals.length;
  const list = byId("goal-board-list");
  list.innerHTML = "";
  if (!sectionExpanded("goals")) return;
  if (!goals.length) {
    list.innerHTML = `<div class="empty">None</div>`;
    return;
  }
  goals.slice(0, 6).forEach((goal) => {
    const card = document.createElement("article");
    card.className = "goal-card goal-page-card";
    const batches = [
      ...(goal.parallel_batches || []),
      ...(goal.worker_batches || []),
      ...(goal.verification_batches || []),
    ].slice(0, 4);
    const blockers = (goal.blocked_lanes || []).slice(0, 3);
    const lanes = (goal.lanes || []).slice(0, 12);
    const completion = goal.total_slices
      ? Math.round((goal.completed_slice_count / goal.total_slices) * 100)
      : 0;
    card.innerHTML = `
      <div class="goal-page-top">
        <div>
          <span class="label">${escapeHtml(goal.goal_id)}</span>
          <h3>${escapeHtml(goal.title)}</h3>
          <p>${escapeHtml(plainGoalState(goal.loop_state))} / ${escapeHtml(plainGoalState(goal.goal_state))}</p>
        </div>
        <div class="goal-progress-summary" aria-label="${completion}% complete">
          <strong>${completion}%</strong>
          <span>${goal.completed_slice_count}/${goal.total_slices} slices done</span>
          <i style="--goal-progress:${completion}%"></i>
        </div>
      </div>
      <div class="goal-metrics">
        <div class="goal-metric"><span>Done</span><strong>${goal.completed_slice_count}</strong></div>
        <div class="goal-metric"><span>Active tasks</span><strong>${goal.active_task_count}</strong></div>
        <div class="goal-metric"><span>Ready lanes</span><strong>${goal.ready_parallel_lane_count}</strong></div>
        <div class="goal-metric"><span>Blocked</span><strong>${goal.blocked_lane_count}</strong></div>
      </div>
      <div class="goal-page-layout">
        <div class="goal-lane-panel">
          <div class="goal-panel-heading">
            <span>Goal slices</span>
            <strong>${lanes.length}</strong>
          </div>
          <div class="goal-lane-grid">
            ${lanes.map((lane) => `
              <button class="goal-select goal-lane-row ${laneStateClass(lane)} ${isSelectedGoalItem(goal.goal_id, "lane", lane.slice_id) ? "selected" : ""}" type="button" data-goal="${escapeHtml(goal.goal_id)}" data-type="lane" data-id="${escapeHtml(lane.slice_id)}" aria-pressed="${isSelectedGoalItem(goal.goal_id, "lane", lane.slice_id) ? "true" : "false"}" aria-label="Select ${escapeHtml(lane.slice_id)} ${escapeHtml(lane.title)}">
                <span>${escapeHtml(lane.slice_id)}</span>
                <strong>${escapeHtml(lane.title)}</strong>
                <small>${escapeHtml(plainGoalState(lane.lane_state))} / ${escapeHtml(lane.risk || "risk unknown")}</small>
                <em>${escapeHtml((lane.linked_task_ids || []).join(", ") || "No linked task")}</em>
                <p>${escapeHtml(lane.recommendation || "No recommendation recorded.")}</p>
              </button>
            `).join("") || '<div class="empty">No goal slices projected</div>'}
          </div>
        </div>
        <aside class="goal-next-panel">
          <div class="goal-panel-heading">
            <span>Next safe action</span>
            <strong>${batches.length ? `${batches.length} batch${batches.length === 1 ? "" : "es"}` : "manual"}</strong>
          </div>
          <code>${escapeHtml(goal.next_action || "None")}</code>
          <div class="goal-mini-list">
            <span>Ready batches</span>
            ${batches.map((batch) => `
              <button class="goal-select goal-mini-row ${isSelectedGoalItem(goal.goal_id, "batch", batch.batch_id) ? "selected" : ""}" type="button" data-goal="${escapeHtml(goal.goal_id)}" data-type="batch" data-id="${escapeHtml(batch.batch_id)}" aria-pressed="${isSelectedGoalItem(goal.goal_id, "batch", batch.batch_id) ? "true" : "false"}" aria-label="Select ${escapeHtml(batch.batch_id)} ${escapeHtml(batch.kind)} batch">
                <strong>${escapeHtml(batch.batch_id)}</strong>
                <small>${escapeHtml(batch.kind)} / ${batch.command_count} commands</small>
              </button>
            `).join("") || '<div class="empty">No ready batches</div>'}
          </div>
          <div class="goal-mini-list">
            <span>Blocked work</span>
            ${blockers.map((lane) => `
              <button class="goal-select goal-mini-row blocked ${isSelectedGoalItem(goal.goal_id, "lane", lane.slice_id) ? "selected" : ""}" type="button" data-goal="${escapeHtml(goal.goal_id)}" data-type="lane" data-id="${escapeHtml(lane.slice_id)}" aria-pressed="${isSelectedGoalItem(goal.goal_id, "lane", lane.slice_id) ? "true" : "false"}" aria-label="Select blocked ${escapeHtml(lane.slice_id)} ${escapeHtml(lane.title)}">
                <strong>${escapeHtml(lane.slice_id)}</strong>
                <small>${escapeHtml((lane.blockers || []).join(", ") || "Needs review")}</small>
              </button>
            `).join("") || '<div class="empty">No blocked goal slices</div>'}
          </div>
        </aside>
      </div>
    `;
    card.addEventListener("click", (event) => {
      const button = event.target.closest(".goal-select");
      if (!button) {
        selectedGoalSelection = { goalId: goal.goal_id, type: "goal", id: goal.goal_id };
      } else {
        selectedGoalSelection = {
          goalId: button.dataset.goal,
          type: button.dataset.type,
          id: button.dataset.id,
        };
      }
      selectedTaskId = null;
      const linked = selectedGoalTaskIds();
      if (linked.length) selectedTaskId = linked[0];
      render();
    });
    list.appendChild(card);
  });
}

function isSelectedGoalItem(goalId, type, id) {
  return selectedGoalSelection
    && selectedGoalSelection.goalId === goalId
    && selectedGoalSelection.type === type
    && selectedGoalSelection.id === id;
}

function plainGoalState(state) {
  const labels = {
    planning_review: "Planning review",
    ready_for_task_creation: "Ready for task creation",
    ready_to_create_task: "Ready to create task",
    ready_to_run_or_verify: "Ready to run or verify",
    repair_or_verify: "Repair or verify",
    ready_to_promote: "Ready for review",
    closed: "Closed",
    complete: "Complete",
  };
  return labels[state] || String(state || "unknown").replaceAll("_", " ");
}

function laneStateClass(lane) {
  const state = String(lane.lane_state || "").toLowerCase();
  if (state.includes("block")) return "blocked";
  if (state.includes("closed") || state.includes("complete")) return "done";
  if (state.includes("ready")) return "ready";
  return "planned";
}

function renderSpecs() {
  const documents = specDocuments();
  const availableDocuments = documents.filter((doc) => doc.status !== "missing");
  byId("spec-count").textContent = documents.length || snapshot.spec_board.length;
  const list = byId("spec-list");
  list.innerHTML = "";
  if (!sectionExpanded("specs")) return;
  if (!snapshot.spec_board.length) {
    list.innerHTML = `
      <div class="library-shell">
        <div class="library-hero">
          <span>Worker Output</span>
          <h2>Library.</h2>
          <p>No spec documents are projected yet.</p>
        </div>
      </div>
    `;
    return;
  }
  const selected = selectedSpecDocument(documents);
  list.innerHTML = `
    <div class="library-shell">
      <div class="library-hero">
        <div>
          <span>Worker Output</span>
          <h2>Library.</h2>
        </div>
        <button type="button" class="library-new-doc" data-toggle-section="actions">New Doc</button>
      </div>
      <div class="library-stats">
        <div><span>Total Docs</span><strong>${documents.length}</strong><small>projected artifacts</small></div>
        <div><span>Available</span><strong>${availableDocuments.length}</strong><small>readable references</small></div>
        <div><span>Goals</span><strong>${snapshot.spec_board.length}</strong><small>active spec roots</small></div>
        <div><span>Latest</span><strong>${escapeHtml(selected ? selected.title : "None")}</strong><small>${escapeHtml(selected ? selected.kind : "no documents")}</small></div>
      </div>
      <div class="library-workspace">
        <aside class="library-sidebar">
          <div class="library-chips">
            ${libraryKinds(documents).map((kind) => `<span>${escapeHtml(kind)}</span>`).join("")}
          </div>
          <div id="library-doc-list" class="library-doc-list"></div>
        </aside>
        <article id="library-reader" class="library-reader"></article>
      </div>
    </div>
  `;
  renderLibraryDocumentList(documents, selected);
  renderLibraryReader(selected);
  const newDoc = list.querySelector(".library-new-doc");
  newDoc?.addEventListener("click", () => {
    sectionState.actions = "expanded";
    setCurrentPage("actions", { updateHash: true });
  });
}

function specDocuments() {
  const documents = [];
  snapshot.spec_board.forEach((goal) => {
    documents.push({
      key: `goal:${goal.goal_id}`,
      kind: "goal",
      title: goal.title,
      subtitle: goal.goal_id,
      path: goal.spec_path,
      source: "goal spec",
      status: goal.state,
      goal,
      slices: goal.slices || [],
      reference: null,
    });
    (goal.references || []).forEach((reference, index) => {
      documents.push({
        key: `ref:${goal.goal_id}:${index}:${reference.path}`,
        kind: reference.kind,
        title: reference.title,
        subtitle: goal.goal_id,
        path: reference.path,
        source: reference.source,
        status: reference.status,
        goal,
        slices: goal.slices || [],
        reference,
      });
    });
  });
  return documents;
}

function selectedSpecDocument(documents) {
  if (!documents.length) return null;
  let selected = documents.find((doc) => doc.key === selectedSpecDocumentKey);
  if (!selected) selected = documents.find((doc) => doc.status !== "missing") || documents[0];
  selectedSpecDocumentKey = selected.key;
  return selected;
}

function libraryKinds(documents) {
  const kinds = ["all", ...Array.from(new Set(documents.map((doc) => doc.kind)))];
  return kinds.slice(0, 6);
}

function renderLibraryDocumentList(documents, selected) {
  const target = byId("library-doc-list");
  if (!target) return;
  target.innerHTML = "";
  documents.slice(0, 14).forEach((doc) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `library-doc ${selected && selected.key === doc.key ? "selected" : ""}`;
    button.setAttribute("aria-pressed", selected && selected.key === doc.key ? "true" : "false");
    button.innerHTML = `
      <span>${escapeHtml(doc.kind)}</span>
      <strong>${escapeHtml(doc.title)}</strong>
      <small>${escapeHtml(doc.subtitle)} / ${escapeHtml(doc.status)}</small>
    `;
    button.addEventListener("click", () => {
      selectedSpecDocumentKey = doc.key;
      renderSpecs();
    });
    target.appendChild(button);
  });
}

function renderLibraryReader(doc) {
  const reader = byId("library-reader");
  if (!reader) return;
  if (!doc) {
    reader.innerHTML = `<div class="empty">Select a document to read</div>`;
    return;
  }
  const slices = (doc.slices || []).slice(0, 6);
  reader.innerHTML = `
    <div class="library-reader-top">
      <span>${escapeHtml(doc.kind)}</span>
      <strong>${escapeHtml(doc.status)}</strong>
    </div>
    <h3>${escapeHtml(doc.title)}</h3>
    <p>${escapeHtml(doc.path)}</p>
    <div class="library-reader-meta">
      <div><span>Goal</span><strong>${escapeHtml(doc.goal.goal_id)}</strong></div>
      <div><span>Source</span><strong>${escapeHtml(doc.source)}</strong></div>
      <div><span>Slices</span><strong>${slices.length}</strong></div>
    </div>
    <div class="library-slice-map">
      ${slices.map((slice) => `
        <div class="library-slice ${slice.state === "blocked" ? "blocked" : ""}">
          <span>${escapeHtml(slice.slice_id)}</span>
          <strong>${escapeHtml(slice.title)}</strong>
          <small>${escapeHtml(slice.state)}${slice.risk ? ` / ${escapeHtml(slice.risk)}` : ""}</small>
        </div>
      `).join("") || '<div class="empty">No slices projected</div>'}
    </div>
    <code>${escapeHtml(doc.reference ? doc.reference.path : doc.goal.spec_path)}</code>
  `;
}

function renderGates() {
  const selectedIds = selectedGoalTaskIds();
  const gates = visibleGateReceipts();
  byId("gate-count").textContent = gates.length;
  const summary = byId("progress-summary-grid");
  const list = byId("gate-list");
  summary.innerHTML = "";
  list.innerHTML = "";
  if (!sectionExpanded("gates")) return;
  if (!gates.length) {
    summary.innerHTML = "";
    list.innerHTML = `<div class="empty">${selectedIds.length ? "No linked task progress" : "None"}</div>`;
    return;
  }
  renderProgressSummary(gates, summary);
  gates.slice(0, 12).forEach((gate) => {
    list.appendChild(renderProgressTask(gate));
  });
}

function renderProgressSummary(gates, target) {
  const counts = {
    open: gates.filter((gate) => gate.next_gate !== "closed").length,
    worker: gates.filter((gate) => gate.next_gate === "run_worker").length,
    verify: gates.filter((gate) => gate.next_gate === "verify").length,
    review: gates.filter((gate) => ["promotion_preview", "human_decision"].includes(gate.next_gate)).length,
  };
  [
    ["Open tasks", counts.open],
    ["Need worker", counts.worker],
    ["Need verify", counts.verify],
    ["Ready review", counts.review],
  ].forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "progress-summary-card";
    card.innerHTML = `<span>${escapeHtml(label)}</span><strong>${value}</strong>`;
    target.appendChild(card);
  });
}

function renderProgressTask(gate) {
  const task = taskById(gate.task_id) || {};
  const row = document.createElement("article");
  row.className = `progress-task-row ${progressTaskTone(gate, task)}`;
  row.setAttribute("role", "listitem");
  row.setAttribute("aria-label", `${gate.task_id}: ${plainNextStep(gate.next_gate)}`);
  const command = gate.command || (task.next_action && task.next_action.command) || "None";
  row.innerHTML = `
    <div class="progress-task-main">
      <span>${escapeHtml(gate.task_id)}</span>
      <strong>${escapeHtml(task.title || "Untitled task")}</strong>
      <p>${escapeHtml(task.display_status || task.status || "unknown")} / ${escapeHtml(task.worker || "no worker")} / ${escapeHtml(task.lane || "unlaned")}</p>
    </div>
    <div class="progress-step-grid" aria-label="Readiness checklist for ${escapeHtml(gate.task_id)}">
      ${progressStepDefinitions().map((step) => {
        const state = progressStepState(gate, step.key);
        return `
          <div class="progress-step ${state}">
            <i aria-hidden="true"></i>
            <strong>${escapeHtml(step.label)}</strong>
            <small>${escapeHtml(progressStepLabel(state))}</small>
          </div>
        `;
      }).join("")}
    </div>
    <div class="progress-next-panel">
      <span>Next safe action</span>
      <p>${escapeHtml(plainNextStep(gate.next_gate))}</p>
      <code>${escapeHtml(command)}</code>
      <p>${escapeHtml(task.latest || "No recent task event recorded.")}</p>
    </div>
  `;
  row.addEventListener("click", () => {
    if (!task.id) return;
    selectedTaskId = task.id;
    renderInspector();
  });
  return row;
}

function progressStepDefinitions() {
  return [
    { key: "intake", label: "Intake" },
    { key: "worker_evidence", label: "Worker output" },
    { key: "verification", label: "Verification" },
    { key: "promotion_readiness", label: "Review preview" },
    { key: "human_decision", label: "Human decision" },
  ];
}

function progressStepState(gate, step) {
  if (gate[step]) return "done";
  if (gate.next_gate === "closed") return "skipped";
  const currentByNextGate = {
    run_worker: "worker_evidence",
    verify: "verification",
    promotion_preview: "promotion_readiness",
    human_decision: "human_decision",
  };
  return currentByNextGate[gate.next_gate] === step ? "current" : "pending";
}

function progressStepLabel(state) {
  const labels = {
    done: "Done",
    current: "Next",
    pending: "Waiting",
    skipped: "Skipped",
  };
  return labels[state] || "Waiting";
}

function progressTaskTone(gate, task) {
  if (gate.next_gate === "closed") return "ready";
  if (task.lane === "blocked" || ["failed", "verification_failed", "blocked"].includes(task.status)) return "blocked";
  if (gate.next_gate === "run_worker") return "waiting";
  if (gate.next_gate === "human_decision") return "ready";
  return "active";
}

function renderProjects() {
  const overview = snapshot.multi_project;
  byId("project-count").textContent = overview ? overview.total_projects : 0;
  const summary = byId("project-summary");
  const list = byId("project-list");
  summary.innerHTML = "";
  list.innerHTML = "";
  if (!overview) {
    list.innerHTML = `<div class="empty">Registry unavailable</div>`;
    return;
  }
  [
    ["Projects", overview.total_projects],
    ["Active", overview.active_projects],
    ["Missing", overview.missing_projects],
    ["Verify", overview.needs_verification],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "project-stat";
    item.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    summary.appendChild(item);
  });
  if (!overview.projects.length) {
    list.innerHTML = `<div class="empty">No projects registered</div>`;
    return;
  }
  overview.projects.slice(0, 8).forEach((project) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `project-card ${project.project_id === selectedProjectId ? "selected" : ""} ${project.path_status === "missing" ? "missing" : ""}`;
    card.disabled = project.path_status === "missing";
    card.innerHTML = `
      <h3>${escapeHtml(project.name)} <span class="label">${escapeHtml(project.project_id)}</span></h3>
      <div class="task-meta">
        <span>${escapeHtml(project.status)}</span>
        <span>${escapeHtml(project.path_status)}</span>
        <span>${escapeHtml(project.branch || "unknown")}</span>
      </div>
      <div class="project-row"><span>tasks</span><strong>${project.total_tasks}</strong></div>
      <div class="project-row"><span>active</span><strong>${project.active_tasks}</strong></div>
      <div class="project-row"><span>verify</span><strong>${project.needs_verification}</strong></div>
      <div class="project-row"><span>review</span><strong>${project.ready_to_promote}</strong></div>
      <code>${escapeHtml(project.next_action || "None")}</code>
    `;
    card.addEventListener("click", async () => {
      if (project.path_status === "missing") return;
      selectedProjectId = project.project_id;
      selectedProjectName = project.name;
      selectedProjectPathStatus = project.path_status;
      selectedTaskId = null;
      await loadSnapshot(project.project_id);
    });
    list.appendChild(card);
  });
}

function renderInbox() {
  byId("inbox-count").textContent = snapshot.inbox ? snapshot.inbox.length : 0;
  const list = byId("inbox-list");
  list.innerHTML = "";
  if (!sectionExpanded("inbox")) return;
  if (!snapshot.inbox || !snapshot.inbox.length) {
    list.innerHTML = `<div class="empty">None</div>`;
    return;
  }
  snapshot.inbox.slice(0, 12).forEach((item) => {
    const div = document.createElement("div");
    div.className = `inbox-item ${item.priority <= 15 ? "urgent" : ""}`;
    div.innerHTML = `
      <strong>${escapeHtml(item.title)}</strong>
      <div class="task-meta">
        <span>${escapeHtml(plainInboxKind(item.kind))}</span>
        <span>${escapeHtml(item.scope)}</span>
        <span>${escapeHtml(item.path || "no path")}</span>
      </div>
      <p>${escapeHtml(item.message)}</p>
      <code>${escapeHtml(item.command || "None")}</code>
    `;
    list.appendChild(div);
  });
}

function plainProgressStep(step) {
  const labels = {
    intake: "Task created",
    worker_evidence: "Worker output recorded",
    verification: "Verification passed",
    promotion_readiness: "Review preview ready",
    human_decision: "Human decision recorded",
  };
  return labels[step] || String(step || "unknown").replaceAll("_", " ");
}

function plainInboxKind(kind) {
  const labels = {
    question: "Question",
    blocked_task: "Blocked task",
    task_attention: "Task attention",
    human_decision: "Human decision",
  };
  return labels[kind] || String(kind || "Item").replaceAll("_", " ");
}

function renderQuestions() {
  byId("question-count").textContent = (snapshot.questions || []).length;
  const list = byId("question-list");
  list.innerHTML = "";
  if (!sectionExpanded("promotion")) return;
  if (!snapshot.questions.length) {
    list.innerHTML = `<div class="empty">None</div>`;
    return;
  }
  snapshot.questions.forEach((item) => {
    list.appendChild(simpleItem(item.task_id, item.question, item.command));
  });
}

function renderPromotion() {
  byId("promotion-count").textContent = (snapshot.promotion_desk || []).length;
  const list = byId("promotion-list");
  list.innerHTML = "";
  if (!sectionExpanded("promotion")) return;
  if (!snapshot.promotion_desk.length) {
    list.innerHTML = `<div class="empty">None</div>`;
    return;
  }
  snapshot.promotion_desk.forEach((item) => {
    list.appendChild(simpleItem(item.task_id, item.title, item.command));
  });
}

function renderEvidence() {
  const selectedIds = selectedGoalTaskIds();
  const evidence = visibleEvidence();
  byId("evidence-count").textContent = evidence.length;
  const list = byId("evidence-list");
  list.innerHTML = "";
  if (!sectionExpanded("evidence")) return;
  if (!evidence.length) {
    list.innerHTML = `<div class="empty">${selectedIds.length ? "No linked evidence" : "None"}</div>`;
    return;
  }
  evidence.slice(0, 16).forEach((item) => {
    const div = document.createElement("div");
    div.className = "evidence-item";
    div.innerHTML = `<strong>${item.task_id}</strong><span>${escapeHtml(item.log_path || item.result_path || item.verification_log_path || "evidence")}</span>`;
    list.appendChild(div);
  });
}

function renderAttention() {
  const inboxCount = snapshot.inbox ? snapshot.inbox.length : 0;
  const questionCount = snapshot.questions.length;
  const promotionCount = snapshot.promotion_desk.length;
  const evidenceCount = visibleEvidence().length;
  const cards = [
    {
      key: "inbox",
      label: "Inbox",
      value: inboxCount,
      detail: inboxCount ? "human decisions waiting" : "clear",
      tone: inboxCount ? "urgent" : "",
    },
    {
      key: "promotion",
      label: "Questions",
      value: questionCount,
      detail: questionCount ? "blocked worker prompts" : "no open questions",
      tone: questionCount ? "urgent" : "",
    },
    {
      key: "promotion",
      label: "Review",
      value: promotionCount,
      detail: promotionCount ? "ready for preview" : "nothing ready",
      tone: promotionCount ? "ready" : "",
    },
    {
      key: "evidence",
      label: "Evidence",
      value: evidenceCount,
      detail: evidenceCount ? "recent task artifacts" : "no evidence yet",
      tone: evidenceCount ? "verify" : "",
    },
  ];
  byId("attention-count").textContent = cards.reduce((total, card) => total + card.value, 0);
  const list = byId("attention-list");
  list.innerHTML = "";
  cards.forEach((card) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `attention-card ${card.tone}`;
    button.setAttribute("aria-label", `${card.label}: ${card.value}. ${card.detail}`);
    button.innerHTML = `
      <span>${escapeHtml(card.label)}</span>
      <strong>${card.value}</strong>
      <p>${escapeHtml(card.detail)}</p>
    `;
    button.addEventListener("click", () => {
      if (Object.prototype.hasOwnProperty.call(sectionState, card.key)) {
        sectionState[card.key] = "expanded";
      }
      setCurrentPage(card.key, { updateHash: true });
    });
    list.appendChild(button);
  });
}

function sectionExpanded(name) {
  return sectionState[name] !== "collapsed";
}

function toggleSection(name) {
  if (!Object.prototype.hasOwnProperty.call(sectionState, name)) return;
  sectionState[name] = sectionExpanded(name) ? "collapsed" : "expanded";
  render();
  if (sectionExpanded(name)) {
    const target = document.querySelector(`#${name} .section-body button, #${name} .section-body a, #${name} .section-body [tabindex], #${name} .section-body code`);
    target?.focus?.();
  }
}

function applySectionState() {
  Object.entries(sectionState).forEach(([name, state]) => {
    const section = byId(name);
    if (!section) return;
    section.classList.toggle("expanded", state === "expanded");
    section.classList.toggle("collapsed", state === "collapsed");
    const trigger = section.querySelector("[data-toggle-section]");
    if (trigger) {
      trigger.setAttribute("aria-expanded", state === "expanded" ? "true" : "false");
    }
  });
}

function normalizePage(page) {
  const value = String(page || "").replace(/^#/, "");
  return Object.prototype.hasOwnProperty.call(pageSections, value) ? value : "orchestrator";
}

function pageFromHash() {
  return normalizePage(window.location.hash || "orchestrator");
}

function setCurrentPage(page, { updateHash = false, scrollTop = true } = {}) {
  const nextPage = normalizePage(page);
  currentPage = nextPage;
  const pageScope = { lanes: "workers", gates: "gates", promotion: "promotion", inbox: "inbox" };
  selectedMapNode = pageScope[nextPage] || null;
  if (nextPage === "lanes") agentsExpanded = true;
  (pageSections[nextPage] || []).forEach((section) => {
    if (Object.prototype.hasOwnProperty.call(sectionState, section)) sectionState[section] = "expanded";
  });
  if (updateHash && window.location.hash !== `#${nextPage}`) {
    window.history.pushState(null, "", `#${nextPage}`);
  }
  if (snapshot) render();
  if (scrollTop) {
    requestAnimationFrame(() => {
      byId("main-panel")?.scrollIntoView({ block: "start" });
      window.scrollTo({ top: 0, behavior: "auto" });
    });
  }
}

function applyPageVisibility() {
  const activeSections = new Set(pageSections[currentPage] || pageSections.orchestrator);
  document.querySelectorAll("[data-section], #context").forEach((section) => {
    const visible = activeSections.has(section.id);
    section.classList.toggle("page-hidden", !visible);
    section.setAttribute("aria-hidden", visible ? "false" : "true");
  });
  const pageName = pageNames[currentPage] || "Overview";
  byId("main-panel").setAttribute("aria-label", `${pageName} page`);
  document.body.dataset.page = currentPage;
}

function currentSection() {
  return currentPage;
}

function updateActiveNav(section) {
  document.querySelectorAll("nav a").forEach((link) => {
    const active = link.getAttribute("href") === `#${section}`;
    link.classList.toggle("active", active);
    if (active) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

function installScrollLinkedNav() {
  if (!("IntersectionObserver" in window)) return;
  const observer = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (visible && visible.target.dataset.section) updateActiveNav(visible.target.dataset.section);
  }, { rootMargin: "-35% 0px -45% 0px", threshold: [0.05, 0.2, 0.6] });
  document.querySelectorAll("[data-section]").forEach((section) => observer.observe(section));
}

function simpleItem(title, body, command) {
  const div = document.createElement("div");
  div.className = "list-item";
  div.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span><code>${escapeHtml(command || "None")}</code>`;
  return div;
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function isTypingTarget(target) {
  if (!target) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable;
}

const _rb = byId("refresh-button"); _rb?.addEventListener("click", () => loadSnapshot());
const _ccb = byId("clear-context-button"); _ccb?.addEventListener("click", () => clearContext());
const _ast = byId("agent-stack-toggle"); _ast?.addEventListener("click", () => {
  agentsExpanded = !agentsExpanded;
  renderLanes();
});
const _gf = byId("global-filter"); _gf?.addEventListener("input", (event) => {
  globalFilter = event.target.value;
  const currentTask = selectedTaskId ? taskById(selectedTaskId) : null;
  if (currentTask && !taskMatchesFilter(currentTask, globalFilter)) {
    selectedTaskId = firstVisibleTaskId();
  }
  render();
});
document.querySelectorAll("[data-toggle-section]").forEach((trigger) => {
  trigger.addEventListener("click", () => toggleSection(trigger.dataset.toggleSection));
  trigger.addEventListener("keydown", (event) => {
    if (event.key === " ") {
      event.preventDefault();
      toggleSection(trigger.dataset.toggleSection);
    }
  });
});
document.querySelectorAll("nav a").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    const section = link.getAttribute("href").slice(1);
    if (Object.prototype.hasOwnProperty.call(sectionState, section)) {
      sectionState[section] = "expanded";
    }
    setCurrentPage(section, { updateHash: true });
  });
});
window.addEventListener("hashchange", () => setCurrentPage(pageFromHash(), { scrollTop: true }));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && globalFilter && isTypingTarget(event.target)) {
    event.preventDefault();
    globalFilter = "";
    byId("global-filter").value = "";
    selectedTaskId = firstVisibleTaskId();
    render();
    return;
  }
  if (event.key === "Escape" && (selectedMapNode || selectedGoalSelection)) {
    clearContext();
    return;
  }
  if (isTypingTarget(event.target)) return;
  if (event.key === "g" && !event.metaKey && !event.ctrlKey && !event.altKey) {
    byId("orchestrator-command")?.focus?.();
    setCurrentPage("orchestrator", { updateHash: true });
    return;
  }
  if (event.key === "f" && !event.metaKey && !event.ctrlKey && !event.altKey) {
    event.preventDefault();
    byId("global-filter")?.focus?.();
    setCurrentPage("orchestrator", { updateHash: true, scrollTop: false });
    return;
  }
  if (event.key === "m" && !event.metaKey && !event.ctrlKey && !event.altKey) {
    setCurrentPage("map", { updateHash: true });
    return;
  }
  if (event.key === "l" && !event.metaKey && !event.ctrlKey && !event.altKey) {
    setCurrentPage("lanes", { updateHash: true });
  }
});
const _ap = byId("all-projects-button"); _ap?.addEventListener("click", async () => {
  selectedProjectId = null;
  selectedProjectName = null;
  selectedProjectPathStatus = null;
  selectedTaskId = null;
  selectedMapNode = null;
  selectedGoalSelection = null;
  await loadSnapshot(null);
});
currentPage = pageFromHash();
loadSnapshot().then(() => setCurrentPage(currentPage, { updateHash: window.location.hash !== `#${currentPage}`, scrollTop: false })).catch(() => {});
"""
