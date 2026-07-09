from __future__ import annotations


IDEA_GREENHOUSE_CSS = """/* ===== IDEA GREENHOUSE ===== */
.idea-greenhouse-section {
  min-width: 0;
}
.idea-capture-form {
  border-top: 1px solid var(--border-light);
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 8px 12px 8px;
}
.idea-capture-form textarea,
.idea-capture-form input {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text);
  font: inherit;
  font-size: 12px;
  min-width: 0;
  outline: none;
  padding: 8px 10px;
  transition: border-color 0.12s;
  width: 100%;
}
.idea-capture-form textarea {
  height: 38px;
  line-height: 1.45;
  max-height: 160px;
  min-height: 38px;
  resize: vertical;
}
.idea-capture-form input {
  flex: 1 1 200px;
  min-height: 30px;
}
.idea-capture-form textarea:focus,
.idea-capture-form input:focus {
  border-color: var(--accent);
}
.idea-capture-form textarea::placeholder,
.idea-capture-form input::placeholder {
  color: var(--text-muted);
}
.idea-capture-form .composer-row {
  align-items: stretch;
  flex-wrap: wrap;
  margin-top: 0;
}
.idea-capture-form .btn {
  flex: 0 0 auto;
  justify-content: center;
  white-space: nowrap;
}
.idea-primary-action:empty,
.idea-greenhouse-lanes:empty {
  display: none;
}
.idea-primary-action:not(:empty) {
  background: linear-gradient(90deg, var(--blue-soft), transparent 70%), var(--bg);
  border: 1px solid rgba(88, 166, 255, 0.22);
  border-left: 3px solid var(--blue);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  display: flex;
  flex-direction: column;
  font-size: 12px;
  gap: 5px;
  margin: 0 14px 8px;
  min-width: 0;
  padding: 7px 10px;
}
.idea-primary-action strong {
  color: var(--text);
  font-size: 12px;
}
.idea-primary-action code {
  background: #070a0f;
  border: 1px solid var(--border-light);
  border-radius: 5px;
  color: var(--text-soft);
  display: block;
  font-size: 11px;
  overflow: hidden;
  padding: 5px 7px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.idea-greenhouse-lanes {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  max-width: 100%;
  min-width: 0;
  padding: 6px 10px 8px;
}
.idea-greenhouse-lanes:has(.idea-card) {
  max-height: 180px;
  overflow: hidden;
}
.idea-lane {
  --idea-accent: var(--border);
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-top: 2px solid var(--idea-accent);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.idea-lane .idea-card {
  flex-shrink: 0;
}
.idea-lane-header {
  align-items: center;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  gap: 6px;
  justify-content: space-between;
  min-width: 0;
  padding: 4px 8px;
}
.idea-lane-header strong {
  color: var(--text);
  font-size: 11px;
  font-weight: 700;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.idea-lane-header span,
.idea-lane-header output {
  color: var(--text-muted);
  flex-shrink: 0;
  font-size: 9px;
}
.idea-lane.raw,
.idea-card.raw {
  --idea-accent: var(--text-muted);
  --idea-tint: rgba(110, 118, 129, 0.035);
}
.idea-lane.clarify,
.idea-card.clarify {
  --idea-accent: var(--purple);
  --idea-tint: rgba(188, 140, 255, 0.055);
}
.idea-lane.candidate,
.idea-card.candidate {
  --idea-accent: var(--blue);
  --idea-tint: var(--blue-soft);
}
.idea-lane.promoted,
.idea-card.promoted {
  --idea-accent: var(--accent);
  --idea-tint: var(--accent-bg);
}
.idea-lane.parked,
.idea-card.parked {
  --idea-accent: var(--text-muted);
  --idea-tint: rgba(110, 118, 129, 0.06);
}
.idea-lane.archived,
.idea-card.archived {
  --idea-accent: var(--text-muted);
  --idea-tint: transparent;
  opacity: 0.72;
}
.idea-card {
  --idea-accent: var(--border);
  --idea-tint: transparent;
  background: linear-gradient(90deg, var(--idea-tint), transparent 68%), var(--bg);
  border: 1px solid var(--border-light);
  border-left: 3px solid var(--idea-accent);
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin: 4px 6px;
  min-width: 0;
  padding: 5px 7px 6px 8px;
}
.idea-card:hover {
  background: var(--panel-hover);
  border-color: var(--border);
}
.idea-card header,
.idea-card-head,
.idea-card-title-row {
  align-items: baseline;
  display: flex;
  gap: 6px;
  min-width: 0;
}
.idea-card strong,
.idea-card-title {
  color: var(--text);
  font-size: 11px;
  font-weight: 700;
  min-width: 0;
  overflow: hidden;
  overflow-wrap: anywhere;
  text-overflow: ellipsis;
  white-space: normal;
}
.idea-card-id {
  color: var(--blue);
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 800;
}
.idea-card-meta,
.idea-card-action,
.idea-card-command,
.idea-card p {
  color: var(--text-muted);
  font-size: 9px;
  line-height: 1.3;
  margin: 0;
  min-width: 0;
  overflow: hidden;
  overflow-wrap: anywhere;
  text-overflow: ellipsis;
  white-space: normal;
}
.idea-card-action {
  color: var(--text-soft);
  font-size: 10px;
  font-weight: 600;
}
.idea-card-meta,
.idea-card-action {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
.idea-card code,
.idea-card-command {
  background: #070a0f;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  color: var(--text-soft);
  display: block;
  font-size: 10px;
  padding: 3px 5px;
  white-space: nowrap;
}
.idea-card .btn {
  align-self: flex-start;
  margin-top: 2px;
}
.idea-card-secondary-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}
.idea-card[role="button"] {
  cursor: pointer;
}
.idea-card[role="button"]:focus-visible {
  border-color: var(--blue);
  box-shadow: 0 0 0 2px rgba(88, 166, 255, 0.22);
  outline: none;
}
.idea-detail-head .lane-raw,
.idea-detail-head .lane-parked,
.idea-detail-head .lane-archived {
  background: rgba(110, 118, 129, 0.12);
  color: var(--text-soft);
}
.idea-detail-head .lane-clarify {
  background: rgba(188, 140, 255, 0.14);
  color: var(--purple);
}
.idea-detail-head .lane-candidate {
  background: var(--blue-soft);
  color: var(--blue);
}
.idea-detail-head .lane-promoted {
  background: var(--accent-bg);
  color: var(--accent);
}
.idea-detail-grid strong {
  overflow-wrap: anywhere;
}
.idea-detail-next-action {
  border-left-color: var(--blue);
}
.idea-detail-evidence .path-line {
  display: block;
  margin: 5px 0;
}
.idea-detail-metadata pre {
  background: #070a0f;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  color: var(--text-soft);
  font-size: 11px;
  line-height: 1.45;
  margin: 8px 0 0;
  max-height: 240px;
  overflow: auto;
  padding: 10px;
  white-space: pre-wrap;
}
.idea-detail-metadata-list {
  display: grid;
  gap: 6px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 0;
}
.idea-detail-metadata-list div {
  background: var(--bg);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  min-width: 0;
  padding: 7px 8px;
}
.idea-detail-metadata-list dt {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 700;
  margin-bottom: 3px;
  text-transform: uppercase;
}
.idea-detail-metadata-list dd {
  color: var(--text-soft);
  font-size: 11px;
  margin: 0;
  overflow-wrap: anywhere;
}
.idea-detail-muted {
  color: var(--text-muted);
  font-size: 12px;
  margin: 0;
}
@media (max-width: 900px) {
  .idea-capture-form { padding: 8px 10px 10px; }
  .idea-capture-form textarea { min-height: 44px; }
  .idea-capture-form input { flex: 1 1 150px; }
  .idea-capture-form .btn { flex: 0 0 auto; }
  .idea-primary-action:not(:empty) { margin: 0 12px 10px; }
  .idea-greenhouse-lanes { grid-template-columns: repeat(3, minmax(0, 1fr)); padding: 6px 8px 8px; }
  .idea-greenhouse-lanes:has(.idea-card) { max-height: 104px; }
  .idea-lane > .idea-card-meta { display: none; }
}
/* ===== CLASSIFY FORM (Slice 2) ===== */
.idea-detail-classify-section { background: var(--bg-3); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px 14px; margin-top: 8px; }
.idea-classify-title { font-size: 13px; font-weight: 600; color: var(--text); margin: 0 0 8px; }
.idea-classify-row { display: flex; gap: 8px; align-items: stretch; margin-bottom: 8px; }
.idea-classify-select { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px 8px; color: var(--text); font-size: 12px; font-family: inherit; cursor: pointer; flex: none; width: 150px; }
.idea-classify-select:focus { border-color: var(--accent); outline: none; }
.idea-classify-note { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px 8px; color: var(--text); font-size: 12px; font-family: inherit; flex: 1; resize: vertical; min-height: 32px; }
.idea-classify-note:focus { border-color: var(--accent); outline: none; }
.idea-classify-error { color: var(--red); font-size: 11px; margin-top: 4px; margin-bottom: 4px; }
.idea-classify-note-error, .idea-classify-select-error { border-color: var(--red) !important; }

/* ===== PARK/ARCHIVE FORM (Slice 3) ===== */
.idea-detail-park-section,
.idea-detail-archive-section { background: var(--bg-3); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px 14px; margin-top: 8px; }
.idea-archive-title { font-size: 13px; font-weight: 600; color: var(--text); margin: 0 0 8px; }
.idea-archive-reason { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px 8px; color: var(--text); font-size: 12px; font-family: inherit; flex: 1; resize: vertical; min-height: 32px; width: 100%; }
.idea-archive-reason:focus { border-color: var(--accent); outline: none; }
.idea-archive-reason::placeholder { color: var(--text-muted); }"""
