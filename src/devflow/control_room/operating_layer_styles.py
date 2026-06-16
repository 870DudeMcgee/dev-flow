from __future__ import annotations

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

.review-loop-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  background: var(--panel-2);
  display: grid;
  gap: 8px;
}

.review-loop-card.ready_to_promote {
  border-color: var(--teal);
}

.review-loop-card.needs_human_decision {
  border-color: var(--red);
}

.review-loop-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.review-loop-metrics span {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  background: var(--panel);
}

.scheduler-block {
  border-top: 1px solid var(--border);
  padding: 12px 0 0;
  display: grid;
  gap: 10px;
}

.scheduler-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(92px, 1fr));
  gap: 8px;
}

.scheduler-grid div {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  background: var(--panel);
}

.scheduler-grid span {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.scheduler-grid strong {
  display: block;
  margin-top: 4px;
  color: var(--text);
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

.approved-verification-control,
.approved-promotion-control {
  display: grid;
  gap: 6px;
  margin-top: 12px;
}

.approved-verification-control input,
.approved-promotion-control input,
.approved-promotion-control textarea {
  width: 100%;
  min-height: 36px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-strong);
  color: var(--text);
  padding: 8px 10px;
  font: inherit;
  font-size: var(--type-body);
}

.approved-promotion-control textarea {
  min-height: 74px;
  resize: vertical;
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

.task-review-panel {
  border: 1px solid rgba(15, 118, 110, 0.24);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(240, 253, 250, 0.88), rgba(255, 255, 255, 0.96));
  padding: 14px;
  box-shadow: var(--shadow-sm);
}

.task-review-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: start;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(15, 118, 110, 0.18);
}

.task-review-head span,
.task-review-item span,
.review-approval-card span {
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.task-review-head h3 {
  margin: 4px 0 0;
  color: var(--text);
  font-size: 20px;
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.task-review-head p {
  margin: 6px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.4;
}

.task-review-head > strong {
  border: 1px solid rgba(15, 118, 110, 0.22);
  border-radius: 999px;
  background: var(--panel);
  color: var(--teal);
  padding: 6px 10px;
  font-size: 12px;
  white-space: nowrap;
}

.task-review-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.task-review-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.72fr);
  gap: 12px;
  margin-top: 12px;
  align-items: start;
}

