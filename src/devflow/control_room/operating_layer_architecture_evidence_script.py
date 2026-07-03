from __future__ import annotations


ARCHITECTURE_EVIDENCE_JS = """// === ARCHITECTURE EVIDENCE ===
function architectureMetricValue(value) {
  if (value === null || value === undefined || value === '') return 'unknown';
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : String(value);
}

function architectureStatusMeta(evidence) {
  const freshness = evidence?.freshness?.status || evidence?.status || 'missing';
  if (freshness === 'fresh') return { label: 'Fresh', cls: 'online' };
  if (freshness === 'stale') return { label: 'Stale', cls: 'warn' };
  if (freshness === 'missing') return { label: 'Missing', cls: 'bad' };
  if (freshness === 'unknown') return { label: 'Unknown', cls: 'idle' };
  if (evidence?.status === 'available') return { label: 'Available', cls: 'online' };
  return { label: sentenceCase(freshness), cls: 'idle' };
}

function inlineCommandFromAction(text) {
  const match = String(text || '').match(/`([^`]+)`/);
  return match ? match[1] : '';
}

function architectureArtifactUrl(artifact) {
  let url = artifact?.view_url || (artifact?.artifact_id ? `/architecture/artifact?id=${encodeURIComponent(artifact.artifact_id)}` : '');
  if (url && selectedProjectId) {
    url += (url.includes('?') ? '&' : '?') + 'project=' + encodeURIComponent(selectedProjectId);
  }
  return url;
}

function findArchitectureArtifact(artifacts, predicate) {
  return (Array.isArray(artifacts) ? artifacts : []).find(predicate) || null;
}

function closeArchitectureViewer() {
  const overlay = $('architecture-viewer-overlay');
  const frame = $('architecture-viewer-frame');
  const report = $('architecture-viewer-report');
  if (frame) { frame.src = 'about:blank'; frame.hidden = true; }
  if (report) { report.textContent = ''; report.hidden = true; }
  if (overlay) overlay.hidden = true;
}

async function openArchitectureReport(artifact) {
  const overlay = $('architecture-viewer-overlay');
  const frame = $('architecture-viewer-frame');
  const report = $('architecture-viewer-report');
  const title = $('architecture-viewer-title');
  if (!overlay || !report) return;
  if (title) title.textContent = artifact?.label || 'Graph report';
  if (frame) { frame.src = 'about:blank'; frame.hidden = true; }
  report.hidden = false;
  report.textContent = 'Loading report…';
  overlay.hidden = false;
  try {
    const resp = await fetch(architectureArtifactUrl(artifact));
    if (!resp.ok) throw new Error(`Report unavailable (${resp.status})`);
    const text = await resp.text();
    // Rendered as escaped text content (textContent), never innerHTML.
    report.textContent = text;
  } catch (e) {
    report.textContent = `Could not load report: ${e.message || 'unknown error'}`;
  }
}

function openArchitectureSandboxedHtml(artifact) {
  const overlay = $('architecture-viewer-overlay');
  const frame = $('architecture-viewer-frame');
  const report = $('architecture-viewer-report');
  const title = $('architecture-viewer-title');
  if (!overlay || !frame) return;
  if (title) title.textContent = artifact?.label || 'Architecture artifact';
  if (report) { report.textContent = ''; report.hidden = true; }
  // sandbox="allow-scripts" only — no same-origin, forms, popups, or top navigation.
  frame.setAttribute('sandbox', 'allow-scripts');
  frame.hidden = false;
  frame.src = architectureArtifactUrl(artifact);
  overlay.hidden = false;
}

function setupArchitectureViewer() {
  const overlay = $('architecture-viewer-overlay');
  const close = $('architecture-viewer-close');
  if (close) close.addEventListener('click', closeArchitectureViewer);
  if (overlay) {
    overlay.addEventListener('click', (e) => { if (e.target === overlay) closeArchitectureViewer(); });
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && overlay && !overlay.hidden) closeArchitectureViewer();
  });
}

function renderArchitectureEvidence(evidence) {
  const section = $('architecture-evidence-section');
  const target = $('architecture-evidence-content');
  const badge = $('architecture-evidence-status');
  if (!section || !target) return;
  const data = evidence || {};
  const status = architectureStatusMeta(data);
  if (badge) {
    badge.textContent = status.label;
    badge.className = 'status-badge ' + status.cls;
  }
  section.classList.toggle('is-empty', (data.status || 'missing') === 'missing');
  section.classList.toggle('is-stale', data?.freshness?.status === 'stale');

  const metrics = data.metrics || {};
  const freshness = data.freshness || {};
  const diagnostic = data.diagnostic || {};
  const artifacts = Array.isArray(data.artifacts) ? data.artifacts : [];
  const hotspots = Array.isArray(data.hotspots) ? data.hotspots : [];
  const questions = Array.isArray(data.suggested_questions) ? data.suggested_questions : [];
  const nextAction = data.next_safe_action || '';
  const nextCommand = inlineCommandFromAction(nextAction);
  const diagnosticWarnings = Array.isArray(diagnostic?.raw?.warnings) ? diagnostic.raw.warnings : [];
  const refreshAction = data.refresh_action || null;
  const artifactCount = Number.isFinite(Number(data.artifact_count)) ? Number(data.artifact_count) : artifacts.length;

  const reportArtifact = findArchitectureArtifact(artifacts, a => a.viewer === 'markdown' || a.kind === 'report');
  const graphArtifact = findArchitectureArtifact(artifacts, a => a.artifact_id === 'graph-tree' || a.kind === 'graph_json');
  const callflowArtifact = findArchitectureArtifact(artifacts, a => String(a.artifact_id || '').startsWith('callflow'));

  const metricRows = [
    ['Nodes', metrics.nodes],
    ['Edges', metrics.edges],
    ['Communities', metrics.communities],
    ['Extracted', metrics.extracted_edge_percent === null || metrics.extracted_edge_percent === undefined ? null : `${metrics.extracted_edge_percent}%`],
  ];

  const provenanceRows = [
    ['Built commit', freshness.built_commit || 'unknown'],
    ['Current HEAD', freshness.head_commit || 'unknown'],
    ['Report date', freshness.report_date || 'unknown'],
    ['Generated', freshness.generated_at ? shortTime(freshness.generated_at) : 'unknown'],
    ['Artifacts', String(artifactCount)],
  ];

  const actionButtons = [];
  if (reportArtifact) {
    actionButtons.push(`<button class="btn btn-sm btn-secondary" type="button" data-arch-view="report" data-arch-id="${esc(reportArtifact.artifact_id)}">View report</button>`);
  }
  if (graphArtifact) {
    actionButtons.push(`<button class="btn btn-sm btn-secondary" type="button" data-arch-view="graph" data-arch-id="${esc(graphArtifact.artifact_id)}">View graph</button>`);
  }
  if (callflowArtifact) {
    actionButtons.push(`<button class="btn btn-sm btn-secondary" type="button" data-arch-view="callflow" data-arch-id="${esc(callflowArtifact.artifact_id)}">View callflow</button>`);
  }
  if (refreshAction?.command) {
    actionButtons.push(`<button class="btn btn-sm btn-caution" type="button" data-arch-refresh="${esc(refreshAction.command)}" title="Approval-required: installs graphifyy if needed and rewrites the checkpoint doc.">${esc(refreshAction.label || 'Refresh evidence')}</button>`);
  }
  const actionHtml = actionButtons.length
    ? actionButtons.join('')
    : '<span class="architecture-empty">No Graphify artifacts found yet. Refresh evidence to generate them.</span>';

  const hotspotHtml = hotspots.length
    ? hotspots.map(item => `<li><strong>${esc(item.label)}</strong><span>${esc(item.detail || '')}</span></li>`).join('')
    : '<li><span>No graph hotspots found in the report.</span></li>';
  const questionHtml = questions.length
    ? questions.map(item => `<li><strong>${esc(item.question)}</strong>${item.reason ? `<span>${esc(item.reason)}</span>` : ''}</li>`).join('')
    : '<li><span>No suggested questions found in the report.</span></li>';
  const diagnosticHtml = diagnosticWarnings.length
    ? diagnosticWarnings.map(item => `<span class="architecture-diagnostic-chip">${esc(item)}</span>`).join('')
    : `<span class="architecture-diagnostic-chip">${esc(sentenceCase(diagnostic.status || 'not_run'))}</span>`;

  target.innerHTML = `<div class="architecture-summary-row">
    <div class="architecture-summary-main">
      <span class="architecture-source-chip">Source: ${esc(data.source_path || 'graphify-out/GRAPH_REPORT.md')}</span>
      <strong>${esc(data.summary || 'Graphify report missing')}</strong>
      <span>${esc(freshness.detail || 'Freshness unknown.')}</span>
    </div>
    <div class="architecture-next-action">
      <span>Next safe action</span>
      <code>${esc(nextAction || 'No architecture action queued.')}</code>
      ${nextCommand ? `<button class="btn btn-sm btn-readonly" type="button" data-copy-command="${esc(nextCommand)}" data-copy-kind="terminal_command" aria-label="Copy architecture evidence command">Copy</button>` : ''}
    </div>
  </div>
  <div class="architecture-metric-grid">
    ${metricRows.map(([label, value]) => `<div class="architecture-metric"><span>${esc(label)}</span><strong>${esc(architectureMetricValue(value))}</strong></div>`).join('')}
    <div class="architecture-metric architecture-freshness"><span>Freshness</span><strong>${esc(status.label)}</strong></div>
    <div class="architecture-metric architecture-diagnostics"><span>Diagnostics</span><strong>${esc(sentenceCase(diagnostic.status || 'not_run'))}</strong></div>
  </div>
  <div class="architecture-provenance-grid">
    ${provenanceRows.map(([label, value]) => `<div class="architecture-provenance"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('')}
  </div>
  <div class="architecture-action-row" role="group" aria-label="Architecture evidence actions">${actionHtml}</div>
  <div class="architecture-evidence-grid">
    <section class="architecture-evidence-block" aria-label="Graphify hotspots">
      <h4>Hotspots</h4>
      <ul>${hotspotHtml}</ul>
    </section>
    <section class="architecture-evidence-block" aria-label="Graphify diagnostic notes">
      <h4>Diagnostics</h4>
      <div class="architecture-diagnostic-list">${diagnosticHtml}</div>
    </section>
    <section class="architecture-evidence-block architecture-question-block" aria-label="Graphify suggested questions">
      <h4>Suggested Questions</h4>
      <ul>${questionHtml}</ul>
    </section>
  </div>`;

  target.querySelectorAll('[data-arch-view]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const kind = btn.dataset.archView;
      const artifactId = btn.dataset.archId;
      const artifact = findArchitectureArtifact(artifacts, a => a.artifact_id === artifactId);
      if (!artifact) return;
      if (kind === 'report') {
        openArchitectureReport(artifact);
      } else {
        openArchitectureSandboxedHtml(artifact);
      }
    });
  });
  target.querySelectorAll('[data-arch-refresh]').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const command = btn.dataset.archRefresh || '';
      if (!command) return;
      btn.disabled = true;
      try {
        await runApprovedCommand(command, {});
        await loadSnapshot(selectedProjectId);
      } catch (err) {
        if (!err?.actionRendered) renderActionError({ message: err.message || 'Refresh failed', command });
      } finally {
        btn.disabled = false;
      }
    });
  });
}

"""
