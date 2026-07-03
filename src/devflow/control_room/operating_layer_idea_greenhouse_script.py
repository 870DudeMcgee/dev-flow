from __future__ import annotations


IDEA_GREENHOUSE_JS = """// === IDEA GREENHOUSE ===
function setIdeaGreenhouseStatus(message, tone) {
  const status = $('idea-greenhouse-status');
  if (!status) return;
  status.textContent = message || 'Ready';
  status.className = 'status-pill muted';
  if (tone === 'error') {
    status.style.color = 'var(--red)';
    status.style.borderColor = 'var(--red-soft)';
    status.style.background = 'rgba(248, 81, 73, 0.10)';
  } else if (tone === 'success') {
    status.style.color = 'var(--accent)';
    status.style.borderColor = 'var(--accent-soft)';
    status.style.background = 'var(--accent-bg)';
  } else {
    status.style.color = '';
    status.style.borderColor = '';
    status.style.background = '';
  }
}

function ideaIdFromStdout(stdout) {
  const match = String(stdout || '').match(/\\bI-\\d{4}\\b/);
  return match ? match[0] : null;
}

function ideaCommandHasPlaceholder(command) {
  return /<[^>]+>/.test(String(command || ''));
}

function isBrowserRunnableIdeaAction(action) {
  const command = String(action?.command || '').trim();
  if (!command || ideaCommandHasPlaceholder(command)) return false;
  if (command.startsWith('devflow idea capture ')) return false;
  if (/^devflow idea (park|archive) I-\\d{4} --reason \\S/.test(command)) return true;
  if (/^devflow idea show I-\\d{4}$/.test(command)) return true;
  if (/^devflow idea create-(goal|task) I-\\d{4} --dry-run$/.test(command)) return true;
  return false;
}

function renderIdeaAction(action) {
  const command = String(action?.command || '').trim();
  const label = action?.label || 'Open CLI';
  if (!command) return `<span class="idea-card-command">${esc(label)}</span>`;
  if (isBrowserRunnableIdeaAction(action)) {
    return `<button class="btn btn-sm btn-secondary" type="button" data-command="${esc(command)}">${esc(label)}</button>`;
  }
  return `<code class="idea-card-command">${esc(shortCommand(command, 110))}</code>`;
}

function secondaryIdeaActions(card) {
  const ideaId = String(card?.id || '').trim();
  const lane = String(card?.lane || '').trim();
  if (!/^I-\\d{4}$/.test(ideaId)) return [];
  if (['raw', 'clarify', 'candidate'].includes(lane)) {
    return [
      {
        label: 'Park',
        command: `devflow idea park ${ideaId} --reason ${shellQuote('Parked from Idea Greenhouse.')}`,
      },
    ];
  }
  if (lane === 'parked') {
    return [
      {
        label: 'Archive',
        command: `devflow idea archive ${ideaId} --reason ${shellQuote('Archived from Idea Greenhouse.')}`,
      },
    ];
  }
  return [];
}

function renderIdeaPrimaryAction(action) {
  const container = $('idea-greenhouse-primary-action');
  if (!container) return;
  if (!action?.label && !action?.command) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = `<strong>${esc(action.label || 'Next idea action')}</strong>${renderIdeaAction(action)}`;
}

function renderIdeaCard(card) {
  const action = card?.primary_action || card?.primaryAction || null;
  const tags = Array.isArray(card?.tags) ? card.tags.slice(0, 3) : [];
  const secondaryActions = secondaryIdeaActions(card);
  const tagHtml = tags.length
    ? `<div class="idea-card-meta">${tags.map(tag => `<span class="lane-badge lane-gray">${esc(tag)}</span>`).join(' ')}</div>`
    : '';
  const secondaryHtml = secondaryActions.length
    ? `<div class="idea-card-secondary-actions">${secondaryActions.map(renderIdeaAction).join('')}</div>`
    : '';
  const brainstormBtn = /^I-\\d{4}$/.test(String(card?.id || ''))
    ? `<button class="btn btn-sm btn-secondary" type="button" data-idea-brainstorm="${esc(card.id)}">Continue brainstorm</button>`
    : '';
  const updated = card?.updated_at ? ago(card.updated_at) : '';
  const meta = [card?.status || 'unknown', card?.maturity || 'unknown', updated || 'updated unknown'].filter(Boolean).join(' · ');
  return `<article class="idea-card ${esc(card?.lane || 'raw')}" data-inspect-idea="${esc(card?.id || '')}" tabindex="0" role="button" aria-label="Inspect idea ${esc(card?.id || '')}">
    <header class="idea-card-head">
      <span class="idea-card-id">${esc(card?.id || 'I-????')}</span>
      <strong class="idea-card-title">${esc(card?.title || 'Untitled idea')}</strong>
    </header>
    <p class="idea-card-meta">${esc(meta)}</p>
    ${tagHtml}
    <p class="idea-card-action">${esc(action?.label || 'Inspect idea')}</p>
    ${renderIdeaAction(action)}
    <div class="idea-card-brainstorm-actions">
      ${brainstormBtn}
    </div>
    ${secondaryHtml}
  </article>`;
}

function renderIdeaGreenhouse(greenhouse) {
  const lanesContainer = $('idea-greenhouse-lanes');
  if (!lanesContainer) return;
  if (!greenhouse) {
    renderIdeaPrimaryAction(null);
    lanesContainer.innerHTML = '';
    return;
  }
  renderIdeaPrimaryAction(greenhouse.primary_next_action || null);
  const lanes = Array.isArray(greenhouse.lanes) ? greenhouse.lanes : [];
  lanesContainer.innerHTML = lanes.map(lane => {
    const laneId = lane?.id || 'raw';
    const cards = Array.isArray(lane?.cards) ? lane.cards : [];
    const cardHtml = cards.length
      ? cards.map(renderIdeaCard).join('')
      : '<p class="idea-card-meta" style="padding:8px 10px;">No ideas in this lane.</p>';
    return `<section class="idea-lane ${esc(laneId)}">
      <div class="idea-lane-header">
        <strong>${esc(lane?.label || sentenceCase(laneId))}</strong>
        <output>${esc(lane?.count ?? cards.length)}</output>
      </div>
      ${cardHtml}
    </section>`;
  }).join('');
}

async function captureIdeaFromGreenhouse() {
  const textInput = $('idea-capture-text');
  const titleInput = $('idea-capture-title');
  const submit = $('idea-capture-submit');
  const text = String(textInput?.value || '').trim();
  const title = String(titleInput?.value || '').trim();
  if (!text) {
    setIdeaGreenhouseStatus('Write the idea first.', 'error');
    textInput?.focus();
    return null;
  }
  const command = `devflow idea capture ${shellQuote(text)} --source operating-layer${title ? ` --title ${shellQuote(title)}` : ''} --tag greenhouse`;
  const body = {
    command,
    human_approved: true,
    approval_phrase: ACTION_APPROVAL_PHRASE,
    approved_command: command,
  };
  if (selectedProjectId) body.project = selectedProjectId;
  setIdeaGreenhouseStatus('Capturing...', 'neutral');
  if (submit) submit.disabled = true;
  try {
    const resp = await fetch('/api/actions/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const payload = await resp.json();
    const ok = resp.ok && payload?.executed && payload?.exit_code === 0;
    if (!ok) {
      const message = payload?.message || payload?.error || payload?.stderr || `Capture failed (${resp.status})`;
      setIdeaGreenhouseStatus(shortCommand(message, 80), 'error');
      return payload;
    }
    const ideaId = ideaIdFromStdout(payload.stdout);
    if (textInput) textInput.value = '';
    if (titleInput) titleInput.value = '';
    setIdeaGreenhouseStatus(ideaId ? `Captured ${ideaId}` : 'Captured idea.', 'success');
    await loadSnapshot(selectedProjectId);
    return payload;
  } catch(e) {
    setIdeaGreenhouseStatus(shortCommand(e.message || 'Capture failed', 80), 'error');
    return null;
  } finally {
    if (submit) submit.disabled = false;
  }
}

function setupIdeaGreenhouse() {
  const form = $('idea-capture-form');
  if (!form) return;
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    captureIdeaFromGreenhouse();
  });
}

function ideaCardsFromSnapshot() {
  const lanes = snapshot?.idea_greenhouse?.lanes || [];
  return lanes.flatMap(lane => Array.isArray(lane?.cards) ? lane.cards : []);
}

function findIdeaCard(ideaId) {
  return ideaCardsFromSnapshot().find(card => card?.id === ideaId) || null;
}

function ideaDetailMetadataRows(metadata) {
  const entries = Object.entries(metadata || {}).filter(([, value]) => value !== null && value !== undefined && value !== '');
  if (!entries.length) return '<p class="idea-detail-muted">No metadata available.</p>';
  return `<dl class="idea-detail-metadata-list">${entries.map(([key, value]) => {
    const shown = Array.isArray(value) || typeof value === 'object'
      ? JSON.stringify(value)
      : String(value);
    return `<div><dt>${esc(key)}</dt><dd>${esc(shortCommand(shown, 180))}</dd></div>`;
  }).join('')}</dl>`;
}

function renderIdeaClassifyForm(card) {
  const ideaId = String(card?.id || '').trim();
  if (!/^I-[0-9]{4}$/.test(ideaId)) return '';
  return `<div class="focus-section idea-detail-classify-section"><h3 class="idea-classify-title">Classify this idea</h3>
    <div id="idea-classify-status" class="idea-detail-status idea-detail-status-neutral" aria-live="polite"></div>
    <div class="idea-classify-row">
      <label for="idea-classify-maturity-${ideaId}">Maturity</label>
      <select class="idea-classify-select" data-idea-classify="maturity" id="idea-classify-maturity-${ideaId}">
        <option value="">Choose maturity...</option>
        <option value="spark">Spark — vague or unresolved</option>
        <option value="concept">Concept — defined direction</option>
        <option value="candidate">Candidate — concrete, actionable</option>
        <option value="goal_ready">Goal Ready — scoped for a goal</option>
        <option value="task_ready">Task Ready — ready to create task</option>
      </select>
    </div>
    <label for="idea-classify-note-${ideaId}">Classification note (required)</label>
    <textarea class="idea-classify-note" data-idea-classify="note" id="idea-classify-note-${ideaId}" placeholder="Why this maturity? What did you observe?" rows="3"></textarea>
    <button class="btn btn-primary" type="button" data-idea-classify-submit="${ideaId}">Apply classification</button>
  </div>`;
}

function renderIdeaParkArchiveForm(card) {
  const ideaId = String(card?.id || '').trim();
  if (!/^I-[0-9]{4}$/.test(ideaId)) return '';
  const lane = String(card?.lane || '').trim();
  const isParkable = ['raw', 'clarify', 'candidate'].includes(lane);
  const isArchivable = lane === 'parked';
  if (!isParkable && !isArchivable) return '';
  const actionVerb = isParkable ? 'Park' : 'Archive';
  return `<div class="focus-section idea-detail-${isParkable ? 'park' : 'archive'}-section"><h3 class="idea-archive-title">${actionVerb} this idea</h3>
    <div id="idea-${isParkable ? 'park' : 'archive'}-status" class="idea-detail-status idea-detail-status-neutral" aria-live="polite"></div>
    <label for="idea-${isParkable ? 'park' : 'archive'}-reason-${ideaId}">Reason (required, at least 3 characters)</label>
    <textarea class="idea-archive-reason" data-idea-${isParkable ? 'park' : 'archive'}="reason" id="idea-${isParkable ? 'park' : 'archive'}-reason-${ideaId}" placeholder="Why are you ${isParkable ? 'parking' : 'archiving'} this idea?" rows="3"></textarea>
    <button class="btn btn-primary" type="button" data-idea-${isParkable ? 'park' : 'archive'}-submit="${ideaId}">${actionVerb}</button>
  </div>`;
}

function renderIdeaDetail(card) {
  const action = card?.primary_action || card?.primaryAction || null;
  const tags = Array.isArray(card?.tags) ? card.tags : [];
  const evidencePaths = Array.isArray(card?.evidence_paths) ? card.evidence_paths : [];
  const metadata = card?.metadata || {};
  const actionCommand = String(action?.command || '').trim();
  const updated = card?.updated_at ? ago(card.updated_at) : '';
  const lane = card?.lane || 'raw';
  // Only show classify form on Raw and Clarify lanes
  const classifyFormHtml = (lane === 'raw' || lane === 'clarify') ? renderIdeaClassifyForm(card) : '';
  return `<div class="focus-task-head idea-detail-head">
      <span class="focus-task-id">${esc(card?.id || 'I-????')}</span>
      <h2>${esc(card?.title || 'Untitled idea')}</h2>
      <span class="focus-status lane-${esc(card?.lane || 'gray')}">${esc(sentenceCase(card?.lane || 'idea'))}</span>
    </div>
    <div class="focus-grid idea-detail-grid">
      <div><span>Lane</span><strong>${esc(card?.lane || 'raw')}</strong></div>
      <div><span>Status</span><strong>${esc(card?.status || 'unknown')}</strong></div>
      <div><span>Maturity</span><strong>${esc(card?.maturity || 'unknown')}</strong></div>
      <div><span>Source</span><strong>${esc(card?.source || 'unknown')}</strong></div>
      <div><span>Updated</span><strong>${esc(updated || card?.updated_at || 'unknown')}</strong></div>
      <div><span>Tags</span><strong>${tags.length ? tags.map(esc).join(', ') : '—'}</strong></div>
    </div>
    ${classifyFormHtml}
    ${renderIdeaParkArchiveForm(card)}
    <div class="task-command-box idea-detail-next-action">
      <label>Current next action</label>
      <strong>${esc(action?.label || 'Inspect idea')}</strong>
      ${actionCommand ? `<code>${esc(actionCommand)}</code>` : '<p>No command attached.</p>'}
    </div>
    <div class="focus-section idea-detail-evidence"><h3>Evidence paths</h3>
      ${evidencePaths.length ? evidencePaths.map(path => `<code class="path-line">${esc(path)}</code>`).join('') : '<p class="idea-detail-muted">No evidence paths recorded.</p>'}
    </div>
    <div class="focus-section idea-detail-metadata"><h3>Raw metadata</h3>
      ${ideaDetailMetadataRows(metadata)}
      <pre>${esc(JSON.stringify(metadata, null, 2))}</pre>
    </div>
    <div class="task-command-box idea-detail-brainstorm">
      <label>Bridge to Brainstorm</label>
      <p>Seed a brainstorm session from this idea while preserving source lineage.</p>
      <div id="idea-brainstorm-status" class="idea-detail-status idea-detail-status-neutral" aria-live="polite"></div>
      <button class="btn btn-primary" type="button" data-idea-brainstorm="${esc(card?.id || '')}">Start brainstorm from idea</button>
    </div>`;
}

async function classifyIdeaFromDetail(card) {
  const ideaId = String(card?.id || '').trim();
  if (!/^I-[0-9]{4}$/.test(ideaId)) return null;
  const cardEl = document.querySelector(`[data-idea-classify-submit="${esc(ideaId)}"]`)?.closest('.focus-section.idea-detail-classify-section');

  const maturitySelect = cardEl?.querySelector('[data-idea-classify="maturity"]')
    || document.querySelector('[data-idea-classify="maturity"]');
  const noteInput = cardEl?.querySelector('[data-idea-classify="note"]')
    || document.querySelector('[data-idea-classify="note"]');

  const maturityValue = (maturitySelect?.value || '').trim();
  const noteValue = (noteInput?.value || '').trim();
  const allowedMaturities = new Set(['spark', 'concept', 'candidate', 'goal_ready', 'task_ready']);

  maturitySelect?.classList.remove('idea-classify-select-error');
  noteInput?.classList.remove('idea-classify-note-error');

  if (!allowedMaturities.has(maturityValue)) {
    setIdeaDetailStatus('Choose a maturity before classifying.', 'error');
    maturitySelect?.classList.add('idea-classify-select-error');
    maturitySelect?.focus();
    return null;
  }

  if (!noteValue) {
    setIdeaDetailStatus('Please write a classification note.', 'error');
    noteInput?.classList.add('idea-classify-note-error');
    noteInput?.focus();
    return null;
  }

  const command = `devflow idea classify ${ideaId} --maturity ${maturityValue} --note ${shellQuote(noteValue)}`;

  // Guard: no placeholder commands
  if (command.includes('<') || command.includes('>') || !/^devflow idea classify I-[0-9]{4} --maturity /.test(command)) {
    setIdeaDetailStatus('This action requires a concrete command first.', 'error');
    return null;
  }

  renderActionPending(command);
  const body = {
    command,
    human_approved: true,
    approval_phrase: ACTION_APPROVAL_PHRASE,
    approved_command: command,
  };
  if (selectedProjectId) body.project = selectedProjectId;

  setIdeaDetailStatus('Classifying...', 'neutral');
  try {
    const resp = await fetch('/api/actions/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const payload = await resp.json();
    renderActionResult(payload, command);

    if (resp.ok && payload?.executed && payload?.exit_code === 0) {
      setIdeaDetailStatus('Idea classified successfully.', 'success');
      // Refresh snapshot so the idea moves lanes
      setTimeout(() => loadSnapshot(selectedProjectId), 500);
      return payload;
    } else {
      const message = payload?.message || payload?.error || `Classification failed (${resp.status})`;
      setIdeaDetailStatus(shortCommand(message, 80), 'error');
      return null;
    }
  } catch(e) {
    setIdeaDetailStatus(shortCommand(e.message || 'Classification failed', 80), 'error');
    return null;
  }
}


async function _submitParkOrArchive(card, actionType) {
  const ideaId = String(card?.id || '').trim();
  if (!/^I-[0-9]{4}$/.test(ideaId)) return null;
  const selAttr = `data-idea-${actionType}="reason"`;
  const textarea = document.querySelector(`textarea[${selAttr}]`);
  const reasonValue = (textarea?.value || '').trim();

  if (!reasonValue || reasonValue.length < 3) {
    setIdeaDetailStatus('Reason is required (at least 3 characters).', 'error', `idea-${actionType}-status`);
    textarea?.focus();
    return null;
  }

  const verb = actionType === 'park' ? 'Park' : 'Archive';
  const command = `devflow idea ${actionType} ${ideaId} --reason ${shellQuote(reasonValue)}`;

  if (command.includes('<') || command.includes('>') || !/^devflow idea (park|archive) I-[0-9]{4} --reason /.test(command)) {
    setIdeaDetailStatus('This action requires a concrete reason first.', 'error', `idea-${actionType}-status`);
    return null;
  }

  renderActionPending(command);
  const body = {
    command,
    human_approved: true,
    approval_phrase: ACTION_APPROVAL_PHRASE,
    approved_command: command,
  };
  if (selectedProjectId) body.project = selectedProjectId;

  setIdeaDetailStatus(`${verb}ing...`, 'neutral', `idea-${actionType}-status`);
  try {
    const resp = await fetch('/api/actions/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const payload = await resp.json();
    renderActionResult(payload, command);

    if (resp.ok && payload?.executed && payload?.exit_code === 0) {
      setIdeaDetailStatus(`${ideaId} ${verb.toLowerCase()}d successfully.`, 'success', `idea-${actionType}-status`);
      // Refresh snapshot so the idea moves lanes
      setTimeout(() => loadSnapshot(selectedProjectId), 500);
      return payload;
    } else {
      const message = payload?.message || payload?.error || `${verb} failed (${resp.status})`;
      setIdeaDetailStatus(shortCommand(message, 80), 'error', `idea-${actionType}-status`);
      return null;
    }
  } catch(e) {
    setIdeaDetailStatus(shortCommand(e.message || `${verb} failed`, 80), 'error', `idea-${actionType}-status`);
    return null;
  }
}

function setIdeaDetailStatus(message, tone, statusId) {
  const statusEl = statusId ? $(statusId) : $('idea-classify-status');
  if (!statusEl) return;
  statusEl.textContent = message || '';
  if (tone === 'error') {
    statusEl.style.color = 'var(--red)';
    statusEl.style.borderColor = 'var(--red-soft)';
    statusEl.style.background = 'rgba(248, 81, 73, 0.10)';
    statusEl.className = 'idea-detail-status idea-detail-status-error';
  } else if (tone === 'success') {
    statusEl.style.color = 'var(--accent)';
    statusEl.style.borderColor = 'var(--accent-soft)';
    statusEl.style.background = 'var(--accent-bg)';
    statusEl.className = 'idea-detail-status idea-detail-status-success';
  } else {
    statusEl.style.color = '';
    statusEl.style.borderColor = '';
    statusEl.style.background = '';
    statusEl.className = 'idea-detail-status idea-detail-status-neutral';
  }
}

async function handleIdeaGreenhouseClick(e) {
  const ideaCard = e.target.closest('[data-inspect-idea]');
  if (ideaCard && !e.target.closest('button,a,input,textarea,select,[data-command]')) {
    e.preventDefault();
    e.stopPropagation();
    const id = ideaCard.dataset.inspectIdea;
    if (id) openFocus('idea', id, {});
    return true;
  }

  const classifyButton = e.target.closest('[data-idea-classify-submit]');
  if (classifyButton) {
    e.preventDefault();
    const ideaId = classifyButton.dataset.ideaClassifySubmit;
    const idea = findIdeaCard(ideaId);
    if (!idea) {
      setIdeaDetailStatus('Idea not found in current snapshot.', 'error');
      return true;
    }
    try {
      await classifyIdeaFromDetail(idea);
    } catch(err) {
      setIdeaDetailStatus(shortCommand(err.message || 'Classification failed', 80), 'error');
    }
    return true;
  }

  const parkButton = e.target.closest('[data-idea-park-submit]');
  if (parkButton) {
    e.preventDefault();
    const ideaId = parkButton.dataset.ideaParkSubmit;
    const idea = findIdeaCard(ideaId);
    if (!idea) {
      setIdeaDetailStatus('Idea not found in current snapshot.', 'error');
      return true;
    }
    try {
      await _submitParkOrArchive(idea, 'park');
    } catch(err) {
      setIdeaDetailStatus(shortCommand(err.message || 'Park failed', 80), 'error');
    }
    return true;
  }

  const archiveButton = e.target.closest('[data-idea-archive-submit]');
  if (archiveButton) {
    e.preventDefault();
    const ideaId = archiveButton.dataset.ideaArchiveSubmit;
    const idea = findIdeaCard(ideaId);
    if (!idea) {
      setIdeaDetailStatus('Idea not found in current snapshot.', 'error');
      return true;
    }
    try {
      await _submitParkOrArchive(idea, 'archive');
    } catch(err) {
      setIdeaDetailStatus(shortCommand(err.message || 'Archive failed', 80), 'error');
    }
    return true;
  }

  const brainstormButton = e.target.closest('[data-idea-brainstorm]');
  if (brainstormButton) {
    e.preventDefault();
    const ideaId = brainstormButton.dataset.ideaBrainstorm;
    if (!/^I-[0-9]{4}$/.test(ideaId)) return true;
    const statusId = 'idea-brainstorm-status';
    setIdeaDetailStatus('Starting brainstorm from ' + ideaId + '...', 'neutral', statusId);
    try {
      const resp = await fetch('/api/brainstorm/start-from-idea', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea_id: ideaId }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.session_id) {
        setIdeaDetailStatus(data.error || 'Failed to start brainstorm.', 'error', statusId);
        return true;
      }
      setActiveBrainstormSession(data.session_id, { userSelected: true });
      setIdeaDetailStatus('Session: ' + data.session_id, 'success', statusId);
      setActiveNav('brainstorm');
      closeFocus();
      await loadBrainstormTranscript(data.session_id);
      appendBrainstormMsg('system', 'Brainstorm session started from ' + ideaId + '. Next: add context or escalate to Spec when the idea is clear.', {});
      await loadBrainstormSessions();
      await refreshPipelineState();
      const input = $('brainstorm-message');
      if (input) input.focus();
    } catch(e) {
      setIdeaDetailStatus(e.message || 'Failed to start brainstorm.', 'error', statusId);
    }
    return true;
  }

  return false;
}

function handleIdeaGreenhouseKeydown(e) {
  const ideaCard = e.target.closest?.('[data-inspect-idea]');
  if (!ideaCard || !['Enter', ' '].includes(e.key)) return false;
  e.preventDefault();
  const id = ideaCard.dataset.inspectIdea;
  if (id) openFocus('idea', id, {});
  return true;
}
"""
