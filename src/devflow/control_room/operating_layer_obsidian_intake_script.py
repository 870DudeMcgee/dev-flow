from __future__ import annotations


OBSIDIAN_INTAKE_JS = """// === OBSIDIAN INTAKE ===
function obsidianCards() {
  return Array.isArray(obsidianIntake?.payload?.cards) ? obsidianIntake.payload.cards : [];
}

function selectedObsidianCard() {
  const cards = obsidianCards();
  if (!cards.length) return null;
  return cards.find(card => card.id === selectedObsidianCardId) || cards[0];
}

function isSafeObsidianLink(value) {
  const href = String(value || '').trim();
  if (!href) return false;
  if (href.startsWith('obsidian://')) return true;
  try {
    const url = new URL(href);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch (_error) {
    return false;
  }
}

function obsidianField(label, value) {
  return `${label}: ${String(value || 'None')}`;
}

function buildObsidianBrainstormContext(card) {
  return [
    'Use this Obsidian intake card as Brainstorm context.',
    obsidianField('Title', card?.title),
    obsidianField('Lane', card?.lane),
    obsidianField('Summary', card?.summary),
    obsidianField('Why', card?.why),
    obsidianField('Evidence', card?.evidence),
    obsidianField('Decision', card?.decision),
    obsidianField('Next action', card?.next_action),
    obsidianField('Source path', card?.path),
  ].join('\\n');
}

function setObsidianIntakeStatus(message, tone) {
  const status = $('obsidian-intake-status');
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

function renderObsidianIntake() {
  const panel = $('obsidian-intake-panel');
  const laneCounts = $('obsidian-intake-lane-counts');
  const body = $('obsidian-intake-body');
  if (!laneCounts || !body) return;
  const payload = obsidianIntake?.payload || null;
  const cards = Array.isArray(payload?.cards) ? payload.cards : [];
  const counts = payload?.lane_counts && typeof payload.lane_counts === 'object' ? payload.lane_counts : {};
  const selected = selectedObsidianCard();
  const scannedAt = payload?.scannedAt ? shortTime(payload.scannedAt) : '';
  if (panel) {
    panel.classList.toggle('is-unavailable', Boolean(payload && payload.available === false));
    panel.classList.toggle('is-ready', Boolean(cards.length));
  }

  laneCounts.innerHTML = Object.entries(counts)
    .map(([lane, count]) => `<span class="obsidian-lane-chip"><span>${esc(sentenceCase(lane))}</span><strong>${esc(count)}</strong></span>`)
    .join('');

  if (obsidianIntake.status === 'loading' && !cards.length) {
    setObsidianIntakeStatus('Loading', null);
    body.innerHTML = '<div class="obsidian-intake-empty">Loading Obsidian intake cards...</div>';
    return;
  }
  if (!payload) {
    setObsidianIntakeStatus('Unavailable', 'error');
    body.innerHTML = '<div class="obsidian-intake-empty error">Obsidian intake is unavailable.</div>';
    return;
  }
  if (payload.available === false) {
    setObsidianIntakeStatus('Unavailable', 'error');
    laneCounts.innerHTML = '';
    body.innerHTML = '';
    return;
  }
  if (!cards.length) {
    setObsidianIntakeStatus('Empty', null);
    body.innerHTML = '<div class="obsidian-intake-empty">No normalized intake cards are available yet.</div>';
    return;
  }

  setObsidianIntakeStatus(`${cards.length} cards`, 'success');
  const detailActions = [
    selected?.path
      ? `<button class="btn btn-sm btn-readonly" type="button" data-copy-command="${esc(selected.path)}" data-copy-kind="obsidian_path" aria-label="Copy Obsidian source path">Copy path</button>`
      : '',
    selected
      ? `<button class="btn btn-sm btn-secondary" type="button" data-obsidian-use-context="${esc(selected.id)}">Use as brainstorm context</button>`
      : '',
    isSafeObsidianLink(selected?.link)
      ? `<a class="btn btn-sm btn-secondary" href="${esc(selected.link)}" target="_blank" rel="noopener noreferrer">Open note</a>`
      : '',
  ].filter(Boolean).join('');

  body.innerHTML = `
    <div class="obsidian-intake-list" role="list" aria-label="Obsidian intake cards">
      ${cards.map(card => `
        <button class="obsidian-intake-card${card.id === selected?.id ? ' is-selected' : ''}" type="button" data-obsidian-card-id="${esc(card.id)}" role="listitem">
          <strong>${esc(card.title || 'Untitled')}</strong>
          <span class="obsidian-intake-card-meta">${esc(sentenceCase(card.lane || 'now'))} · ${esc(card.status || 'open')}</span>
          <span class="obsidian-intake-card-summary">${esc(card.summary || card.path || 'No summary')}</span>
        </button>
      `).join('')}
    </div>
    <article class="obsidian-intake-detail" aria-live="polite">
      <div class="obsidian-intake-detail-header">
        <h4>${esc(selected?.title || 'Untitled')}</h4>
        <div class="obsidian-intake-detail-meta">${esc(sentenceCase(selected?.lane || 'now'))} · ${esc(selected?.status || 'open')}${scannedAt ? ` · scanned ${esc(scannedAt)}` : ''}</div>
      </div>
      <div class="obsidian-intake-detail-grid">
        <div><strong>Summary</strong><span>${esc(selected?.summary || 'None')}</span></div>
        <div><strong>Why</strong><span>${esc(selected?.why || 'None')}</span></div>
        <div><strong>Evidence</strong><span>${esc(selected?.evidence || 'None')}</span></div>
        <div><strong>Decision</strong><span>${esc(selected?.decision || 'None')}</span></div>
        <div><strong>Next action</strong><span>${esc(selected?.next_action || 'None')}</span></div>
        <div><strong>Source path</strong><span>${esc(selected?.path || 'None')}</span></div>
      </div>
      <div class="obsidian-intake-detail-actions">
        ${detailActions}
        <span id="obsidian-intake-action-status" class="obsidian-intake-detail-actions-status" aria-live="polite"></span>
      </div>
    </article>
  `;
}

async function loadObsidianIntake() {
  obsidianIntake = { status: 'loading', payload: obsidianIntake?.payload || null };
  renderObsidianIntake();
  try {
    const resp = await fetch('/api/obsidian/cards');
    const payload = await resp.json();
    obsidianIntake = { status: resp.ok ? 'ready' : 'error', payload };
    const cards = Array.isArray(payload?.cards) ? payload.cards : [];
    if (!cards.find(card => card.id === selectedObsidianCardId)) {
      selectedObsidianCardId = cards[0]?.id || null;
    }
  } catch (e) {
    obsidianIntake = {
      status: 'error',
      payload: {
        available: false,
        cards: [],
        lane_counts: {},
        error: e?.message || 'Request failed',
      },
    };
    selectedObsidianCardId = null;
  }
  renderObsidianIntake();
}
"""
