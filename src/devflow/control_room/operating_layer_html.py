from __future__ import annotations

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Dev-Flow Operating Layer — control room">
  <title>Dev-Flow Operating Layer</title>
  <link rel="stylesheet" href="/app.css">
</head>
<body>
  <div class="app-shell">

    <!-- ===== SIDEBAR ===== -->
    <aside class="sidebar" role="navigation" aria-label="Main navigation">

      <div class="brand">
        <span class="brand-mark">D</span>
        <div class="brand-text">
          <strong>DEV-FLOW</strong>
          <span>Operating Layer</span>
        </div>
      </div>

      <nav class="nav-list" aria-label="Sections">
        <a href="#home" class="nav-item active" data-nav="home">
          <svg class="nav-icon" viewBox="0 0 20 20" fill="currentColor" width="18" height="18"><path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z"/></svg>
          <span>Home</span>
        </a>
        <a href="#work" class="nav-item" data-nav="work">
          <svg class="nav-icon" viewBox="0 0 20 20" fill="currentColor" width="18" height="18"><path fill-rule="evenodd" d="M4 4a2 2 0 012-2h8a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 0h8v2H6V4zm0 4h8v2H6V8zm0 4h8v2H6v-2z" clip-rule="evenodd"/></svg>
          <span>Work</span>
        </a>
        <a href="#review" class="nav-item" data-nav="review">
          <svg class="nav-icon" viewBox="0 0 20 20" fill="currentColor" width="18" height="18"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>
          <span>Review</span>
        </a>
        <a href="#projects" class="nav-item" data-nav="projects">
          <svg class="nav-icon" viewBox="0 0 20 20" fill="currentColor" width="18" height="18"><path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"/></svg>
          <span>Projects</span>
        </a>
        <a href="#advanced" class="nav-item" data-nav="advanced">
          <svg class="nav-icon" viewBox="0 0 20 20" fill="currentColor" width="18" height="18"><path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/></svg>
          <span>Advanced</span>
        </a>
      </nav>

      <div class="sidebar-spacer"></div>

      <div class="sidebar-status-card">
        <span class="status-dot online" aria-hidden="true"></span>
        <div>
          <strong>Control Room</strong>
          <span class="status-sub">Local-first</span>
        </div>
      </div>

      <div class="sidebar-footer">
        <a href="#settings" class="nav-item small" data-nav="settings">
          <svg class="nav-icon" viewBox="0 0 20 20" fill="currentColor" width="16" height="16"><path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/></svg>
          <span>Settings</span>
        </a>
        <a href="#help" class="nav-item small" data-nav="help">
          <svg class="nav-icon" viewBox="0 0 20 20" fill="currentColor" width="16" height="16"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg>
          <span>Help</span>
        </a>
      </div>
    </aside>

    <!-- ===== MAIN ===== -->
    <main id="main-panel" role="main" aria-label="DevFlow Operating Layer">

      <!-- ===== TOP BAR ===== -->
      <header class="topbar">
        <div class="topbar-left">
          <div class="repo-selector" id="repo-selector" tabindex="0" role="button" aria-haspopup="true" aria-label="Select repository">
            <span class="repo-icon">⚑</span>
            <div class="repo-info">
              <span class="repo-label">Repository</span>
              <strong id="repo-name">DevFlow</strong>
              <span class="repo-path" id="repo-path">~/DevFlow</span>
            </div>
            <svg class="chevron" viewBox="0 0 20 20" fill="currentColor" width="14" height="14"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
          </div>

          <div class="topbar-pill" id="branch-pill">
            <span class="pill-icon">⑂</span>
            <span class="pill-label">Branch</span>
            <strong id="branch-name">main</strong>
          </div>

          <div class="topbar-pill">
            <span class="status-dot clean" aria-hidden="true"></span>
            <span class="pill-label">State</span>
            <strong id="tree-state">Clean</strong>
          </div>

          <div class="topbar-pill">
            <span class="pill-icon">◴</span>
            <span class="pill-label">Last sync</span>
            <strong id="last-sync">2m ago</strong>
          </div>
        </div>

        <div class="topbar-right">
          <button id="refresh-button" type="button" class="topbar-btn" title="Refresh snapshot">⟳ Refresh</button>
          <span class="control-status">
            <span class="status-dot online" aria-hidden="true"></span>
            Control Room Online
            <svg class="chevron" viewBox="0 0 20 20" fill="currentColor" width="12" height="12"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
          </span>
        </div>
      </header>

      <!-- ===== REPO SELECTOR DROPDOWN ===== -->
      <div id="repo-dropdown" class="repo-dropdown" role="listbox" aria-label="Select a repository" hidden>
        <div class="repo-dropdown-header">
          <span class="pill-label">Working directory</span>
        </div>
        <div id="repo-current-path" style="padding:4px 12px;font-size:11px;color:var(--text-muted);word-break:break-all;"></div>
        <div id="repo-browser" style="max-height:300px;overflow-y:auto;padding:4px 0;"></div>
        <div class="repo-dropdown-footer" style="padding:8px 12px;border-top:1px solid var(--border-light);display:flex;gap:8px;align-items:center;">
          <input type="text" id="repo-path-input" placeholder="Enter path..." style="flex:1;padding:4px 8px;font-size:12px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text);outline:none;">
          <button class="btn btn-sm btn-primary" id="repo-open-btn" type="button" style="padding:4px 12px;font-size:11px;">Open</button>
        </div>
      </div>

      <!-- ===== LAYOUT COLUMNS ===== -->
      <div class="layout-columns">

        <!-- Center: Brainstorm + Next Task -->
        <div class="center-column">

          <!-- Brainstorm -->
          <section id="brainstorm-section" class="panel brainstorm-section" aria-label="Brainstorm">
            <div class="panel-header">
              <h2 class="panel-title">Brainstorm</h2>
              <div class="panel-header-controls">
                <button class="btn btn-sm btn-secondary" id="brainstorm-new-session" type="button" style="padding:3px 10px;font-size:11px;">+ New</button>
                <div class="model-selector-wrap">
                  <span class="model-selector" id="model-selector" tabindex="0" role="button" aria-haspopup="listbox">
                    <span id="model-selector-label">DeepSeek V4 Flash Free</span>
                    <svg class="chevron" viewBox="0 0 20 20" fill="currentColor" width="12" height="12"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
                  </span>
                  <div class="model-dropdown" id="model-dropdown" hidden></div>
                </div>
                <label class="evidence-toggle">
                  <input type="checkbox" id="local-evidence-only" checked>
                  <span>Local evidence only</span>
                </label>
              </div>
            </div>

            <div id="brainstorm-transcript" class="brainstorm-transcript" role="log" aria-live="polite" aria-label="Brainstorm transcript"></div>

            <form id="brainstorm-chat-form" class="brainstorm-chat-form">
              <textarea id="brainstorm-message" autocomplete="off" placeholder="Ask DeepSeek anything about your idea, architecture, or next step..."></textarea>
              <div class="composer-row">
                <span class="composer-shortcuts">
                  <span class="shortcut-badge">@</span>
                  <span class="shortcut-badge">/</span>
                </span>
                <span class="newline-hint">Shift + Enter for newline</span>
                <button id="brainstorm-send" class="btn btn-primary" type="submit">
                  <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16"><path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/></svg>
                  Send
                </button>
              </div>
            </form>
          </section>

          <!-- Next Task section (below brainstorm) -->
          <section id="orchestrator-section" class="panel orchestrator-section next-task-section" aria-label="Next Task">
            <div class="panel-header">
              <h2 class="panel-title">Next Task</h2>
              <output id="orchestrator-sync" class="status-badge online" aria-live="polite" aria-atomic="true">Launchpad</output>
            </div>
            <div class="orchestrator-content next-task-content">
              <div class="orchestrator-directive next-task-summary">
                <span class="label">Selected Task</span>
                <h3 id="orchestrator-goal-title">Loading task...</h3>
                <p id="orchestrator-directive">Reading operating layer snapshot.</p>
              </div>
              <div id="next-task-meta" class="next-task-meta" aria-label="Selected task metadata"></div>
              <div class="next-task-definition">
                <span class="label">Definition of Done</span>
                <p id="next-task-definition-of-done">No definition captured yet.</p>
              </div>
              <div class="next-action">
                <span class="label">Next Safe Action</span>
                <code id="orchestrator-command">Loading...</code>
              </div>
              <div id="next-task-action-slot" class="next-task-action-slot"></div>
              <div id="next-task-latest-evidence" class="next-task-evidence"></div>
              <div class="orchestrator-agents next-task-switcher-wrap">
                <div class="label">Task switcher</div>
                <div id="orchestrator-agent-progress" class="agent-progress-list next-task-switcher"></div>
              </div>
              <div id="next-task-command-output"></div>
            </div>
          </section>

          <!-- Mission Feed -->
          <section id="mission-feed-section" class="panel mission-feed-section" aria-label="Work feed">
            <div class="panel-header">
              <h2 class="panel-title">Work Feed</h2>
              <output id="mission-feed-count" aria-live="polite" aria-atomic="true">0</output>
            </div>
            <div id="mission-feed-list" class="mission-feed-list"></div>
            <div id="guided-action-result" class="guided-action-result" aria-live="polite"></div>
          </section>

          <!-- Builder-Judge Loop -->
          <section id="builder-judge-section" class="panel builder-judge-section" aria-label="Builder-Judge Loop">
            <div class="panel-header">
              <h2 class="panel-title">Builder-Judge Loop</h2>
              <output id="bj-status-badge" class="status-badge" aria-live="polite" aria-atomic="true">Idle</output>
            </div>

            <div id="bj-form-area" class="bj-form-area">
              <div class="bj-form-group">
                <label for="bj-definition-of-done">Definition of Done <span class="bj-required">*</span></label>
                <textarea id="bj-definition-of-done" rows="3" placeholder="What does great look like? Be specific. The more honest you are, the better the judge can grade."></textarea>
              </div>

              <div class="bj-form-group">
                <label for="bj-starting-point">Starting Point <span class="bj-optional">(optional)</span></label>
                <textarea id="bj-starting-point" rows="2" placeholder="Seed text for the builder to start from, or leave blank."></textarea>
              </div>

              <div class="bj-form-row">
                <div class="bj-form-group">
                  <label for="bj-builder-model">Builder Model</label>
                  <select id="bj-builder-model"></select>
                </div>
                <div class="bj-form-group">
                  <label for="bj-judge-model">Judge Model</label>
                  <select id="bj-judge-model"></select>
                </div>
              </div>

              <div class="bj-form-row">
                <div class="bj-form-group">
                  <label for="bj-pass-threshold">Pass Threshold</label>
                  <input type="number" id="bj-pass-threshold" min="50" max="100" value="85" style="width:80px;">
                </div>
                <div class="bj-form-group">
                  <label for="bj-max-rounds">Max Rounds</label>
                  <input type="number" id="bj-max-rounds" min="1" max="20" value="5" style="width:80px;">
                </div>
                <div class="bj-form-group bj-checkbox-group">
                  <label class="bj-checkbox-label">
                    <input type="checkbox" id="bj-escalate" checked>
                    <span>Escalate if max rounds reached</span>
                  </label>
                </div>
              </div>

              <button id="bj-run-btn" class="btn btn-primary" type="button" style="width:100%;">
                ▶ Run Loop
              </button>
            </div>

            <div id="bj-progress-area" class="bj-progress-area" hidden>
              <div class="bj-rounds-header">
                <span class="label">Rounds</span>
                <span id="bj-round-summary" class="bj-round-summary"></span>
              </div>
              <div id="bj-rounds-list" class="bj-rounds-list"></div>
            </div>

            <div id="bj-result-area" class="bj-result-area" hidden>
              <div class="bj-result-header">
                <h3>Final Result</h3>
                <span id="bj-final-score" class="bj-score-badge"></span>
              </div>
              <div id="bj-final-draft" class="bj-final-draft"></div>
              <div id="bj-stop-reason" class="bj-stop-reason"></div>
              <div id="bj-next-action" class="bj-next-action"></div>
            </div>

            <div class="bj-history-header">
              <span class="label">Recent Loops</span>
              <button class="btn btn-sm btn-secondary" id="bj-refresh-list" type="button" style="padding:2px 8px;font-size:10px;">↻</button>
            </div>
            <div id="bj-loops-list" class="bj-loops-list"></div>
          </section>
        </div>

        <!-- Right: Pipeline + Health -->
        <div class="right-column">
          <section class="panel pipeline-section" aria-label="Pipeline">
            <div class="panel-header">
              <h2 class="panel-title">Pipeline</h2>
              <span class="info-icon" title="Pipeline stages for the current project">ⓘ</span>
            </div>
            <div class="pipeline-stages">
               <div class="pipeline-step active" data-stage="brainstorm">
                <div class="step-number">
                  <span>01</span>
                  <svg class="step-connector" width="2" height="24"><line x1="1" y1="0" x2="1" y2="24" stroke="currentColor" stroke-width="2"/></svg>
                </div>
                <div class="step-content">
                  <div class="step-row">
                    <strong>Brainstorm</strong>
                    <span class="step-status active">Active</span>
                  </div>
                  <p class="step-desc">Refining ideas in active discussion.</p>
                  <p class="step-action">
                    <button type="button" class="btn btn-sm btn-primary" data-brainstorm-stage="spec">Escalate to Spec →</button>
                    <button type="button" class="btn btn-sm btn-secondary" data-bj-quality-gate="spec" title="Run builder-judge quality gate before escalating">QC Gate</button>
                  </p>
                </div>
              </div>
              <div class="pipeline-step locked" data-stage="spec">
                <div class="step-number">
                  <span>02</span>
                  <svg class="step-connector" width="2" height="24"><line x1="1" y1="0" x2="1" y2="24" stroke="currentColor" stroke-width="2"/></svg>
                </div>
                <div class="step-content">
                  <div class="step-row">
                    <strong>Spec</strong>
                    <span class="step-status pending">Pending</span>
                  </div>
                  <p class="step-desc">Freeze the intent as local spec evidence.</p>
                  <p class="step-action">
                    <button type="button" class="btn btn-sm btn-secondary" data-brainstorm-stage="plan">Generate Plan →</button>
                    <button type="button" class="btn btn-sm btn-secondary" data-bj-quality-gate="plan" title="Run builder-judge quality gate before generating plan">QC Gate</button>
                  </p>
                </div>
              </div>
              <div class="pipeline-step locked" data-stage="plan">
                <div class="step-number">
                  <span>03</span>
                </div>
                <div class="step-content">
                  <div class="step-row">
                    <strong>Plan</strong>
                    <span class="step-status pending">Pending</span>
                  </div>
                  <p class="step-desc">Convert the transcript into an implementation plan artifact.</p>
                  <p class="step-action">
                    <button type="button" class="btn btn-sm btn-secondary" data-brainstorm-stage="implementation">Create Task →</button>
                  </p>
                </div>
              </div>
            </div>
            <div class="definition-editor">
              <label for="brainstorm-definition-of-done">Definition of Done</label>
              <textarea id="brainstorm-definition-of-done" rows="4" placeholder="What must be true before this brainstorm becomes done?"></textarea>
            </div>
          </section>

          <!-- System Health -->
          <section class="panel health-section" aria-label="System health">
            <div class="panel-header">
              <h2 class="panel-title">System Health</h2>
              <output id="orchestrator-health-label" class="status-badge online" aria-live="polite" aria-atomic="true">Nominal</output>
            </div>
            <div id="orchestrator-health-bars" class="health-bars"></div>
            <div class="health-meta">
              <div><span class="label">Freshness</span><output id="orchestrator-freshness">unknown</output></div>
              <div><span class="label">Goal</span><output id="orchestrator-goal-id">none</output></div>
            </div>
          </section>

          <!-- Brainstorm History -->
          <section class="panel history-panel" aria-label="Brainstorm history">
            <div class="panel-header">
              <h2 class="panel-title" style="font-size:13px;">History</h2>
              <button class="btn btn-sm btn-secondary" id="brainstorm-new-session-side" type="button" style="padding:2px 8px;font-size:10px;">+ New</button>
            </div>
            <div id="brainstorm-sessions-list" class="history-list"></div>
          </section>
        </div>
      </div>

      <!-- ===== BOTTOM DOCK ===== -->
      <div class="bottom-dock">
        <!-- Worker lanes -->
        <section class="dock-panel" aria-labelledby="worker-lanes-heading">
          <div class="dock-panel-header">
            <h3 id="worker-lanes-heading">Worker lanes</h3>
            <output id="active-work-count" class="dock-count" aria-live="polite" aria-atomic="true">0 tasks</output>
            <a href="#" class="dock-view-all">View all →</a>
          </div>
          <div id="active-work-groups" class="worker-lanes-list" role="list" aria-label="Task cards"></div>
        </section>

        <!-- Review queue -->
        <section class="dock-panel" aria-labelledby="review-queue-heading">
          <div class="dock-panel-header">
            <h3 id="review-queue-heading">Review queue</h3>
            <output id="review-queue-count" class="dock-count" aria-live="polite" aria-atomic="true">0 items</output>
            <a href="#" class="dock-view-all">View all →</a>
          </div>
          <div id="guided-review-queue" class="review-queue-list" role="list" aria-label="Review items"></div>
        </section>

        <!-- Evidence stream -->
        <section class="dock-panel" aria-labelledby="evidence-stream-heading">
          <div class="dock-panel-header">
            <h3 id="evidence-stream-heading">Evidence stream</h3>
            <output id="evidence-stream-count" class="dock-count" aria-live="polite" aria-atomic="true">0 items</output>
            <a href="#" class="dock-view-all">View all →</a>
          </div>
          <div id="guided-evidence-stream" class="evidence-stream-list" role="list" aria-label="Evidence items"></div>
        </section>
      </div>

      <!-- ===== FOOTER ===== -->
      <footer class="app-footer">
        <span class="status-dot online" aria-hidden="true"></span>
        <span>Local-first mode</span>
        <span class="footer-sep">·</span>
        <span>All data stored locally</span>
        <span class="footer-sep">·</span>
        <span class="version">Dev-Flow v0.1.0</span>
      </footer>

      <!-- ===== FOCUS/DETAIL OVERLAY ===== -->
      <div id="focus-overlay" class="focus-overlay" role="dialog" aria-modal="true" aria-label="Item detail" hidden>
        <div class="focus-panel" id="focus-panel">
          <button id="focus-close" class="focus-close" type="button" aria-label="Close detail">&times;</button>
          <div id="focus-content"></div>
        </div>
      </div>

    </main>
  </div>
  <script src="/app.js"></script>
</body>
</html>
"""
