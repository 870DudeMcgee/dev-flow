from __future__ import annotations

TASK_CONTROL_WORKBENCH_CSS = """.next-task-action-slot .task-command-box { margin: 0; }
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
.pipeline-primary-context {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin-top: 8px;
}
.pipeline-context-item {
  background: var(--bg-2);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  min-width: 0;
  padding: 5px 7px;
}
.pipeline-context-item span {
  color: var(--text-muted);
  display: block;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.3px;
  line-height: 1.2;
  margin-bottom: 2px;
  text-transform: uppercase;
}
.pipeline-context-item strong {
  color: var(--text);
  display: block;
  font-size: 11px;
  font-weight: 650;
  line-height: 1.25;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
.step-evidence {
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.25;
  margin: 2px 0 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
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
.local-model-inventory {
  border-top: 1px solid var(--border-light);
  margin-top: 8px;
  padding-top: 8px;
  min-width: 0;
}
.local-model-summary {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.local-model-summary strong {
  color: var(--text);
  font-size: 11px;
  font-weight: 700;
}
.local-model-summary span,
.local-model-summary em {
  color: var(--text-muted);
  font-size: 10px;
  font-style: normal;
  line-height: 1.35;
  overflow-wrap: anywhere;
}
.local-model-list {
  display: grid;
  gap: 5px;
  margin-top: 7px;
  max-height: 240px;
  overflow-y: auto;
}
.local-model-item {
  align-items: center;
  border-top: 1px solid var(--border-light);
  display: grid;
  gap: 6px;
  grid-template-columns: minmax(0, 1fr) auto;
  min-width: 0;
  padding-top: 6px;
}
.local-model-item-main {
  display: grid;
  gap: 1px;
  min-width: 0;
}
.local-model-item-main strong {
  color: var(--text);
  font-size: 11px;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.local-model-item-main span,
.local-model-item-main em {
  color: var(--text-muted);
  font-size: 10px;
  font-style: normal;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.local-model-status {
  color: var(--text-soft);
  font-size: 10px;
  white-space: nowrap;
}
.local-model-action {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  cursor: pointer;
  font-size: 10px;
  grid-column: 2;
  padding: 3px 7px;
  white-space: nowrap;
}
.local-model-action:hover { border-color: var(--accent); color: var(--accent); }
.local-model-action:disabled { cursor: wait; opacity: 0.6; }
.local-model-readiness-actions {
  display: grid;
  gap: 6px;
  margin-top: 8px;
}
.local-model-readiness-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--text-muted);
  font-size: 11px;
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
  grid-template-columns: minmax(120px, 1fr) auto auto;
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
.worker-quick-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; grid-column: 1 / -1; justify-content: flex-start; }
.worker-action-chip {
  border-radius: 999px;
  line-height: 1.15;
  padding: 2px 8px;
  white-space: nowrap;
  font-size: 11px;
  max-width: 100%;
}
.worker-action-chip.btn-readonly {
  border: 1px solid rgba(100, 128, 172, 0.35);
}
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
.evidence-actions { display: flex; align-items: center; justify-content: flex-end; gap: 6px; }
.evidence-action-btn { margin: 0; }
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

"""