.task-review-brief {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.task-review-row {
  display: grid;
  grid-template-columns: 128px minmax(0, 1fr);
  gap: 12px;
  align-items: baseline;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  padding: 10px;
}

.task-review-row.stack {
  align-items: start;
}

.task-review-row span,
.task-review-preview summary {
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.task-review-row strong {
  min-width: 0;
  color: var(--text);
  font-size: 13px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.task-review-row pre,
.task-review-preview pre {
  margin: 0;
  color: var(--text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.task-review-row pre {
  max-height: 116px;
  overflow: auto;
}

.worker-lane-block,
.local-worker-lane-block {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  min-width: 0;
  border: 1px solid rgba(15, 118, 110, 0.22);
  border-radius: 7px;
  background: rgba(240, 253, 250, 0.72);
  padding: 10px;
}

.worker-lane-block span,
.local-worker-lane-block span {
  display: block;
  color: var(--muted);
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}

.worker-lane-block strong,
.local-worker-lane-block strong {
  display: block;
  margin-top: 4px;
  color: var(--text);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.worker-lane-block code {
  display: block;
  margin-top: 6px;
  color: var(--teal);
  font-size: 11px;
  overflow-wrap: anywhere;
  white-space: normal;
}

.worker-lane-block p {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.local-worker-lane-block div:last-child {
  grid-column: 1 / -1;
}

.task-review-preview {
  margin-top: 12px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--panel);
  padding: 10px;
}

.task-review-preview summary {
  cursor: pointer;
}

.task-review-preview pre {
  max-height: 220px;
  margin-top: 10px;
  overflow: auto;
}

.task-review-item {
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  padding: 10px;
}

.task-review-item.wide {
  grid-column: span 3;
}

.task-review-item pre {
  margin: 6px 0 0;
  color: var(--text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.review-approval-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(240px, 0.7fr) auto;
  gap: 10px;
  align-items: end;
  margin-top: 12px;
  border: 1px solid rgba(22, 163, 74, 0.28);
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(240, 253, 244, 0.9), #ffffff);
  padding: 12px;
}

.review-approval-card.muted {
  align-items: start;
  grid-template-columns: 1fr;
  border-color: var(--border);
  background: var(--panel);
}

.review-approval-card strong {
  display: block;
  margin-top: 4px;
  color: var(--text);
  font-size: 15px;
}

.review-approval-card code {
  display: block;
  margin-top: 8px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.review-approval-card label {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.review-approval-card input,
.review-approval-card textarea {
  width: 100%;
  min-height: 38px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel-strong);
  color: var(--text);
  padding: 8px 10px;
  font: inherit;
  font-size: var(--type-body);
}

.review-approval-card textarea {
  min-height: 96px;
  resize: vertical;
}

.review-approval-card button {
  min-height: 38px;
  border-color: rgba(22, 163, 74, 0.42);
  background: var(--green);
  color: #ffffff;
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
.agents-canvas.collapsed .model-catalog-panel,
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

.model-catalog-panel {
  min-width: 0;
  padding: 14px;
  border: 1px solid rgba(168, 156, 222, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.045);
}

.model-catalog-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.model-catalog-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(168, 156, 222, 0.12);
  border-radius: 6px;
  background: rgba(12, 14, 24, 0.44);
}

.model-catalog-row div {
  min-width: 0;
}

.model-catalog-row strong,
.model-catalog-row span {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-catalog-row strong {
  color: #fff;
  font-size: 13px;
}

.model-catalog-row span {
  color: rgba(224, 225, 246, 0.68);
  font-size: 11px;
}

.model-catalog-row button,
.model-catalog-add {
  min-height: 34px;
  border-color: rgba(102, 240, 209, 0.24);
  background: rgba(102, 240, 209, 0.08);
  color: var(--teal);
}

.model-catalog-add {
  justify-self: start;
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

.task-review-panel {
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(143, 216, 255, 0.24);
  border-radius: 8px;
  background:
    radial-gradient(circle at 8% 10%, rgba(102, 240, 209, 0.18), transparent 16rem),
    radial-gradient(circle at 92% 0%, rgba(165, 128, 255, 0.17), transparent 18rem),
    linear-gradient(135deg, rgba(255, 255, 255, 0.08), rgba(255, 255, 255, 0.025)),
    rgba(12, 13, 27, 0.74);
  box-shadow:
    0 24px 70px rgba(0, 0, 0, 0.32),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(22px);
}

.task-review-panel::before {
  content: "";
  position: absolute;
  inset: 0 0 auto;
  height: 1px;
  background: linear-gradient(90deg, rgba(102, 240, 209, 0.7), rgba(143, 216, 255, 0.34), transparent);
  opacity: 0.82;
}

.task-review-head {
  position: relative;
  border-bottom-color: rgba(143, 216, 255, 0.14);
}

.task-review-head span,
.task-review-item span,
.review-approval-card span {
  color: rgba(213, 219, 244, 0.7);
}

.task-review-head h3 {
  color: #ffffff;
  text-shadow: 0 0 20px rgba(143, 216, 255, 0.12);
}

.task-review-head p {
  color: rgba(213, 219, 244, 0.7);
}

.task-review-head > strong {
  border-color: rgba(102, 240, 209, 0.32);
  background: rgba(102, 240, 209, 0.12);
  color: var(--teal);
  box-shadow: 0 0 20px rgba(102, 240, 209, 0.11);
}

.task-review-item,
.task-review-row,
.task-review-preview,
.review-approval-card {
  border: 1px solid rgba(168, 156, 222, 0.16);
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.075), rgba(255, 255, 255, 0.026)),
    rgba(16, 17, 32, 0.68);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 12px 34px rgba(0, 0, 0, 0.18);
  backdrop-filter: blur(14px);
}

.task-review-item {
  border-radius: 7px;
}

.task-review-layout .review-approval-card {
  grid-template-columns: 1fr;
  align-items: stretch;
  margin-top: 0;
}

.task-review-brief {
  gap: 8px;
}

.task-review-row {
  grid-template-columns: 118px minmax(0, 1fr);
}

.task-review-row span,
.task-review-preview summary {
  color: rgba(213, 219, 244, 0.68);
}

.task-review-row strong,
.task-review-row pre,
.task-review-preview pre {
  color: rgba(248, 249, 255, 0.9);
}

.worker-lane-block,
.local-worker-lane-block {
  border-color: rgba(102, 240, 209, 0.2);
  background:
    linear-gradient(135deg, rgba(102, 240, 209, 0.08), rgba(143, 216, 255, 0.04)),
    rgba(11, 18, 27, 0.64);
}

.worker-lane-block span,
.worker-lane-block p,
.local-worker-lane-block span {
  color: rgba(213, 219, 244, 0.68);
}

.worker-lane-block strong,
.local-worker-lane-block strong {
  color: rgba(248, 249, 255, 0.94);
}

.worker-lane-block code {
  color: var(--teal);
}

.task-review-preview {
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.055), rgba(255, 255, 255, 0.018)),
    rgba(10, 12, 24, 0.58);
}

.task-review-preview summary {
  list-style: none;
}

.task-review-preview summary::-webkit-details-marker {
  display: none;
}

.task-review-preview summary::after {
  content: "Open";
  float: right;
  color: var(--teal);
  font-family: var(--font-mono);
}

.task-review-preview[open] summary::after {
  content: "Close";
}

.task-review-item pre {
  color: rgba(248, 249, 255, 0.9);
}

.review-approval-card {
  border-color: rgba(121, 242, 178, 0.24);
  background:
    radial-gradient(circle at 95% 10%, rgba(121, 242, 178, 0.11), transparent 12rem),
    linear-gradient(135deg, rgba(121, 242, 178, 0.08), rgba(165, 128, 255, 0.045)),
    rgba(13, 18, 30, 0.72);
}

.review-approval-card.muted {
  border-color: rgba(168, 156, 222, 0.16);
  background:
    linear-gradient(135deg, rgba(255, 255, 255, 0.06), rgba(255, 255, 255, 0.02)),
    rgba(16, 17, 32, 0.66);
}

.review-approval-card strong {
  color: #ffffff;
}

.review-approval-card input,
.review-approval-card textarea,
.approved-promotion-control textarea {
  border-color: rgba(143, 216, 255, 0.22);
  background: rgba(5, 8, 14, 0.62);
  color: #ffffff;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.review-approval-card input::placeholder,
.review-approval-card textarea::placeholder,
.approved-promotion-control textarea::placeholder {
  color: rgba(213, 219, 244, 0.44);
}

.review-approval-card input:focus,
.review-approval-card textarea:focus,
.approved-promotion-control textarea:focus {
  outline: 0;
  border-color: rgba(102, 240, 209, 0.64);
  box-shadow: 0 0 0 3px rgba(102, 240, 209, 0.12), 0 0 24px rgba(102, 240, 209, 0.14);
}

.review-approval-card button {
  border-color: rgba(121, 242, 178, 0.4);
  background:
    linear-gradient(135deg, rgba(121, 242, 178, 0.95), rgba(102, 240, 209, 0.78));
  color: #08111a;
  box-shadow: 0 0 22px rgba(121, 242, 178, 0.18);
}

.review-approval-card button:disabled {
  border-color: rgba(168, 156, 222, 0.14);
  background: rgba(255, 255, 255, 0.06);
  color: rgba(213, 219, 244, 0.44);
  box-shadow: none;
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

#command { order: 1; }
#guided { order: 2; }
#orchestrator { order: 3; }
#map { order: 4; }
#lanes { order: 5; }
#goals { order: 6; }
#projects { order: 7; }
#gates { order: 8; }
#attention { order: 9; }
#inbox { order: 10; }
#promotion { order: 11; }
#actions { order: 12; }
#specs { order: 13; }
#evidence { order: 14; }
#context { order: 15; }

.guided-control-room {
  display: grid;
  grid-template-columns: minmax(280px, 1.15fr) minmax(260px, 0.85fr);
  gap: 12px;
  min-width: 0;
}

.idea-intake-panel {
  grid-column: 1 / -1;
}

.guided-panel {
  min-width: 0;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(14, 16, 31, 0.78);
  box-shadow: var(--shadow);
}

.active-work-panel,
.review-queue-panel {
  min-height: 280px;
}

.next-step-panel h2 {
  margin: 10px 0 6px;
  font-size: clamp(24px, 3vw, 42px);
  line-height: 1;
}

.next-step-panel p,
.guided-task-card p {
  margin: 0;
  color: var(--muted);
  line-height: 1.45;
}

.next-step-panel code,
.review-queue-card code,
.guided-task-card code,
.action-result code {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
}

.guided-action-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
}

.primary-action,
.secondary-action,
.guided-task-actions button,
.action-run-button {
  min-height: 38px;
  border: 1px solid rgba(102, 240, 209, 0.42);
  border-radius: 7px;
  background: rgba(102, 240, 209, 0.14);
  color: #f8fbff;
  font-size: var(--type-body);
  font-weight: 800;
  cursor: pointer;
}

.primary-action,
.secondary-action {
  padding: 0 14px;
}

.primary-action:disabled,
.secondary-action:disabled,
.guided-task-actions button:disabled,
.action-run-button:disabled {
  opacity: 0.48;
  cursor: not-allowed;
}

.idea-intake-form,
.start-work-form {
  display: grid;
  gap: 12px;
}

.idea-intake-form textarea {
  width: 100%;
  min-width: 0;
  min-height: 118px;
  resize: vertical;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.065);
  color: var(--text);
  padding: 10px 12px;
  font: inherit;
  line-height: 1.45;
}

.idea-intake-form textarea::placeholder,
.idea-intake-form input::placeholder,
.start-work-form input::placeholder {
  color: rgba(225, 231, 245, 0.42);
}

.task-create-toggle {
  margin-top: 12px;
}

.task-create-toggle .start-work-form {
  margin-top: 10px;
}

.idea-intake-form input,
.start-work-form input,
.guided-command-input input,
.guided-timeout-input input,
.approved-timeout-control input {
  width: 100%;
  min-width: 0;
  min-height: 38px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.055);
  color: var(--text);
  padding: 8px 10px;
  font: inherit;
}

.advanced-toggle {
  border: 1px solid rgba(168, 156, 222, 0.18);
  border-radius: 7px;
  padding: 8px 10px;
}

.advanced-toggle summary {
  cursor: pointer;
  color: var(--muted);
  font-weight: 800;
}

.inline-control {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  color: var(--text);
}

.active-work-groups {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.guided-work-group {
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(168, 156, 222, 0.16);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.035);
}

.guided-group-heading,
.guided-task-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.guided-group-heading span,
.guided-task-top span {
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: var(--type-caption);
  font-weight: 900;
  text-transform: uppercase;
}

.guided-task-stack {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}

.guided-task-card {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 8px;
  background: rgba(9, 10, 19, 0.58);
}

.guided-task-card h3 {
  margin: 2px 0 0;
  font-size: 15px;
  line-height: 1.2;
}

.guided-task-top strong {
  flex: 0 0 auto;
  color: var(--teal);
  font-size: var(--type-caption);
}

.guided-task-actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: end;
}

.guided-timeout-input {
  max-width: 118px;
}

.guided-task-actions button {
  padding: 0 10px;
}

.review-queue-list {
  display: grid;
  gap: 8px;
}

.review-queue-card {
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 10px;
  border: 1px solid rgba(102, 240, 209, 0.18);
  border-radius: 8px;
  background: rgba(102, 240, 209, 0.06);
}

.review-queue-card span {
  color: var(--muted);
  font-size: var(--type-caption);
  font-weight: 900;
  text-transform: uppercase;
}

.guided-action-result {
  margin-top: 12px;
}

.action-result {
  display: grid;
  gap: 8px;
}

.action-preview-grid small {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-size: var(--type-caption);
}

@media (max-width: 1040px) {
  .guided-control-room {
    grid-template-columns: 1fr;
  }

  .active-work-groups {
    grid-template-columns: 1fr;
  }

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
  .progress-step-grid,
  .task-review-layout,
  .task-review-grid,
  .review-approval-card {
    grid-template-columns: 1fr;
  }

  .task-review-item.wide {
    grid-column: span 1;
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
  .task-review-layout,
  .task-review-grid,
  .review-approval-card,
  .goal-metrics {
    grid-template-columns: 1fr;
  }

  .task-review-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  .task-review-item.wide {
    grid-column: span 1;
  }

  .task-review-head {
    display: grid;
  }

  .task-review-head > strong {
    justify-self: start;
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
  .guided-panel,
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
