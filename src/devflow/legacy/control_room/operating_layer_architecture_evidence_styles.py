from __future__ import annotations


ARCHITECTURE_EVIDENCE_CSS = """/* ===== ARCHITECTURE EVIDENCE ===== */
.architecture-evidence-section {
  margin-top: 8px;
}
.architecture-evidence-section.is-stale {
  border-color: rgba(210, 153, 34, 0.34);
}
.architecture-evidence-content {
  display: grid;
  gap: 10px;
  padding: 12px 14px 14px;
}
.architecture-summary-row {
  align-items: stretch;
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(0, 1fr) minmax(240px, 0.62fr);
}
.architecture-summary-main,
.architecture-next-action,
.architecture-evidence-block,
.architecture-metric {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
}
.architecture-summary-main,
.architecture-next-action {
  display: grid;
  gap: 5px;
  min-width: 0;
  padding: 10px 11px;
}
.architecture-summary-main strong {
  color: var(--text);
  font-size: 13px;
  line-height: 1.35;
}
.architecture-summary-main span,
.architecture-next-action span,
.architecture-evidence-block li span,
.architecture-empty {
  color: var(--text-soft);
  font-size: 12px;
  line-height: 1.4;
}
.architecture-source-chip {
  color: var(--text-muted) !important;
  font-size: 10px !important;
  font-weight: 700;
  letter-spacing: 0.35px;
  text-transform: uppercase;
}
.architecture-next-action {
  align-content: start;
}
.architecture-next-action code {
  background: #070a0f;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  display: block;
  font-size: 11px;
  min-width: 0;
  overflow: hidden;
  padding: 6px 8px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.architecture-next-action .btn {
  justify-self: start;
}
.architecture-metric-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(6, minmax(0, 1fr));
}
.architecture-metric {
  border-left: 3px solid var(--border);
  display: grid;
  gap: 2px;
  min-width: 0;
  padding: 8px 9px;
}
.architecture-metric span,
.architecture-evidence-block h4 {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.35px;
  margin: 0;
  text-transform: uppercase;
}
.architecture-metric strong {
  color: var(--text);
  font-size: 13px;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.architecture-freshness {
  border-left-color: var(--orange);
}
.architecture-diagnostics {
  border-left-color: var(--blue);
}
.architecture-evidence-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.architecture-evidence-block {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 10px 11px;
}
.architecture-question-block {
  grid-column: 1 / -1;
}
.architecture-artifact-list,
.architecture-diagnostic-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}
.architecture-provenance-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
}
.architecture-provenance {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  display: grid;
  gap: 2px;
  min-width: 0;
  padding: 8px 9px;
}
.architecture-provenance span {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.35px;
  text-transform: uppercase;
}
.architecture-provenance strong {
  color: var(--text);
  font-size: 12px;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.architecture-action-row {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.architecture-viewer-overlay .architecture-viewer-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 86vh;
  max-width: min(1100px, 94vw);
  width: 94vw;
}
.architecture-viewer-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.architecture-viewer-header strong {
  color: var(--text);
  font-size: 14px;
}
.architecture-viewer-report {
  background: #070a0f;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  flex: 1 1 auto;
  font-size: 12px;
  line-height: 1.45;
  margin: 0;
  max-height: 74vh;
  overflow: auto;
  padding: 12px 14px;
  white-space: pre-wrap;
  word-break: break-word;
}
.architecture-viewer-frame {
  background: #ffffff;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  flex: 1 1 auto;
  min-height: 60vh;
  width: 100%;
}
.architecture-artifact-chip,
.architecture-diagnostic-chip {
  align-items: center;
  background: var(--bg-2);
  border: 1px solid var(--border-light);
  border-radius: 999px;
  display: inline-flex;
  gap: 6px;
  max-width: 100%;
  min-width: 0;
  padding: 3px 8px;
}
.architecture-artifact-chip strong,
.architecture-diagnostic-chip {
  color: var(--text-soft);
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}
.architecture-artifact-chip code {
  color: var(--text-muted);
  font-size: 10px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.architecture-evidence-block ul {
  display: grid;
  gap: 6px;
  list-style: none;
  margin: 0;
  padding: 0;
}
.architecture-evidence-block li {
  border-top: 1px solid var(--border-light);
  display: grid;
  gap: 2px;
  min-width: 0;
  padding-top: 6px;
}
.architecture-evidence-block li:first-child {
  border-top: 0;
  padding-top: 0;
}
.architecture-evidence-block li strong {
  color: var(--text);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

@media (max-width: 1200px) {
  .architecture-metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .architecture-provenance-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 900px) {
  .architecture-summary-row,
  .architecture-evidence-grid { grid-template-columns: 1fr; }
  .architecture-metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .architecture-provenance-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .architecture-question-block { grid-column: auto; }
}
"""
