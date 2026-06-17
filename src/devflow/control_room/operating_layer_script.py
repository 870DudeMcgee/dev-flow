from __future__ import annotations

APP_JS = """
// === STATE ===
let snapshot = null;
let selectedProjectId = null;
let brainstormSessionId = localStorage.getItem('devflow-brainstorm-session') || `browser-${Date.now().toString(36)}`;
localStorage.setItem('devflow-brainstorm-session', brainstormSessionId);
let brainstormMessage = '';
let selectedTaskId = null;
let availableAgents = [];
let selectedProfileId = localStorage.getItem('devflow-brainstorm-profile') || null;

// === HELPERS ===
function $(id) { return document.getElementById(id); }
function esc(s) { const d = document.createElement('div'); d.textContent = String(s ?? ''); return d.innerHTML; }
function shortTime(iso) {
  if (!iso) return '--';
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
function ago(iso) {
  if (!iso || iso === 'NaN' || iso === 'undefined') return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 0) return 'just now';
  if (sec < 60) return sec + 's ago';
  if (sec < 3600) return Math.floor(sec / 60) + 'm ago';
  if (sec < 86400) return Math.floor(sec / 3600) + 'h ago';
  return Math.floor(sec / 86400) + 'd ago';
}

// === SNAPSHOT LOADING ===
async function loadSnapshot(project) {
  const url = project ? `/api/snapshot?project=${encodeURIComponent(project)}` : '/api/snapshot';
  try {
    const resp = await fetch(url);
    snapshot = await resp.json();
    render();
  } catch (e) {
    snapshot = null;
    render();
  }
}

// === NAVIGATION ===
function setActiveNav(navId) {
  document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
  const target = document.querySelector(`[data-nav="${navId}"]`);
  if (target) target.classList.add('active');
}

// === REPO SELECTOR ===
function setupRepoSelector() {
  const selector = $('repo-selector');
  const dropdown = $('repo-dropdown');
  if (!selector || !dropdown) return;
  selector.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdown.hidden = !dropdown.hidden;
  });
  dropdown.addEventListener('click', (e) => {
    const item = e.target.closest('.repo-item');
    if (!item) return;
    const path = item.dataset.repoPath;
    const name = item.querySelector('strong')?.textContent || 'Project';
    // Update selector
    document.getElementById('repo-name').textContent = name;
    document.getElementById('repo-path').textContent = path;
    // Update active state
    dropdown.querySelectorAll('.repo-item').forEach(el => { el.classList.remove('active'); el.querySelector('.check')?.remove(); });
    item.classList.add('active');
    const check = document.createElement('span');
    check.className = 'check';
    check.textContent = '✓';
    check.setAttribute('aria-hidden', 'true');
    item.appendChild(check);
    dropdown.hidden = true;
    selectedProjectId = path;
    loadSnapshot(path);
  });
  document.addEventListener('click', () => { dropdown.hidden = true; });
}

// === MODEL SELECTOR ===
async function loadAgents() {
  try {
    const resp = await fetch('/api/agents');
    const data = await resp.json();
    availableAgents = data.agents || [];
    renderModelDropdown();
  } catch(e) {
    availableAgents = [];
  }
}

function renderModelDropdown() {
  const dropdown = $('model-dropdown');
  if (!dropdown) return;
  if (availableAgents.length === 0) {
    dropdown.innerHTML = '<div class="model-dropdown-item"><div class="md-name">No agents available</div></div>';
    return;
  }
  dropdown.innerHTML = availableAgents.map(agent => {
    const isActive = agent.id === selectedProfileId;
    const localityBadge = agent.is_local ? '<span style="font-size:9px;color:var(--accent);margin-left:4px;">LOCAL</span>' : '<span style="font-size:9px;color:var(--text-muted);margin-left:4px;">CLOUD</span>';
    return `<div class="model-dropdown-item${isActive ? ' active' : ''}" data-agent-id="${esc(agent.id)}">
      <div class="md-name">${esc(agent.label || agent.id)}${localityBadge}</div>
      <div class="md-model">${esc(agent.model)}</div>
      ${agent.purpose ? `<div class="md-purpose">${esc(agent.purpose)}</div>` : ''}
    </div>`;
  }).join('');
  dropdown.querySelectorAll('.model-dropdown-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      const agentId = item.dataset.agentId;
      const agent = availableAgents.find(a => a.id === agentId);
      if (agent) {
        selectedProfileId = agentId;
        localStorage.setItem('devflow-brainstorm-profile', agentId);
        const label = $('model-selector-label');
        if (label) label.textContent = agent.label || agent.id;
        dropdown.hidden = true;
        renderModelDropdown();
      }
    });
  });
}

function setupModelSelector() {
  const selector = $('model-selector');
  const dropdown = $('model-dropdown');
  if (!selector || !dropdown) return;
  selector.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdown.hidden = !dropdown.hidden;
  });
  document.addEventListener('click', () => { dropdown.hidden = true; });
  loadAgents().then(() => {
    // Restore label from saved profile
    if (selectedProfileId) {
      const agent = availableAgents.find(a => a.id === selectedProfileId);
      const label = $('model-selector-label');
      if (label && agent) label.textContent = agent.label || agent.id;
    }
  });
}

// === BRAINSTORM SESSION MANAGEMENT ===
async function loadBrainstormTranscript(sessionId) {
  try {
    const resp = await fetch(`/api/brainstorm/transcript?session_id=${encodeURIComponent(sessionId)}`);
    const data = await resp.json();
    const container = $('brainstorm-transcript');
    if (!container) return;
    if (!data.messages || data.messages.length === 0) {
      container.innerHTML = '<div class="msg-avatar ai" style="padding:20px;text-align:center;color:var(--text-muted);font-size:13px;background:none;border:none;justify-content:center;">Start a brainstorm conversation above.</div>';
      return;
    }
    container.innerHTML = '';
    for (const msg of data.messages) {
      const isUser = msg.role === 'user';
      const isError = msg.role === 'system' && msg.kind === 'provider_error';
      const isStageGen = msg.kind && msg.kind.endsWith('_generation');
      if (isStageGen) {
        appendBrainstormMsg('assistant', msg.content, { time: shortTime(msg.created_at) });
      } else if (isError) {
        appendBrainstormMsg('system', msg.content, { kind: 'provider_error', time: shortTime(msg.created_at) });
      } else {
        appendBrainstormMsg(msg.role, msg.content, { time: shortTime(msg.created_at) });
      }
    }
    container.scrollTop = container.scrollHeight;
    // Refresh pipeline state for this session
    pipelineState = {
      hasSpec: data.spec != null,
      hasPlan: data.plan != null,
      hasImplementation: false,
    };
    renderPipeline();
  } catch(e) {
    console.error('Failed to load transcript:', e);
  }
}

function newBrainstormSession() {
  brainstormSessionId = `browser-${Date.now().toString(36)}`;
  localStorage.setItem('devflow-brainstorm-session', brainstormSessionId);
  const container = $('brainstorm-transcript');
  if (container) {
    container.innerHTML = '<div class="msg-avatar ai" style="padding:20px;text-align:center;color:var(--text-muted);font-size:13px;background:none;border:none;justify-content:center;">Start a brainstorm conversation above.</div>';
  }
  pipelineState = { hasSpec: false, hasPlan: false, hasImplementation: false };
  renderPipeline();
  loadBrainstormSessions();
}

async function loadBrainstormSessions() {
  try {
    const resp = await fetch('/api/brainstorm/sessions');
    const data = await resp.json();
    const container = $('brainstorm-sessions-list');
    if (!container) return;
    const sessions = data.sessions || [];
    if (sessions.length === 0) {
      container.innerHTML = '<div style="padding:8px;color:var(--text-muted);font-size:11px;">No previous sessions</div>';
      return;
    }
    container.innerHTML = sessions.slice(0, 30).map(s => {
      const isActive = s.session_id === brainstormSessionId;
      const badges = [];
      if (s.has_spec) badges.push('<span class="si-badge">SPEC</span>');
      if (s.has_plan) badges.push('<span class="si-badge">PLAN</span>');
      return `<div class="session-item${isActive ? ' active' : ''}" data-session-id="${esc(s.session_id)}">
        <div class="si-preview">${esc(s.preview)}</div>
        <div class="si-meta">
          <span>${s.message_count} msgs</span>
          <span>${ago(s.modified_at)}</span>
          ${badges.join(' ')}
        </div>
      </div>`;
    }).join('');
    container.querySelectorAll('.session-item').forEach(item => {
      item.addEventListener('click', () => {
        const sid = item.dataset.sessionId;
        if (!sid) return;
        brainstormSessionId = sid;
        localStorage.setItem('devflow-brainstorm-session', sid);
        loadBrainstormTranscript(sid);
        loadBrainstormSessions();
      });
    });
  } catch(e) {
    console.error('Failed to load sessions:', e);
  }
}

// === BRAINSTORM CHAT ===
async function sendBrainstormMessage(message) {
  const body = { message, session_id: brainstormSessionId };
  if (selectedProfileId) body.profile_id = selectedProfileId;
  const resp = await fetch('/api/brainstorm/message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return resp.json();
}

async function escalateBrainstormStage(stage, useModel) {
  const body = { session_id: brainstormSessionId, stage };
  if (selectedProfileId) body.profile_id = selectedProfileId;
  if (useModel) body.use_model = true;
  const resp = await fetch('/api/brainstorm/escalate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return resp.json();
}

function renderBrainstormTranscript(messages) {
  const container = $('brainstorm-transcript');
  if (!container) return;
  if (!messages || messages.length === 0) {
    container.innerHTML = '<div class="msg-avatar ai" style="padding:20px;text-align:center;color:var(--text-muted);font-size:13px;background:none;border:none;justify-content:center;">Start a brainstorm conversation above.</div>';
    return;
  }
  container.innerHTML = messages.map(msg => {
    const isUser = msg.role === 'user';
    const isError = msg.role === 'system' && msg.kind === 'provider_error';
    const avatar = isUser ? 'U' : (isError ? '!' : 'DS');
    const author = isUser ? 'You' : (isError ? 'DevFlow' : 'DeepSeek V4 Flash Free');
    return `<div class="brainstorm-msg ${isUser ? 'user' : ''}">
      <div class="msg-avatar ${isUser ? 'user' : 'ai'}"${isError ? ' style="color:var(--red);border-color:var(--red-soft);"' : ''}>${avatar}</div>
      <div class="msg-body">
        <div class="msg-meta">
          <span class="msg-author">${author}</span>
          <span class="msg-time">${shortTime(msg.created_at)}</span>
        </div>
        <div class="msg-bubble ${isUser ? 'user' : 'ai'}"${isError ? ' style="border-color:var(--red-soft);color:var(--red);"' : ''}>${esc(msg.content)}</div>
        ${!isUser && !isError ? `<div class="msg-actions">
          <button class="msg-action-btn" title="Helpful">👍</button>
          <button class="msg-action-btn" title="Not helpful">👎</button>
          <button class="msg-action-btn" title="Copy code">&lt;/&gt;</button>
        </div>` : ''}
      </div>
    </div>`;
  }).join('');
  container.scrollTop = container.scrollHeight;
}

function appendBrainstormMsg(role, content, opts) {
  const transcript = $('brainstorm-transcript');
  if (!transcript) return;
  const isUser = role === 'user';
  const isError = role === 'system' && opts && opts.kind === 'provider_error';
  const isInfo = role === 'system' && !isError;
  const isThinking = opts && opts.thinking;
  const avatar = isUser ? 'U' : (isError ? '!' : (isInfo ? 'ℹ' : 'DS'));
  const modelLabel = selectedProfileId ? (availableAgents.find(a => a.id === selectedProfileId)?.label || availableAgents.find(a => a.id === selectedProfileId)?.model || 'DeepSeek') : 'DeepSeek V4 Flash Free';
  const author = isUser ? 'You' : (isError ? 'DevFlow' : (isInfo ? 'DevFlow' : modelLabel));
  const time = (opts && opts.time) || 'just now';
  const el = document.createElement('div');
  el.className = 'brainstorm-msg ' + (isUser ? 'user' : '');
  if (isThinking) el.dataset.thinking = '1';
  const avatarStyle = isError ? ' style="color:var(--red);border-color:var(--red-soft);"' : (isInfo ? ' style="color:var(--accent);border-color:var(--accent-soft);"' : '');
  const bubbleStyle = isError ? ' style="border-color:var(--red-soft);color:var(--red);"' : (isInfo ? ' style="border-color:var(--accent-soft);color:var(--text-soft);background:var(--accent-bg);"' : '');
  el.innerHTML = `<div class="msg-avatar ${isUser ? 'user' : 'ai'}"${avatarStyle}>${avatar}</div>` +
    `<div class="msg-body"><div class="msg-meta"><span class="msg-author">${author}</span><span class="msg-time">${time}</span></div>` +
    `<div class="msg-bubble ${isUser ? 'user' : 'ai'}"${bubbleStyle}>${isThinking ? '<span class="thinking-dots"><span>.</span><span>.</span><span>.</span></span>' : esc(content)}</div></div>`;
  transcript.appendChild(el);
  transcript.scrollTop = transcript.scrollHeight;
}

function removeThinkingIndicator() {
  const transcript = $('brainstorm-transcript');
  if (!transcript) return;
  const thinking = transcript.querySelector('[data-thinking="1"]');
  if (thinking) thinking.remove();
}

function setupBrainstormForm() {
  const form = $('brainstorm-chat-form');
  const input = $('brainstorm-message');
  if (!form || !input) return;
  const sendBtn = form.querySelector('button[type="submit"]');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (!msg) return;
    input.disabled = true;
    if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = 'Sending…'; }
    // Optimistic append
    appendBrainstormMsg('user', msg);
    input.value = '';
    // Thinking indicator
    appendBrainstormMsg('assistant', '', { thinking: true });
    try {
      const payload = await sendBrainstormMessage(msg);
      removeThinkingIndicator();
      if (payload.status === 'success' && payload.assistant_message) {
        appendBrainstormMsg('assistant', payload.assistant_message, { time: shortTime(payload.created_at) });
      } else if (payload.error) {
        appendBrainstormMsg('system', payload.error, { kind: 'provider_error', time: shortTime(payload.created_at) });
      } else if (payload.messages) {
        renderBrainstormTranscript(payload.messages);
      }
    } catch(e) {
      removeThinkingIndicator();
      appendBrainstormMsg('system', 'Request failed. Check that OPENROUTER_API_KEY is set.', { kind: 'provider_error' });
    }
    input.disabled = false;
    if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Send'; }
    loadBrainstormSessions();
    input.focus();
  });
  // Shift+Enter for newline
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      form.dispatchEvent(new Event('submit'));
    }
  });
}

// === PIPELINE ===
let pipelineState = { hasSpec: false, hasPlan: false, hasImplementation: false };

async function refreshPipelineState() {
  try {
    const resp = await fetch(`/api/brainstorm/transcript?session_id=${encodeURIComponent(brainstormSessionId)}`);
    const data = await resp.json();
    pipelineState = {
      hasSpec: data.spec != null,
      hasPlan: data.plan != null,
      hasImplementation: false,
    };
  } catch(e) { /* ignore */ }
  renderPipeline();
}

function renderPipeline() {
  const stages = [
    { id: 'brainstorm', label: 'Brainstorm', nextStage: 'spec' },
    { id: 'spec', label: 'Spec', nextStage: 'plan' },
    { id: 'plan', label: 'Plan', nextStage: 'implementation' },
    { id: 'implement', label: 'Implement', nextStage: null },
  ];
  // Determine completed stages
  const completed = new Set();
  completed.add('brainstorm'); // always have a brainstorm
  if (pipelineState.hasSpec) completed.add('spec');
  if (pipelineState.hasPlan) completed.add('plan');

  // Current active stage = first not completed
  let activeStage = 'implement';
  for (const s of stages) {
    if (!completed.has(s.id)) { activeStage = s.id; break; }
  }

  document.querySelectorAll('.pipeline-step').forEach(el => {
    const stage = el.dataset.stage;
    const isCompleted = completed.has(stage);
    const isActive = stage === activeStage;
    const isLocked = !isActive && !isCompleted;

    el.classList.remove('active', 'locked');
    if (isActive) el.classList.add('active');
    if (isLocked) el.classList.add('locked');

    const statusEl = el.querySelector('.step-status');
    if (statusEl) {
      if (isCompleted && !isActive) {
        statusEl.textContent = 'Done';
        statusEl.className = 'step-status active';
      } else if (isActive) {
        statusEl.textContent = 'Active';
        statusEl.className = 'step-status active';
      } else {
        statusEl.textContent = 'Pending';
        statusEl.className = 'step-status pending';
      }
    }

    // Enable the button only on the active stage
    const btn = el.querySelector('.btn[data-brainstorm-stage]');
    if (btn) {
      btn.disabled = !isActive;
      btn.classList.toggle('disabled', !isActive);
      btn.classList.toggle('btn-primary', isActive);
      btn.classList.toggle('btn-secondary', !isActive);
    }
  });
}

function setupPipelineButtons() {
  document.querySelectorAll('[data-brainstorm-stage]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const stage = btn.dataset.brainstormStage;
      if (!stage) return;
      btn.disabled = true;
      const originalText = btn.textContent;
      btn.textContent = 'Escalating...';
      const useModel = stage === 'spec' || stage === 'plan';
      if (useModel) {
        const modelLabel = selectedProfileId ? (availableAgents.find(a => a.id === selectedProfileId)?.label || 'selected model') : 'DeepSeek V4 Flash Free';
        appendBrainstormMsg('assistant', '', { thinking: true });
        appendBrainstormMsg('system', `Generating ${stage} with ${modelLabel}...`, {});
      }
      try {
        const payload = await escalateBrainstormStage(stage, useModel);
        if (useModel) removeThinkingIndicator();
        if (payload.error) {
          appendBrainstormMsg('system', payload.error, { kind: 'provider_error' });
        } else if (payload.status === 'ready') {
          const stageLabel = payload.stage ? payload.stage.charAt(0).toUpperCase() + payload.stage.slice(1) : 'Stage';
          let info = `Escalated to ${stageLabel}. `;
          if (payload.stage === 'implementation' && payload.action) {
            info += `Task action ready: ${payload.action.command}`;
          } else if (payload.model_info && payload.model_info.used_model) {
            info += `Generated by ${payload.model_info.model}. Artifact: ${payload.artifact_path || 'session dir'}`;
            if (payload.model_info.content) {
              appendBrainstormMsg('system', info, {});
              appendBrainstormMsg('assistant', payload.model_info.content, { time: shortTime(new Date().toISOString()) });
              info = '';
            }
          } else if (payload.model_info && payload.model_info.error) {
            info += `Model error: ${payload.model_info.error}. Artifact: ${payload.artifact_path || 'session dir'}`;
          } else {
            info += `Artifact written to ${payload.artifact_path || 'session dir'}. No model call.`;
          }
          if (info) appendBrainstormMsg('system', info, {});
        }
        loadSnapshot(selectedProjectId);
        refreshPipelineState();
        loadBrainstormSessions();
      } catch(e) {
        removeThinkingIndicator();
        appendBrainstormMsg('system', 'Escalation failed: ' + (e.message || 'unknown error'), { kind: 'provider_error' });
      } finally {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    });
  });
}

// === WORKER LANES ===
function renderWorkerLanes(tasks) {
  const container = $('active-work-groups');
  if (!container) return;
  const all = (tasks || []).filter(t => t.lane !== 'closed');
  const totalCount = (tasks || []).length;
  const count = $('active-work-count');
  if (count) count.textContent = all.length + ' active / ' + totalCount + ' total';
  if (all.length === 0) {
    container.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted);font-size:12px;">No active tasks — all ' + totalCount + ' tasks are closed</div>';
    return;
  }
  container.innerHTML = all.map(t => {
    const status = t.lane || 'new';
    const lightClass = status === 'new' ? 'green' : status === 'needs_verification' ? 'yellow' : status === 'ready_to_promote' ? 'green' : status === 'in_progress' ? 'yellow' : 'gray';
    const ts = t.latest || t.updated_at || t.created_at;
    return `<div class="worker-card" data-task-id="${esc(t.id || '')}" onclick="openFocus('task','${esc(t.id || '')}')">
      <span class="worker-light ${lightClass}"></span>
      <span class="worker-name">${esc(t.title || t.id || 'Task')}</span>
      <span class="worker-branch">${esc(t.lane || '')}</span>
      <span class="worker-time">${ago(ts)}</span>
    </div>`;
  }).join('');
}

// === REVIEW QUEUE ===
function renderReviewQueue(reviewLoop) {
  const container = $('guided-review-queue');
  if (!container) return;
  const available = reviewLoop ? (reviewLoop.ready_to_promote_count || 0) + (reviewLoop.needs_verification_count || 0) : 0;
  const count = $('review-queue-count');
  if (count) count.textContent = available + ' items';
  if (available === 0) {
    container.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted);font-size:12px;">' + esc(reviewLoop?.headline || 'No items to review') + '</div>';
    return;
  }
  const summary = reviewLoop?.evidence_summary || reviewLoop?.headline || reviewLoop?.status || '';
  container.innerHTML = '<div style="padding:8px 12px;font-size:12px;color:var(--text-soft);">' + esc(summary) +
    '</div><div style="display:flex;gap:8px;padding:4px 12px 8px;">' +
    '<span class="review-priority high">Ready: ' + (reviewLoop.ready_to_promote_count || 0) + '</span>' +
    '<span class="review-priority med">Verify: ' + (reviewLoop.needs_verification_count || 0) + '</span>' +
    '</div>';
}

// === EVIDENCE STREAM ===
function renderEvidenceStream(evidence) {
  const container = $('guided-evidence-stream');
  if (!container) return;
  const items = evidence || [];
  const count = $('evidence-stream-count');
  if (count) count.textContent = items.length + ' items';
  if (items.length === 0) {
    container.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted);font-size:12px;">No evidence yet</div>';
    return;
  }
  container.innerHTML = items.slice(0, 20).map(item => {
    const cmd = item.verification_command || '';
    const text = cmd ? cmd.substring(0, 80) : ('task ' + (item.task_id || '?'));
    const ts = item.created_at || item.timestamp || item.generated_at;
    return `<div class="evidence-item" onclick="openFocus('evidence','${esc(item.task_id || item.id || '')}')">
      <span class="evidence-icon">></span>
      <span class="evidence-text">${esc(text)}</span>
      <span class="evidence-time">${ts ? ago(ts) : ''}</span>
    </div>`;
  }).join('');
}

// === MISSION FEED ===
function renderMissionFeed(feedItems) {
  const container = $('mission-feed-list');
  if (!container) return;
  const items = feedItems || [];
  const count = $('mission-feed-count');
  if (count) count.textContent = String(items.length);
  if (items.length === 0) {
    container.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-muted);font-size:12px;">No recent activity</div>';
    return;
  }
  container.innerHTML = items.slice(0, 20).map(item => {
    const tone = item.tone || item.type || '';
    const icon = tone === 'command' || tone === 'shell' ? '>' : tone === 'success' ? '✓' : tone === 'error' ? '!' : tone === 'write' ? '+' : '·';
    const text = item.title || item.label || item.detail || item.command || item.summary || '';
    const ts = item.timestamp || item.created_at || item.generated_at;
    return `<div class="feed-item" onclick="openFocus('feed','${esc(item.id || item.task_id || '')}')">
      <span class="feed-icon">${icon}</span>
      <span class="feed-text">${esc(text)}</span>
      <span class="feed-time">${ts ? ago(ts) : ''}</span>
    </div>`;
  }).join('');
}

// === ORCHESTRATOR ===
function renderOrchestrator(snap) {
  if (!snap) return;

  // Goal info — use goals list or goal_board, not a non-existent goal object
  const goals = snap.goals || [];
  const goalBoard = snap.goal_board || [];
  const hasGoal = goals.length > 0 || goalBoard.length > 0;
  const goal = hasGoal ? (goals[0] || goalBoard[0]) : null;
  const title = $('orchestrator-goal-title');
  const directive = $('orchestrator-directive');
  if (title) title.textContent = goal ? (goal.title || goal.id || 'Active goal') : 'No active goal';
  if (directive) directive.textContent = goal ? (goal.directive || goal.description || 'Goal active.') : 'No goal set. Create tasks from brainstorm escalations or the CLI.';

  // Next Safe Action — use snap.next_action, not goal.next_safe_action
  const na = snap.next_action || {};
  const cmd = $('orchestrator-command');
  if (cmd) cmd.textContent = na.command || na.label || 'No actions pending';

  // Stats — use actual lane counts from tasks
  const tasks = snap.tasks || [];
  setText('orchestrator-queue', String(tasks.filter(t => t.lane === 'new' || t.lane === 'in_progress').length));
  setText('orchestrator-ready', String(tasks.filter(t => t.lane === 'ready_to_promote').length));
  setText('orchestrator-blocked', String(tasks.filter(t => t.lane === 'needs_verification').length));
  setText('orchestrator-evidence', String(snap.evidence?.length ?? 0));

  // Agent progress
  const agents = $('orchestrator-agent-progress');
  if (agents) {
    const progress = snap.worker_activity || [];
    if (progress.length === 0) {
      agents.innerHTML = '<div style="color:var(--text-muted);font-size:11px;padding:4px;">No agents running</div>';
    } else {
      agents.innerHTML = progress.slice(0, 8).map(a => `<div class="agent-row" onclick="openFocus('agent','${esc(a.worker || a.name || a.id || '')}')">
        <span class="agent-dot ${(a.state || a.status || 'waiting').toLowerCase()}"></span>
        <span class="agent-name">${esc(a.worker || a.name || a.id || 'Agent')}</span>
        <span class="agent-task">${esc(a.description || a.task || '')}</span>
        <span class="agent-time">${a.latest ? ago(a.latest) : ''}</span>
      </div>`).join('');
    }
  }

  // Health — render real metrics from the health object
  const health = $('orchestrator-health-bars');
  const snapHealth = snap.health || {};
  const hStatus = snapHealth.timeout || snapHealth.worker_failed > 0 ? 'degraded' : 'nominal';
  setText('orchestrator-health-label', hStatus === 'degraded' ? 'Degraded' : 'Nominal');
  if (health) {
    const total = snapHealth.total_tasks || 0;
    if (total === 0) {
      health.innerHTML = '<div style="color:var(--text-muted);font-size:11px;padding:4px;">No tasks</div>';
    } else {
      const metrics = [
        { name: 'Active', value: snapHealth.active_tasks || 0, max: total, status: 'good' },
        { name: 'Needs verification', value: snapHealth.needs_verification || 0, max: total, status: (snapHealth.needs_verification || 0) > 0 ? 'warn' : 'good' },
        { name: 'Ready to promote', value: snapHealth.ready_to_promote || 0, max: total, status: 'good' },
        { name: 'Promoted', value: snapHealth.promoted_tasks || 0, max: total, status: 'good' },
        { name: 'Failed', value: snapHealth.worker_failed || 0, max: total, status: (snapHealth.worker_failed || 0) > 0 ? 'bad' : 'good' },
      ];
      health.innerHTML = metrics.map(m => {
        const pct = m.max > 0 ? Math.round((m.value / m.max) * 100) : 0;
        return `<div class="health-row">
          <span class="label">${esc(m.name)} (${m.value})</span>
          <div class="bar-track"><div class="bar-fill ${m.status}" style="width:${pct}%"></div></div>
        </div>`;
      }).join('');
    }
  }
  setText('orchestrator-freshness', typeof snap.freshness === 'object' ? (snap.freshness?.status || 'ok') : (snap.freshness || 'unknown'));
  setText('orchestrator-goal-id', goal ? (goal.id || 'active') : 'none');
}

function setText(id, text) {
  const el = $(id);
  if (el) el.textContent = text;
}

// === FOCUS OVERLAY ===
function openFocus(type, id) {
  const overlay = $('focus-overlay');
  const content = $('focus-content');
  if (!overlay || !content) return;
  selectedTaskId = id;
  const task = snapshot?.tasks?.find(t => t.id === id);
  if (task) {
    const lane = task.lane || 'new';
    let actionBtns = '<button class="btn btn-secondary btn-sm" data-action="close">Close</button>';
    if (lane === 'ready_to_promote') {
      actionBtns = '<button class="btn btn-primary btn-sm" data-action="promote" data-task="' + esc(task.id) + '">Promote</button> ' + actionBtns;
    }
    if (lane === 'needs_verification') {
      actionBtns = '<button class="btn btn-primary btn-sm" data-action="verify" data-task="' + esc(task.id) + '">Run Verification</button> ' + actionBtns;
    }
    content.innerHTML = '<h2 style="margin:0 0 12px;font-size:18px;">' + esc(task.title || task.id) + '</h2>' +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px;">' +
        '<div style="padding:8px;background:var(--bg);border-radius:6px;"><span style="color:var(--text-muted);font-size:10px;">Status</span><br><strong>' + esc(lane) + '</strong></div>' +
        '<div style="padding:8px;background:var(--bg);border-radius:6px;"><span style="color:var(--text-muted);font-size:10px;">Branch</span><br><strong>' + esc(task.branch || '—') + '</strong></div>' +
        '<div style="padding:8px;background:var(--bg);border-radius:6px;"><span style="color:var(--text-muted);font-size:10px;">Worker</span><br><strong>' + esc(task.worker || '—') + '</strong></div>' +
        '<div style="padding:8px;background:var(--bg);border-radius:6px;"><span style="color:var(--text-muted);font-size:10px;">Updated</span><br><strong>' + ago(task.updated_at) + '</strong></div>' +
      '</div>' +
      (task.description ? '<p style="color:var(--text-soft);font-size:13px;">' + esc(task.description) + '</p>' : '') +
      (task.log ? '<pre style="background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:8px;font-size:11px;overflow:auto;max-height:200px;color:var(--text-soft);">' + esc(task.log) + '</pre>' : '') +
      '<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">' + actionBtns + '</div>';
  } else {
    content.innerHTML = '<h2 style="margin:0 0 8px;font-size:16px;">Item Detail</h2>' +
      '<p style="color:var(--text-soft);font-size:13px;">ID: ' + esc(id || '&mdash;') + '</p>' +
      '<button class="btn btn-secondary btn-sm" data-action="close">Close</button>';
  }
  overlay.hidden = false;
}

function closeFocus() {
  const overlay = $('focus-overlay');
  if (overlay) overlay.hidden = true;
  selectedTaskId = null;
}

// === ACTION EXECUTION ===
async function executeAction(taskId, action) {
  const phrase = 'confirmed';
  if (!confirm(`Execute "${action}" on task ${taskId}? Type "${phrase}" to confirm.`)) return;
  try {
    const resp = await fetch('/api/actions/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, action, approval_phrase: phrase }),
    });
    const payload = await resp.json();
    closeFocus();
    loadSnapshot(selectedProjectId);
  } catch(e) {
    console.error('Action failed', e);
  }
}

// === ACTION RESULT UTILITIES ===
function rememberApprovedActionResult(result) {
  const container = $('guided-action-result');
  if (!container) return;
  container.innerHTML = `<div style="background:var(--accent-soft);border:1px solid rgba(63,185,80,0.2);border-radius:6px;padding:8px 12px;font-size:12px;color:var(--accent);margin-top:8px;">
    Action done: ${esc(result?.action || 'executed')} on ${esc(result?.task_id || 'task')}
  </div>`;
  setTimeout(() => { container.innerHTML = ''; }, 5000);
}

function refreshSnapshotAfterApprovedAction(action) {
  setTimeout(() => loadSnapshot(selectedProjectId), 500);
}

// === GLOBAL FILTER ===
function setupFilter() {
  const filter = $('global-filter');
  if (!filter) return;
  filter.addEventListener('input', () => {
    const q = filter.value.toLowerCase();
    // Filter worker cards
    document.querySelectorAll('.worker-card').forEach(card => {
      const text = card.textContent.toLowerCase();
      card.style.display = text.includes(q) ? '' : 'none';
    });
    // Filter review cards
    document.querySelectorAll('.review-card').forEach(card => {
      const text = card.textContent.toLowerCase();
      card.style.display = text.includes(q) ? '' : 'none';
    });
    // Update count
    const visible = document.querySelectorAll('.worker-card:not([style*=\"none\"]), .review-card:not([style*=\"none\"]), .evidence-item:not([style*=\"none\"])').length;
    const count = $('filter-count');
    if (count) count.textContent = q ? String(visible) + ' hits' : 'All';
  });
}

// === RENDER ===
function render() {
  if (!snapshot) {
    document.querySelectorAll('[id$="-name"],[id$="-state"]').forEach(el => { if (el.id !== 'repo-name') el.textContent = '—'; });
    return;
  }
  // Top bar
  const repo = snapshot.project || {};
  setText('repo-name', repo.name || 'DevFlow');
  setText('repo-path', repo.path || '~/DevFlow');
  setText('branch-name', repo.branch || 'main');
  setText('tree-state', repo.working_tree === 'clean' ? 'Clean' : (repo.working_tree || 'Clean'));
  setText('last-sync', ago(snapshot.generated_at || repo.last_sync));

  // Pipeline
  renderPipeline();

  // Brainstorm transcript — managed by the chat form, not the snapshot.
  // The snapshot has no brainstorm_messages field, so never clobber the DOM here.

  // Worker lanes
  const tasks = snapshot.tasks || [];
  renderWorkerLanes(tasks);

  // Review queue
  renderReviewQueue(snapshot.review_loop || null);

  // Evidence stream
  const evidence = snapshot.evidence || [];
  renderEvidenceStream(evidence);

  // Mission feed
  const feed = snapshot.feed || snapshot.mission_feed || [];
  renderMissionFeed(feed);

  // Orchestrator
  renderOrchestrator(snapshot);
}

// === INIT ===
function init() {
  setupRepoSelector();
  setupModelSelector();
  setupBrainstormForm();
  setupPipelineButtons();
  setupFilter();

  // Load persisted brainstorm session
  loadBrainstormTranscript(brainstormSessionId);
  loadBrainstormSessions();

  // New session buttons
  const newBtn = $('brainstorm-new-session');
  if (newBtn) newBtn.addEventListener('click', newBrainstormSession);
  const newBtnSide = $('brainstorm-new-session-side');
  if (newBtnSide) newBtnSide.addEventListener('click', newBrainstormSession);

  // Focus overlay actions via event delegation
  const focusPanel = $('focus-panel');
  if (focusPanel) {
    focusPanel.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-action]');
      if (!btn) return;
      const action = btn.dataset.action;
      if (action === 'close') {
        closeFocus();
      } else if (action === 'promote' || action === 'verify') {
        const taskId = btn.dataset.task;
        if (taskId) executeAction(taskId, action);
      }
    });
  }

  // Keyboard: Escape closes focus
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeFocus();
  });

  // Close repo dropdown on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const dd = $('repo-dropdown');
      if (dd) dd.hidden = true;
    }
  });

  // Load snapshot
  loadSnapshot();
}

document.addEventListener('DOMContentLoaded', init);
"""