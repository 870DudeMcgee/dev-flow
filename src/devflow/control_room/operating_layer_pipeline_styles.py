from __future__ import annotations


PIPELINE_CSS = """/* ===== PIPELINE SECTION ===== */
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

@media (max-width: 900px) {
  .pipeline-stages { padding: 8px 12px; }
  .pipeline-primary-context { grid-template-columns: 1fr; }
  .pipeline-step { gap: 8px; }
  .pipeline-step:not(:last-child) { padding-bottom: 4px; }
  .step-number { min-width: 24px; }
  .step-number span { width: 24px; height: 24px; font-size: 11px; }
  .step-connector { height: 16px; }
  .step-desc { display: none; }
  .step-action { margin-top: 4px; }
}
"""
