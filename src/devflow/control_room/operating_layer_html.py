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
          <div id="task-review-panel" class="task-review-panel" aria-live="polite" aria-atomic="true" aria-label="Selected task review"></div>
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

