from __future__ import annotations

MODEL_PICKER_CSS = """.model-selector {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--bg-3);
  border: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-soft);
  cursor: pointer;
}
.model-selector .chevron { color: var(--text-muted); }
.model-selector.is-starting { cursor: wait; border-color: var(--orange); }
.model-selector-wrap { position: relative; }
.model-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  z-index: 100;
  min-width: 280px;
  max-height: 320px;
  overflow-y: auto;
}
.model-dropdown-item {
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--border-light);
  transition: background 0.1s;
}
.model-dropdown-item:last-child { border-bottom: none; }
.model-dropdown-item:hover { background: var(--bg-3); }
.model-dropdown-item.active { background: var(--accent-bg); }
.model-dropdown-item .md-name { font-size: 12px; font-weight: 600; color: var(--text); }
.model-dropdown-item .md-model { font-size: 10px; color: var(--text-muted); margin-top: 2px; }
.model-dropdown-item .md-purpose { font-size: 10px; color: var(--text-soft); margin-top: 2px; line-height: 1.3; }
.model-dropdown-section { border-bottom: 1px solid var(--border-light); }
.model-dropdown-section:last-child { border-bottom: none; }
.model-dropdown-section-title {
  color: var(--text-soft);
  font-size: 10px;
  letter-spacing: 0.3px;
  padding: 7px 12px 3px;
  text-transform: uppercase;
}
.model-dropdown-inventory-item { cursor: default; }
.model-setup-section { background: rgba(255, 255, 255, 0.012); }
.model-setup-toggle {
  align-items: center;
  background: none;
  border: none;
  color: var(--text-soft);
  cursor: pointer;
  display: flex;
  gap: 8px;
  padding: 7px 12px;
  text-align: left;
  width: 100%;
}
.model-setup-toggle .model-dropdown-section-title { padding: 0; }
.model-setup-counts {
  color: var(--orange);
  font-size: 10px;
  font-weight: 700;
  margin-left: auto;
}
.model-setup-chevron {
  color: var(--text-muted);
  font-size: 10px;
  transition: transform 0.15s ease;
}
.model-setup-toggle[aria-expanded="true"] .model-setup-chevron { transform: rotate(180deg); }
.model-setup-body { border-top: 1px dashed var(--border-light); }
.model-setup-body .model-dropdown-inventory-item { opacity: 0.92; }
.model-dropdown-empty .md-purpose { color: var(--text-muted); }
.model-fallback-note {
  color: var(--orange);
  font-size: 10px;
  font-weight: 600;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-fallback-note[hidden] { display: none; }
.md-badge {
  color: var(--text-muted);
  font-size: 9px;
  font-weight: 700;
  margin-left: 5px;
}
.md-badge.local { color: var(--accent); }
.md-badge.cloud,
.md-badge.muted { color: var(--text-muted); }

"""

BUILDER_JUDGE_MODEL_PICKER_CSS = """.bj-form-group .model-selector:focus {
  border-color: var(--accent);
  outline: none;
}
.bj-form-row { display: flex; gap: 10px; align-items: flex-end; }
.bj-form-row .bj-form-group { flex: 1; }
.bj-model-picker-wrap { width: 100%; }
.bj-model-selector {
  border-radius: var(--radius-sm);
  justify-content: space-between;
  min-height: 29px;
  padding: 5px 8px;
  width: 100%;
}
.bj-model-dropdown {
  left: 0;
  min-width: min(320px, 90vw);
  right: auto;
  width: 100%;
}
.bj-model-picker-note {
  display: block;
  margin-top: 3px;
  max-width: 100%;
}
"""
