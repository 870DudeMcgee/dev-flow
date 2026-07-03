from __future__ import annotations


OBSIDIAN_INTAKE_CSS = """/* ===== OBSIDIAN INTAKE ===== */
.obsidian-intake-section {
  min-width: 0;
}
.obsidian-intake-section:not(.is-ready) {
  display: none;
}
.obsidian-intake-section.is-unavailable .panel-header {
  min-height: 44px;
  padding: 8px 12px;
}
.obsidian-intake-section.is-unavailable .panel-subtitle {
  display: none;
}
.obsidian-intake-lane-counts:empty,
.obsidian-intake-body:empty {
  display: none;
}
.obsidian-intake-lane-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 14px 8px;
}
.obsidian-lane-chip {
  align-items: center;
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: 999px;
  color: var(--text-soft);
  display: inline-flex;
  font-size: 11px;
  gap: 6px;
  min-height: 24px;
  padding: 4px 9px;
}
.obsidian-lane-chip strong {
  color: var(--text);
  font-size: 11px;
}
.obsidian-intake-body {
  border-top: 1px solid var(--border-light);
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(220px, 0.8fr) minmax(0, 1.2fr);
  padding: 10px 14px 14px;
}
.obsidian-intake-empty {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font-size: 12px;
  padding: 10px 12px;
}
.obsidian-intake-empty.error {
  border-left: 3px solid var(--red);
  color: var(--text);
}
.obsidian-intake-list {
  display: grid;
  gap: 6px;
  max-height: 260px;
  overflow: auto;
}
.obsidian-intake-card {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: inherit;
  cursor: pointer;
  display: grid;
  gap: 3px;
  min-width: 0;
  padding: 8px 10px;
  text-align: left;
}
.obsidian-intake-card.is-selected {
  border-color: rgba(88, 166, 255, 0.35);
  box-shadow: inset 0 0 0 1px rgba(88, 166, 255, 0.2);
}
.obsidian-intake-card strong {
  color: var(--text);
  font-size: 12px;
}
.obsidian-intake-card-meta,
.obsidian-intake-card-summary,
.obsidian-intake-detail-meta,
.obsidian-intake-detail-grid div span,
.obsidian-intake-detail-actions-status {
  color: var(--text-soft);
  font-size: 11px;
}
.obsidian-intake-card-summary {
  overflow: hidden;
  text-overflow: ellipsis;
}
.obsidian-intake-detail {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  display: grid;
  gap: 10px;
  min-width: 0;
  padding: 10px 12px;
}
.obsidian-intake-detail-header {
  display: grid;
  gap: 4px;
}
.obsidian-intake-detail-header h4 {
  color: var(--text);
  font-size: 14px;
  margin: 0;
}
.obsidian-intake-detail-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.obsidian-intake-detail-grid div {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.obsidian-intake-detail-grid div strong {
  color: var(--text);
  font-size: 11px;
}
.obsidian-intake-detail-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.obsidian-intake-detail-actions-status {
  margin-left: auto;
}
@media (max-width: 900px) {
  .obsidian-intake-body {
    grid-template-columns: 1fr;
  }
}
"""
