from __future__ import annotations


WORKBENCH_CSS = """/* ===== UNIFIED CHAT WORKBENCH ===== */
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

@media (max-width: 1200px) {
  .workbench-stage-path { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 900px) {
  .unified-workbench-section .panel-subtitle { display: none; }
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
"""
