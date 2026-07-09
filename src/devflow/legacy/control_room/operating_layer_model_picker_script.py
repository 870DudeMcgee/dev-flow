from __future__ import annotations

MODEL_PICKER_JS = """// === MODEL SELECTOR ===
function brainstormModelPickerConfig() {
  return {
    key: 'brainstorm',
    selectorId: 'model-selector',
    labelId: 'model-selector-label',
    dropdownId: 'model-dropdown',
    noteId: 'model-fallback-note',
    storageKey: 'devflow-brainstorm-profile',
    emptyText: 'No selectable profiles',
    setupEmptyText: 'Register a model in Model setup below.',
    optionIdPrefix: 'brainstorm-model',
  };
}

function builderModelPickerConfig() {
  return {
    key: 'builder',
    inputId: 'bj-builder-model',
    selectorId: 'bj-builder-model-selector',
    labelId: 'bj-builder-model-label',
    dropdownId: 'bj-builder-model-dropdown',
    noteId: 'bj-builder-model-fallback-note',
    fallbackId: 'hermes-qwen37plus',
    fallbackLabel: 'Hermes Qwen 3.7 Plus',
    optionIdPrefix: 'builder-model',
  };
}

function judgeModelPickerConfig() {
  return {
    key: 'judge',
    inputId: 'bj-judge-model',
    selectorId: 'bj-judge-model-selector',
    labelId: 'bj-judge-model-label',
    dropdownId: 'bj-judge-model-dropdown',
    noteId: 'bj-judge-model-fallback-note',
    fallbackId: 'hermes-opus48',
    fallbackLabel: 'Hermes Opus 4.8',
    avoidInputId: 'bj-builder-model',
    optionIdPrefix: 'judge-model',
  };
}

function seedAvailableAgentsFromSnapshot(snap) {
  const catalog = snap?.agent_catalog;
  const agents = Array.isArray(catalog?.hermes_agents) ? catalog.hermes_agents : null;
  const selectableAgents = Array.isArray(agents) ? agents.filter(agent => agent && agent.id) : [];
  const hasInventory = snap?.local_model_inventory && typeof snap.local_model_inventory === 'object';
  const hasReadiness = snap?.local_model_readiness && typeof snap.local_model_readiness === 'object';
  const schemaVersion = Number(catalog?.schema_version || 0);

  if (!selectableAgents.length || !hasInventory || !hasReadiness || (schemaVersion > 0 && schemaVersion < 1)) return false;

  availableAgents = selectableAgents;
  reconcileSelectedProfile();
  populateBJModelSelectors();
  return true;
}

async function loadAgents() {
  try {
    const resp = await fetch('/api/agents');
    const data = await resp.json();
    availableAgents = data.agents || [];
    localModelInventory = data.local_model_inventory || {};
    localModelReadiness = data.local_model_readiness || {};
    reconcileSelectedProfile();
    populateBJModelSelectors();
  } catch(e) {
    availableAgents = [];
    localModelInventory = {};
    localModelReadiness = {};
    reconcileSelectedProfile();
    populateBJModelSelectors();
  }
}

function renderModelDropdown() {
  renderModelPickerDropdown(brainstormModelPickerConfig());
}

function renderModelPickerDropdown(config) {
  const dropdown = $(config.dropdownId);
  if (!dropdown) return;
  const rows = Array.isArray(localModelInventory?.rows) ? localModelInventory.rows : [];
  const selectable = selectableAgents();
  const selectableIds = new Set(selectable.map(agent => agent.id));
  const selectedId = getModelPickerValue(config);

  const remoteRows = selectable.filter(agent => !agent.is_local).map(toSelectableModelRow);
  const localRows = selectable.filter(agent => agent.is_local).map(toSelectableModelRow);

  // Setup rows: installed-but-unregistered models, discovered endpoint models,
  // offline endpoints, and registered-but-unavailable profiles. These are NOT
  // selectable models — they live in a collapsed "Model setup" section.
  const installedRows = rows.filter(row => row.kind === 'unregistered_ollama_model');
  const endpointModelRows = rows.filter(row => row.kind === 'local_endpoint_model');
  const offlineEndpointRows = rows.filter(row => row.kind === 'local_endpoint' || row.status === 'unavailable');
  const unavailableProfileRows = rows.filter(row =>
    row.kind === 'registered_profile' && !selectableIds.has(row.selectable_profile_id || row.profile_id || '')
  );

  const needsProfileCount = installedRows.length + endpointModelRows.filter(row => row.status !== 'ready').length;
  const offlineCount = offlineEndpointRows.length;

  const sections = [];
  if (remoteRows.length) sections.push(renderModelDropdownSection('Remote profiles', remoteRows.map(agent => renderSelectableModelRow(agent, selectedId))));
  if (localRows.length) sections.push(renderModelDropdownSection('Local profiles', localRows.map(agent => renderSelectableModelRow(agent, selectedId))));
  if (!remoteRows.length && !localRows.length) {
    sections.push(`<div class="model-dropdown-item model-dropdown-empty"><div class="md-name">${esc(config.emptyText || 'No selectable profiles')}</div><div class="md-purpose">${esc(config.setupEmptyText || 'Register a model in Model setup below.')}</div></div>`);
  }

  const setupRows = [
    ...installedRows.map(renderInventoryModelRow),
    ...endpointModelRows.map(renderInventoryModelRow),
    ...offlineEndpointRows.map(renderInventoryModelRow),
    ...unavailableProfileRows.map(renderInventoryModelRow),
  ];
  if (setupRows.length) {
    sections.push(renderModelSetupSection(setupRows, needsProfileCount, offlineCount));
  }

  dropdown.innerHTML = sections.join('');

  dropdown.querySelectorAll('[data-agent-id]').forEach(item => {
    item.addEventListener('click', async (e) => {
      e.stopPropagation();
      const agentId = item.dataset.agentId;
      const agent = availableAgents.find(a => a.id === agentId);
      if (agent) {
        await selectModelPickerAgent(config, agent);
      }
    });
  });
  // Toggle the collapsed Model setup section.
  dropdown.querySelectorAll('[data-model-setup-toggle]').forEach(toggle => {
    toggle.addEventListener('click', (e) => {
      e.stopPropagation();
      const body = toggle.parentElement?.querySelector('.model-setup-body');
      if (!body) return;
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!expanded));
      body.hidden = expanded;
    });
  });
  dropdown.querySelectorAll('[data-local-model-command]').forEach(button => {
    button.addEventListener('click', async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const command = button.dataset.localModelCommand || '';
      if (!command) return;
      button.disabled = true;
      try {
        await runApprovedCommand(command, {});
        await loadSnapshot(selectedProjectId);
      } catch(err) {
        if (!err?.actionRendered) renderActionError({ message: err.message || 'Onboarding failed', command });
      } finally {
        button.disabled = false;
      }
    });
  });
}

function toSelectableModelRow(agent) {
  return {
    kind: 'agent',
    id: agent.id,
    label: agent.label || agent.id,
    model: agent.model || '',
    purpose: agent.purpose || '',
    is_local: Boolean(agent.is_local),
  };
}

function getModelPickerValue(config) {
  if (config.inputId) return ($(config.inputId)?.value || '').trim();
  return selectedProfileId || localStorage.getItem(config.storageKey || '') || '';
}

function setModelPickerValue(config, value, options = {}) {
  if (config.inputId) {
    const input = $(config.inputId);
    if (input) input.value = value || '';
  } else {
    selectedProfileId = value || null;
    if (options.persist && config.storageKey && value) localStorage.setItem(config.storageKey, value);
  }
  const note = $(config.noteId);
  if (note) { note.hidden = true; note.textContent = ''; }
}

async function selectModelPickerAgent(config, agent) {
  if (!agent?.id) return;
  const dropdown = $(config.dropdownId);
  const selector = $(config.selectorId);
  const previousValue = getModelPickerValue(config);
  const previousAgent = previousValue ? availableAgents.find(a => a.id === previousValue) : null;
  const selectNow = () => {
    setModelPickerValue(config, agent.id, { persist: true });
    updateModelPickerLabel(config, agent);
    closeModelPickerDropdown(config);
    renderModelPickerDropdown(config);
  };

  if (!shouldEnsureLocalModelBeforeSelection(agent)) {
    selectNow();
    return;
  }

  try {
    setModelPickerBusy(config, true);
    updateModelPickerLabel(config, { id: agent.id, label: 'Starting...' });
    if (dropdown) dropdown.hidden = true;
    if (selector) selector.setAttribute('aria-expanded', 'false');
    const evidence = await ensureLocalModelProfile(agent.id);
    if (!localModelEnsureSucceeded(evidence)) {
      throw new Error(evidence?.reason || `Local model boot did not finish (${evidence?.status || 'unknown'})`);
    }
    setModelPickerValue(config, agent.id, { persist: true });
    updateModelPickerLabel(config, agent);
    renderModelPickerDropdown(config);
  } catch(e) {
    setModelPickerValue(config, previousValue, { persist: false });
    updateModelPickerLabel(config, previousAgent || { id: previousValue, label: previousValue || config.fallbackLabel || 'Select model' });
    showModelPickerNote(config, `Could not start ${agent.label || agent.id}: ${e.message || 'unknown error'}`);
  } finally {
    setModelPickerBusy(config, false);
  }
}

function closeModelPickerDropdown(config) {
  const dropdown = $(config.dropdownId);
  const selector = $(config.selectorId);
  if (dropdown) dropdown.hidden = true;
  if (selector) selector.setAttribute('aria-expanded', 'false');
}

function setModelPickerBusy(config, busy) {
  const selector = $(config.selectorId);
  if (!selector) return;
  selector.classList.toggle('is-starting', Boolean(busy));
  selector.setAttribute('aria-busy', busy ? 'true' : 'false');
}

function showModelPickerNote(config, message) {
  const note = $(config.noteId);
  if (!note) return;
  note.hidden = false;
  note.textContent = message;
}

function shouldEnsureLocalModelBeforeSelection(agent) {
  if (!agent?.is_local) return false;
  if (agent.provider === 'ollama' || agent.adapter === 'ollama_chat') return false;
  return true;
}

async function ensureLocalModelProfile(profileId) {
  const body = { profile_id: profileId };
  if (selectedProjectId) body.project = selectedProjectId;
  const resp = await fetch('/api/local-model/ensure', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  let payload = {};
  try {
    payload = await resp.json();
  } catch(_e) {
    payload = {};
  }
  if (!resp.ok) {
    throw new Error(payload.error || `Local model ensure failed (${resp.status})`);
  }
  return payload;
}

function localModelEnsureSucceeded(evidence) {
  const status = String(evidence?.status || evidence?.lifecycle?.status || '').toLowerCase();
  return !['failed', 'error', 'started_unready'].includes(status);
}

function updateModelPickerLabel(config, agent) {
  const label = $(config.labelId);
  if (!label) return;
  label.textContent = agent?.label || agent?.id || config.fallbackLabel || 'Select model';
}

function reconcileModelPicker(config) {
  const selectable = selectableAgents();
  const currentValue = getModelPickerValue(config);
  const savedId = config.storageKey ? localStorage.getItem(config.storageKey) || currentValue : currentValue;
  const preferred = savedId ? selectable.find(a => a.id === savedId) : null;
  if (preferred) {
    setModelPickerValue(config, preferred.id, { persist: false });
    updateModelPickerLabel(config, preferred);
    renderModelPickerDropdown(config);
    return;
  }
  let fallback = null;
  if (config.fallbackId) fallback = selectable.find(a => a.id === config.fallbackId) || null;
  if (!fallback && config.avoidInputId) {
    const avoidValue = ($(config.avoidInputId)?.value || '').trim();
    fallback = selectable.find(a => a.id !== avoidValue) || null;
  }
  fallback = fallback || selectable[0] || null;
  if (fallback) {
    setModelPickerValue(config, fallback.id, { persist: false });
    updateModelPickerLabel(config, fallback);
    const note = $(config.noteId);
    if (note) {
      if (savedId && savedId !== fallback.id) {
        note.hidden = false;
        note.textContent = `Saved model unavailable - using ${fallback.label || fallback.id}`;
      } else {
        note.hidden = true;
        note.textContent = '';
      }
    }
  } else {
    setModelPickerValue(config, config.fallbackId || '', { persist: false });
    updateModelPickerLabel(config, { id: config.fallbackId, label: config.fallbackLabel });
  }
  renderModelPickerDropdown(config);
}

function renderModelSetupSection(rowHtml, needsProfileCount, offlineCount) {
  if (!rowHtml.length) return '';
  const counts = [];
  if (needsProfileCount > 0) counts.push(`${needsProfileCount} model${needsProfileCount === 1 ? '' : 's'} need profiles`);
  if (offlineCount > 0) counts.push(`${offlineCount} endpoint${offlineCount === 1 ? '' : 's'} offline`);
  const countHtml = counts.length ? `<span class="model-setup-counts">${esc(counts.join(' · '))}</span>` : '';
  return `<div class="model-dropdown-section model-setup-section">
    <button type="button" class="model-setup-toggle" data-model-setup-toggle aria-expanded="false">
      <span class="model-dropdown-section-title">Model setup</span>
      ${countHtml}
      <span class="model-setup-chevron" aria-hidden="true">▾</span>
    </button>
    <div class="model-setup-body" hidden>${rowHtml.join('')}</div>
  </div>`;
}

function selectableAgents() {
  return (availableAgents || []).filter(agent => agent && agent.id);
}

function renderModelDropdownSection(label, rowHtml) {
  if (!rowHtml.length) return '';
  return `<div class="model-dropdown-section">
    <div class="model-dropdown-section-title">${esc(label)}</div>
    ${rowHtml.join('')}
  </div>`;
}

function renderSelectableModelRow(agent, activeId) {
  const isActive = agent.id === activeId;
  const localityBadge = agent.is_local
    ? '<span class="md-badge local">LOCAL</span>'
    : '<span class="md-badge cloud">CLOUD</span>';
  return `<div class="model-dropdown-item${isActive ? ' active' : ''}" data-agent-id="${esc(agent.id)}">
    <div class="md-name">${esc(agent.label)}${localityBadge}</div>
    <div class="md-model">${esc(agent.model)}</div>
    ${agent.purpose ? `<div class="md-purpose">${esc(agent.purpose)}</div>` : ''}
  </div>`;
}

function renderInventoryModelRow(row) {
  const action = row?.action || null;
  const status = row?.status_label || sentenceCase(row?.status || '');
  const actionHtml = action?.command
    ? `<button type="button" class="local-model-action" data-local-model-command="${esc(action.command)}">${esc(action.label || 'Add profile')}</button>`
    : '';
  const detail = row?.detail || row?.machine_fit_reason || '';
  return `<div class="model-dropdown-item model-dropdown-inventory-item">
    <div class="md-name">${esc(row?.model || row?.provider_label || 'Local endpoint')}<span class="md-badge muted">${esc(status)}</span></div>
    <div class="md-model">${esc(row?.provider_label || row?.provider_id || '')}${row?.adapter ? ` · ${esc(row.adapter)}` : ''}</div>
    ${detail ? `<div class="md-purpose">${esc(detail)}</div>` : ''}
    ${actionHtml}
  </div>`;
}

function setupModelSelector() {
  setupModelPicker(brainstormModelPickerConfig());
}

function setupModelPicker(config, options = {}) {
  const selector = $(config.selectorId);
  const dropdown = $(config.dropdownId);
  if (!selector || !dropdown) return;
  selector.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdown.hidden = !dropdown.hidden;
    selector.setAttribute('aria-expanded', String(!dropdown.hidden));
    if (!dropdown.hidden) {
      _initDropdownKeyboard(selector, dropdown, '.model-dropdown-item[data-agent-id]', config.optionIdPrefix || config.key || 'model');
    }
  });
  document.addEventListener('click', () => {
    dropdown.hidden = true;
    selector.setAttribute('aria-expanded', 'false');
  });
  dropdown.addEventListener('click', (e) => e.stopPropagation());
  // Keyboard: Enter/Space toggles, arrows navigate, Escape closes.
  selector.addEventListener('keydown', (e) => {
    if (!dropdown.hidden && e.key === 'Enter' && dropdown.querySelector('.keyboard-active')) {
      e.preventDefault();
      dropdown.querySelector('.keyboard-active').click();
    } else if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      dropdown.hidden = !dropdown.hidden;
      selector.setAttribute('aria-expanded', String(!dropdown.hidden));
      if (!dropdown.hidden) _initDropdownKeyboard(selector, dropdown, '.model-dropdown-item[data-agent-id]', config.optionIdPrefix || config.key || 'model');
    } else if (e.key === 'Escape') {
      dropdown.hidden = true;
      selector.setAttribute('aria-expanded', 'false');
    } else if (!dropdown.hidden && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault();
      _moveDropdownActive(dropdown, e.key === 'ArrowDown' ? 1 : -1, selector, '.model-dropdown-item[data-agent-id]', config.optionIdPrefix || config.key || 'model');
    }
  });
  if (options.load) loadAgents();
}

// If the saved profile is unavailable, fall back to the first selectable
// profile for this session WITHOUT overwriting localStorage, and surface a
// small note naming the fallback. A concrete user pick (which writes
// localStorage) clears the note.
function reconcileSelectedProfile() {
  reconcileModelPicker(brainstormModelPickerConfig());
}

// --- Shared dropdown keyboard helpers ---
function _initDropdownKeyboard(trigger, dropdown, itemSelector, idPrefix = 'dd-opt') {
  const items = dropdown.querySelectorAll(itemSelector);
  items.forEach(i => i.classList.remove('keyboard-active'));
  if (items.length) {
    items[0].classList.add('keyboard-active');
    items[0].scrollIntoView({ block: 'nearest' });
    trigger.setAttribute('aria-activedescendant', items[0].id || _ensureIds(items, idPrefix + '-opt'));
  }
  // Make items keyboard-clickable
  items.forEach(item => {
    item.onkeydown = (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); item.click(); }
    };
  });
}

function _moveDropdownActive(dropdown, dir, trigger, itemSelector, idPrefix = 'dd-opt') {
  const items = Array.from(dropdown.querySelectorAll(itemSelector));
  if (!items.length) return;
  let idx = items.findIndex(i => i.classList.contains('keyboard-active'));
  idx = idx < 0 ? 0 : (idx + dir + items.length) % items.length;
  items.forEach(i => i.classList.remove('keyboard-active'));
  items[idx].classList.add('keyboard-active');
  items[idx].scrollIntoView({ block: 'nearest' });
  trigger.setAttribute('aria-activedescendant', items[idx].id || _ensureIds(items, idPrefix + '-opt'));
}

function _ensureIds(items, prefix) {
  let firstId = '';
  items.forEach((item, i) => {
    if (!item.id) item.id = prefix + '-' + i;
    if (!i) firstId = item.id;
  });
  return firstId;
}

"""
