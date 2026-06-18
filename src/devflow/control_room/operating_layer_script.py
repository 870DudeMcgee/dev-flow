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
const ACTION_APPROVAL_PHRASE = 'I approve this exact Dev-Flow command';
const BRAINSTORM_DOD_PREFIX = 'devflow-brainstorm-definition-of-done:';

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
function sentenceCase(value) {
  return String(value || '').replace(/_/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase());
}
function lastTaskEvent(task) {
  const events = task?.detail?.recent_events || [];
  return events.length ? events[events.length - 1] : null;
}
function taskTimestamp(task) {
  return lastTaskEvent(task)?.timestamp || task?.updated_at || task?.created_at || '';
}
function taskFreshness(task) {
  const ts = taskTimestamp(task);
  return ts ? ago(ts) : (task?.latest || '');
}
function shortTaskLatest(item, latestEvent) {
  const value = String(item?.latest || '').trim();
  if (value && value.length <= 18 && !value.includes('/')) return value;
  const valueAgo = ago(value);
  if (valueAgo) return valueAgo;
  return latestEvent?.timestamp ? ago(latestEvent.timestamp) : '';
}
function taskWorkerLabel(task) {
  const local = task?.local_worker_lane || null;
  if (local?.profile_id || local?.model) {
    const model = local.model ? ` · ${local.model}` : '';
    return `${local.profile_id || local.worker_id || 'local model'}${model}`;
  }
  return task?.worker || 'unassigned';
}

// === BROWSER ACTION CAPABILITIES ===
function intentForCommand(command) {
  const value = String(command || '');
  if (value.includes(' task run ') && value.includes('--worker shell')) return 'start_shell';
  if (value.includes(' task verify ')) return 'verify';
  if (value.includes(' task promote-preview ')) return 'review_preview';
  if (value.includes(' task promote ')) return 'promote';
  if (value.includes(' task cleanup ') && value.includes('--preview')) return 'cleanup_preview';
  if (value.includes(' task close ')) return 'close';
  if (value.includes(' task log ')) return 'inspect_log';
  if (value.includes(' task show ')) return 'inspect';
  return 'next_safe_action';
}
function labelForIntent(intent) {
  const labels = {
    start_shell: 'Start shell',
    retry: 'Retry',
    verify: 'Verify',
    review_preview: 'Review preview',
    promote: 'Promote',
    cleanup_preview: 'Cleanup preview',
    close: 'Close',
    inspect: 'Inspect',
    inspect_log: 'Inspect log',
    next_safe_action: 'Next safe action',
  };
  return labels[intent] || sentenceCase(intent);
}
function inferredRequiredInputs(intent, command) {
  const value = String(command || '');
  if (intent === 'start_shell' || intent === 'retry' || /--\\s*<command>\\s*$/.test(value)) return ['shell_command'];
  if (intent === 'verify' || /--shell\\s+["']?<command>/.test(value)) return ['verification_command'];
  if (intent === 'close' || value.includes('<reason>')) return ['close_outcome', 'close_reason'];
  return [];
}
function normalizeCapability(raw) {
  if (!raw || !raw.command) return null;
  const intent = raw.intent || intentForCommand(raw.command);
  const requiredInputs = Array.isArray(raw.required_inputs) && raw.required_inputs.length
    ? raw.required_inputs
    : inferredRequiredInputs(intent, raw.command);
  return {
    intent,
    label: raw.label || labelForIntent(intent),
    command: raw.command,
    scope: raw.scope || 'task',
    enabled: raw.enabled !== false,
    safety_class: raw.safety_class || '',
    requires_human_approval: Boolean(raw.requires_human_approval),
    supervisor_may_auto_run: Boolean(raw.supervisor_may_auto_run),
    required_inputs: requiredInputs,
    reason: raw.reason || null,
  };
}
function taskCapabilities(task) {
  const capabilities = [];
  const seen = new Set();
  const push = (raw) => {
    const cap = normalizeCapability(raw);
    if (!cap || !cap.command) return;
    const key = `${cap.intent}\\n${cap.command}`;
    if (seen.has(key)) return;
    seen.add(key);
    capabilities.push(cap);
  };
  for (const control of task?.controls || []) push(control);
  for (const action of task?.actions || []) push({ ...action, intent: intentForCommand(action.command) });
  if (task?.next_action?.command) {
    push({ ...task.next_action, intent: intentForCommand(task.next_action.command), label: task.next_action.label || labelForIntent(intentForCommand(task.next_action.command)) });
  }
  return capabilities;
}
function taskCapability(task, intentOrLabel) {
  const needle = String(intentOrLabel || '').toLowerCase();
  const caps = taskCapabilities(task).filter(cap => cap.enabled);
  return caps.find(cap => String(cap.intent || '').toLowerCase() === needle)
    || caps.find(cap => String(cap.label || '').toLowerCase() === needle)
    || caps.find(cap => String(cap.label || '').toLowerCase().startsWith(needle))
    || null;
}
function taskCapabilityAny(task, intents) {
  for (const intent of intents || []) {
    const cap = taskCapability(task, intent);
    if (cap) return cap;
  }
  return null;
}
function taskAction(task, labelOrPrefix) {
  return taskCapability(task, labelOrPrefix);
}
function primaryTaskCapability(task) {
  const capabilities = taskCapabilities(task).filter(cap => cap.enabled);
  const nextCommand = task?.next_action?.command || '';
  return capabilities.find(cap => cap.command === nextCommand)
    || taskCapabilityAny(task, ['start_shell', 'retry', 'verify', 'review_preview', 'promote', 'cleanup_preview', 'inspect'])
    || null;
}
function primaryTaskCommand(task) {
  return primaryTaskCapability(task)?.command || task?.next_action?.command || '';
}
function commandNeedsShellInput(command, capability) {
  return Boolean(capability?.required_inputs?.includes('shell_command')) || /devflow task run .* -- .*<command>/.test(command || '');
}
function commandNeedsVerificationInput(command, capability) {
  return Boolean(capability?.required_inputs?.includes('verification_command')) || /devflow task verify .*--shell\\s+["']?<command>/.test(command || '');
}
function shellQuote(value) {
  return "'" + String(value || '').replace(/'/g, "'\\''") + "'";
}
function fillCapabilityCommand(capability, replacements) {
  let command = capability?.command || '';
  if (replacements?.shellCommand) {
    command = command.replace(/--\\s*<command>\\s*$/, `-- /bin/sh -c ${shellQuote(replacements.shellCommand)}`);
    command = command.replace('<command>', `/bin/sh -c ${shellQuote(replacements.shellCommand)}`);
  }
  if (replacements?.verificationCommand) {
    command = command.replace(/--shell\\s+["']?<command>["']?/, `--shell ${shellQuote(replacements.verificationCommand)}`);
  }
  if (replacements?.closeOutcome) {
    command = command.replace(/--outcome\\s+\\S+/, `--outcome ${shellQuote(replacements.closeOutcome)}`);
  }
  if (replacements?.closeReason) {
    command = command.replace(/--reason\\s+["']?<reason>["']?/, `--reason ${shellQuote(replacements.closeReason)}`);
  }
  return command;
}
function buildShellRunCommand(taskId, shellCommand, task) {
  const capability = taskCapabilityAny(task, ['start_shell', 'retry'])
    || { command: `devflow task run ${taskId} --worker shell -- <command>` };
  return fillCapabilityCommand(capability, { shellCommand });
}
function buildVerifyCommand(taskId, shellCommand, task) {
  const capability = taskCapability(task, 'verify') || { command: `devflow task verify ${taskId} --shell "<command>"` };
  return fillCapabilityCommand(capability, { verificationCommand: shellCommand });
}
function buildCloseCommand(taskId, outcome, reason, task) {
  const capability = taskCapability(task, 'close') || { command: `devflow task close ${taskId} --outcome evidence-only --reason "<reason>"` };
  return fillCapabilityCommand(capability, { closeOutcome: outcome, closeReason: reason });
}
function taskActionLabel(task) {
  const capability = primaryTaskCapability(task);
  const command = capability?.command || primaryTaskCommand(task);
  if (commandNeedsShellInput(command, capability)) return capability?.label || 'Start shell';
  if (commandNeedsVerificationInput(command, capability)) return capability?.label || 'Verify';
  return capability?.label || task?.next_action?.label || 'Inspect task';
}
function normalizeStatusKey(value) {
  return String(value || 'unknown').trim().toLowerCase().replace(/[\\s-]+/g, '_') || 'unknown';
}

function taskStatusInfo(value) {
  const key = normalizeStatusKey(value);
  const labels = {
    active: 'Active',
    blocked: 'Blocked',
    closed: 'Closed',
    command: 'Command',
    complete: 'Complete',
    created: 'New',
    error: 'Error',
    evidence: 'Evidence',
    failed: 'Failed',
    idle: 'Idle',
    in_progress: 'In Progress',
    log: 'Log',
    needs_review: 'Needs Review',
    needs_verification: 'Needs Verification',
    new: 'New',
    not_run: 'Not Run',
    passed: 'Passed',
    promoted: 'Promoted',
    ready_to_promote: 'Ready',
    result: 'Result',
    retry: 'Retry',
    running: 'Running',
    success: 'Success',
    timeout: 'Timeout',
    unknown: 'Unknown',
    verified: 'Verified',
    verification: 'Verification',
    verification_failed: 'Verification Failed',
    worker_failed: 'Worker Failed',
    worker_log: 'Worker Log',
  };
  let color = 'blue';
  if (key.includes('fail') || key === 'error') color = 'red';
  else if (['blocked', 'needs_review', 'needs_verification', 'retry', 'escalated', 'timeout'].includes(key)) color = 'orange';
  else if (['ready_to_promote', 'verified', 'passed', 'promoted', 'complete', 'success', 'result'].includes(key)) color = 'green';
  else if (['closed', 'idle', 'not_run', 'unknown', 'none'].includes(key)) color = 'gray';
  const tone = color === 'red' ? 'bad' : color === 'orange' ? 'warn' : color === 'green' ? 'good' : 'neutral';
  return {
    key,
    label: labels[key] || sentenceCase(key),
    color,
    tone,
    badgeClass: `task-status-badge task-tone-${color}`,
    railClass: `task-rail-${color}`,
    toneClass: `task-tone-${color}`,
  };
}

function evidenceStatusInfo(kind, text) {
  const key = normalizeStatusKey(kind);
  const value = `${key} ${normalizeStatusKey(text)}`;
  if (value.includes('fail') || value.includes('error')) return taskStatusInfo('failed');
  if (key.includes('verification')) return taskStatusInfo('verification');
  if (key.includes('result') || value.includes('success') || value.includes('passed')) return taskStatusInfo('result');
  if (key.includes('log') || key.includes('command') || key.includes('shell')) return taskStatusInfo('worker_log');
  return taskStatusInfo(key || 'evidence');
}

function statusTone(lane) {
  return taskStatusInfo(lane).tone;
}

function laneColor(lane) {
  return taskStatusInfo(lane).color;
}

function laneBadge(lane) {
  const info = taskStatusInfo(lane);
  return `<span class="lane-badge lane-${info.color} ${info.badgeClass}">${esc(info.label)}</span>`;
}

// === FIRST VIEWPORT PRESENTATION ===
function taskLookupById(tasks) {
  return new Map((tasks || []).map(t => [t.id, t]));
}

function taskCardFromSnapshotTask(task) {
  const status = task.lane || 'new';
  const latestEvent = lastTaskEvent(task);
  return {
    task_id: task.id,
    title: task.title || 'Untitled task',
    lane: status,
    display_status: task.display_status || status,
    tone: statusTone(status),
    worker_model_label: task.worker_model_label || taskWorkerLabel(task),
    verification_status: task.verification_status || 'not_run',
    latest: taskFreshness(task),
    action_label: taskActionLabel(task),
    command: primaryTaskCommand(task),
    latest_event: latestEvent,
  };
}

function reviewCardFromSnapshotTask(task) {
  const command = primaryTaskCommand(task);
  const detail = task.review_detail || {};
  const blockers = detail.blockers || task.review_blockers || task.promotion_blockers || [];
  const changedFiles = detail.changed_files || [];
  const priority = task.lane === 'ready_to_promote' || task.lane === 'failed' || task.lane === 'blocked'
    ? 'high'
    : 'medium';
  return {
    task_id: task.id,
    title: task.title || 'Untitled task',
    lane: task.lane || 'new',
    priority: detail.review_priority || priority,
    reason: detail.review_reason || blockers[0] || task.next_action?.reason || task.display_status || '',
    action_label: taskActionLabel(task),
    command: detail.review_command || command || task.review_next_command || '',
    evidence_paths: detail.evidence_paths || task.evidence_paths || task.detail?.evidence_paths || [],
    review_state: detail.review_state || task.review_state || 'not_ready',
    review_score: detail.review_score || task.review_score || 0,
    operator_summary: detail.operator_summary || '',
    blockers,
    changed_files: changedFiles,
    evidence_count: (detail.evidence_paths || task.evidence_paths || task.detail?.evidence_paths || []).length,
  };
}

function evidenceCardFromSnapshotPointer(item, taskLookup) {
  const task = taskLookup.get(item.task_id) || null;
  const path = item.path || item.verification_log_path || item.result_path || item.log_path || '';
  const command = item.command || item.verification_command || '';
  const kind = item.kind || (item.verification_log_path ? 'verification' : item.result_path ? 'result' : item.log_path ? 'worker log' : 'evidence');
  return {
    task_id: item.task_id || '',
    kind,
    text: item.text || command || path || ('task ' + (item.task_id || '?')),
    path,
    command,
    label: item.label || kind,
    timestamp: taskTimestamp(task) || item.created_at || item.timestamp || item.generated_at || '',
  };
}

function buildFirstViewportPresentation(snap) {
  const source = snap || {};
  const server = source.first_viewport || null;
  const tasks = source.tasks || [];
  const taskLookup = taskLookupById(tasks);
  const activeTasks = tasks.filter(t => t.lane !== 'closed');
  const laneRank = { failed: 0, blocked: 1, running: 2, needs_verification: 3, needs_review: 4, ready_to_promote: 5, new: 6, idle: 7 };
  const sortedActiveTasks = [...activeTasks].sort((a, b) => (laneRank[a.lane] ?? 9) - (laneRank[b.lane] ?? 9) || String(b.id).localeCompare(String(a.id)));
  const fallbackTaskId = source.focus_task_id || sortedActiveTasks[0]?.id || tasks[0]?.id || null;
  const serverLaunchpad = server?.launchpad || {};
  const selectedId = serverLaunchpad.selected_task_id || fallbackTaskId;
  const selected = taskLookup.get(selectedId) || null;
  const primary = selected ? primaryTaskCapability(selected) : null;
  const reviewTasks = tasks.filter(t => ['needs_verification', 'needs_review', 'ready_to_promote', 'failed', 'blocked'].includes(t.lane));
  const switcherIds = Array.isArray(serverLaunchpad.switcher_task_ids) && serverLaunchpad.switcher_task_ids.length
    ? serverLaunchpad.switcher_task_ids
    : (sortedActiveTasks.length ? sortedActiveTasks : tasks.slice(0, 6)).map(t => t.id);
  return {
    schema_version: server?.schema_version || 1,
    tasks,
    task_lookup: taskLookup,
    active_tasks: activeTasks,
    active_task_count: server?.active_task_count ?? activeTasks.length,
    total_task_count: server?.total_task_count ?? tasks.length,
    worker_lanes: Array.isArray(server?.worker_lanes) ? server.worker_lanes : sortedActiveTasks.map(taskCardFromSnapshotTask),
    review_queue: Array.isArray(server?.review_queue) ? server.review_queue : reviewTasks.map(reviewCardFromSnapshotTask),
    evidence_stream: Array.isArray(server?.evidence_stream)
      ? server.evidence_stream
      : (source.evidence || []).map(item => evidenceCardFromSnapshotPointer(item, taskLookup)),
    mission_feed: source.feed || source.mission_feed || [],
    review_loop: source.review_loop || null,
    launchpad: {
      selected_task_id: selected?.id || selectedId || null,
      active_task_ids: Array.isArray(serverLaunchpad.active_task_ids) ? serverLaunchpad.active_task_ids : activeTasks.map(t => t.id),
      switcher_task_ids: switcherIds,
      command: serverLaunchpad.command || primary?.command || selected?.next_action?.command || '',
      action_label: serverLaunchpad.action_label || (selected ? taskActionLabel(selected) : 'Inspect task'),
      reason: serverLaunchpad.reason || selected?.next_action?.reason || null,
    },
  };
}

function asFirstViewportPresentation(input) {
  if (input && Array.isArray(input.worker_lanes) && Array.isArray(input.review_queue)) return input;
  if (Array.isArray(input)) return buildFirstViewportPresentation({ tasks: input });
  return buildFirstViewportPresentation(input || snapshot || {});
}

function verificationBadge(status) {
  const info = taskStatusInfo(status || 'not_run');
  const s = info.key;
  const cls = s === 'passed' ? 'verify-passed' : s === 'failed' ? 'verify-failed' : 'verify-notrun';
  return `<span class="verify-badge ${cls} ${info.badgeClass}">${esc(info.label)}</span>`;
}
function parseCreatedTaskId(stdout) {
  const match = String(stdout || '').match(/Created\\s+(task-\\d+)/);
  return match ? match[1] : null;
}
function shortCommand(command, limit) {
  const value = String(command || '').replace(/\\s+/g, ' ').trim();
  if (!value) return '';
  const max = limit || 96;
  return value.length > max ? value.slice(0, max - 1) + '…' : value;
}
function pipelineDetailFromPayload(payload) {
  return payload?.pipeline_detail || {};
}
function taskActionFromPipelinePayload(payload) {
  const detail = pipelineDetailFromPayload(payload);
  return detail.task_action || payload?.action || null;
}
function implementationContextFromPipelinePayload(payload) {
  const detail = pipelineDetailFromPayload(payload);
  const context = detail.implementation_context || null;
  if (context && context.text) return context;
  if (payload?.implementation_context) {
    return {
      text: payload.implementation_context,
      source_paths: [],
      artifact_path: payload.implementation_context_path || null,
      target_path_template: '.devflow/workspaces/{task_id}/implementation-context.md',
    };
  }
  return null;
}
function brainstormDefinitionStorageKey(sessionId) {
  return BRAINSTORM_DOD_PREFIX + String(sessionId || brainstormSessionId || 'default');
}
function currentBrainstormDefinitionOfDone() {
  const input = $('brainstorm-definition-of-done');
  return String(input?.value || '').trim();
}
function loadBrainstormDefinitionOfDone() {
  const input = $('brainstorm-definition-of-done');
  if (!input) return;
  input.value = localStorage.getItem(brainstormDefinitionStorageKey()) || '';
}
function setupBrainstormDefinitionOfDone() {
  const input = $('brainstorm-definition-of-done');
  if (!input) return;
  loadBrainstormDefinitionOfDone();
  input.addEventListener('input', () => {
    localStorage.setItem(brainstormDefinitionStorageKey(), input.value);
  });
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
let currentBrowsePath = null;

async function browseDirectory(path) {
  try {
    const url = `/api/browse?path=${encodeURIComponent(path || '~')}`;
    const resp = await fetch(url);
    const data = await resp.json();
    currentBrowsePath = data.current_path;
    renderRepoBrowser(data);
  } catch(e) {
    console.error('Browse failed:', e);
  }
}

function renderRepoBrowser(data) {
  const browser = $('repo-browser');
  const pathDisplay = $('repo-current-path');
  if (!browser) return;
  if (pathDisplay) pathDisplay.textContent = data.current_path;

  let html = '';
  if (data.parent_path) {
    html += `<div class="repo-item" data-browse-path="${esc(data.parent_path)}" style="cursor:pointer;">
      <span class="repo-item-icon">↑</span>
      <div><strong>..</strong><span class="repo-path">Parent directory</span></div>
    </div>`;
  }
  for (const entry of data.entries) {
    if (!entry.is_dir) continue;
    const icon = entry.has_devflow ? '⚑' : '📁';
    const badge = entry.has_devflow ? '<span style="font-size:9px;color:var(--accent);margin-left:4px;">DevFlow</span>' : '';
    html += `<div class="repo-item" data-browse-path="${esc(entry.path)}" data-is-dir="true" style="cursor:pointer;">
      <span class="repo-item-icon">${icon}</span>
      <div>
        <strong>${esc(entry.name)}${badge}</strong>
        <span class="repo-path">${esc(entry.path)}</span>
      </div>
    </div>`;
  }
  if (!data.entries.some(e => e.is_dir)) {
    html += '<div style="padding:12px;text-align:center;color:var(--text-muted);font-size:12px;">No subdirectories</div>';
  }
  browser.innerHTML = html;

  browser.querySelectorAll('.repo-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      const browsePath = item.dataset.browsePath;
      if (!browsePath) return;
      browseDirectory(browsePath);
    });
  });
}

async function setRepoRoot(path) {
  try {
    const resp = await fetch('/api/repo/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    const data = await resp.json();
    if (data.error) {
      alert(data.error);
      return;
    }
    const nameEl = $('repo-name');
    const pathEl = $('repo-path');
    if (nameEl) nameEl.textContent = data.name || path;
    if (pathEl) pathEl.textContent = data.path || path;
    const dropdown = $('repo-dropdown');
    if (dropdown) dropdown.hidden = true;
    selectedProjectId = null;
    loadSnapshot();
    loadBrainstormTranscript(brainstormSessionId);
    loadBrainstormDefinitionOfDone();
    loadBrainstormSessions();
    refreshPipelineState();
  } catch(e) {
    alert('Failed to set repository: ' + (e.message || 'unknown error'));
  }
}

function setupRepoSelector() {
  const selector = $('repo-selector');
  const dropdown = $('repo-dropdown');
  if (!selector || !dropdown) return;
  selector.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdown.hidden = !dropdown.hidden;
    if (!dropdown.hidden && !currentBrowsePath) {
      browseDirectory('~');
    }
  });
  document.addEventListener('click', () => { dropdown.hidden = true; });
  dropdown.addEventListener('click', (e) => e.stopPropagation());

  const openBtn = $('repo-open-btn');
  const pathInput = $('repo-path-input');
  if (openBtn && pathInput) {
    const doOpen = () => {
      const p = pathInput.value.trim();
      if (p) setRepoRoot(p);
    };
    openBtn.addEventListener('click', doOpen);
    pathInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); doOpen(); }
    });
  }
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
      container.innerHTML = '<div class="brainstorm-empty-state">Start a brainstorm conversation above.</div>';
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
      hasTranscript: (data.messages || []).length > 0,
      hasSpec: data.spec != null,
      hasPlan: data.plan != null,
      hasImplementation: Boolean(data.implementation || data.pipeline?.has_implementation),
    };
    renderPipeline();
  } catch(e) {
    console.error('Failed to load transcript:', e);
  }
}

function newBrainstormSession() {
  brainstormSessionId = `browser-${Date.now().toString(36)}`;
  localStorage.setItem('devflow-brainstorm-session', brainstormSessionId);
  loadBrainstormDefinitionOfDone();
  const container = $('brainstorm-transcript');
  if (container) {
    container.innerHTML = '<div class="brainstorm-empty-state">Start a brainstorm conversation above.</div>';
  }
  pipelineState = { hasTranscript: false, hasSpec: false, hasPlan: false, hasImplementation: false };
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
      if (s.has_implementation) badges.push('<span class="si-badge">TASK</span>');
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
        loadBrainstormDefinitionOfDone();
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
  if (stage === 'implementation') {
    const definitionOfDone = currentBrainstormDefinitionOfDone();
    if (definitionOfDone) body.definition_of_done = definitionOfDone;
  }
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
    container.innerHTML = '<div class="brainstorm-empty-state">Start a brainstorm conversation above.</div>';
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
let pipelineState = { hasTranscript: false, hasSpec: false, hasPlan: false, hasImplementation: false };

async function refreshPipelineState() {
  try {
    const resp = await fetch(`/api/brainstorm/transcript?session_id=${encodeURIComponent(brainstormSessionId)}`);
    const data = await resp.json();
    pipelineState = {
      hasTranscript: (data.messages || []).length > 0,
      hasSpec: data.spec != null,
      hasPlan: data.plan != null,
      hasImplementation: Boolean(data.implementation || data.pipeline?.has_implementation),
    };
  } catch(e) { /* ignore */ }
  renderPipeline();
}

function renderPipeline() {
  const stages = [
    { id: 'brainstorm', label: 'Brainstorm', nextStage: 'spec' },
    { id: 'spec', label: 'Spec', nextStage: 'plan' },
    { id: 'plan', label: 'Plan', nextStage: null },
  ];
  // Determine completed stages based on actual artifacts
  const completed = new Set();
  if (pipelineState.hasTranscript) completed.add('brainstorm');
  if (pipelineState.hasSpec) completed.add('spec');
  if (pipelineState.hasPlan) completed.add('plan');

  // Current active stage = first not completed
  let activeStage = 'plan';
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

// Write implementation context to a task workspace via the server
async function writeTaskImplementationContext(taskId, context) {
  try {
    await fetch('/api/task/write-context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, context: context }),
    });
  } catch(e) { /* non-fatal */ }
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
          const detail = pipelineDetailFromPayload(payload);
          const taskAction = taskActionFromPipelinePayload(payload);
          if (payload.stage === 'implementation' && taskAction) {
            appendBrainstormMsg('system', detail.operator_summary || 'Creating implementation task...', {});
            try {
              const cmd = taskAction.command;
              const actionResult = await runApprovedCommand(cmd, {});
              if (actionResult.executed && actionResult.exit_code === 0) {
                const outLine = (actionResult.stdout || '').trim().split(String.fromCharCode(10))[0];
                const createdTaskId = parseCreatedTaskId(actionResult.stdout);
                const implementationContext = implementationContextFromPipelinePayload(payload);

                if (createdTaskId && implementationContext?.text) {
                  try {
                    await writeTaskImplementationContext(createdTaskId, implementationContext.text);
                  } catch(e3) {
                    console.warn('Failed to write implementation context:', e3);
                  }
                }

                const contextTarget = implementationContext?.target_path_template || '.devflow/workspaces/{task_id}/implementation-context.md';
                const nextMsg = createdTaskId
                  ? `Task created: ${outLine}. Implementation context target: ${contextTarget.replace('{task_id}', createdTaskId)}. Next: use the Next Task launchpad.`
                  : `Task created: ${outLine}`;
                appendBrainstormMsg('system', nextMsg, {});
                await loadSnapshot(selectedProjectId);
                if (createdTaskId) selectTaskInLaunchpad(createdTaskId, { focusShell: true });
              } else {
                appendBrainstormMsg('system', 'Task creation failed: ' + (actionResult.message || actionResult.stderr || 'unknown'), { kind: 'provider_error' });
              }
            } catch(e2) {
              appendBrainstormMsg('system', 'Task creation error: ' + (e2.message || 'unknown'), { kind: 'provider_error' });
            }
          } else {
            let info = `Escalated to ${stageLabel}. `;
            const modelDetail = detail.advisory_model || payload.model_info;
            if (modelDetail && modelDetail.used_model) {
              info += `Generated by ${modelDetail.model || modelDetail.profile_id}. Artifact: ${payload.artifact_path || detail.artifact_path || 'session dir'}`;
              if (payload.model_info && payload.model_info.content) {
                appendBrainstormMsg('system', info, {});
                appendBrainstormMsg('assistant', payload.model_info.content, { time: shortTime(new Date().toISOString()) });
                info = '';
              }
            } else if (modelDetail && modelDetail.error) {
              info += `Model error: ${modelDetail.error}. Artifact: ${payload.artifact_path || detail.artifact_path || 'session dir'}`;
            } else {
              info += `Artifact written to ${payload.artifact_path || detail.artifact_path || 'session dir'}.`;
            }
            if (info) appendBrainstormMsg('system', info, {});
          }
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

  // Quality-gate buttons
  document.querySelectorAll('[data-bj-quality-gate]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const stage = btn.dataset.bjQualityGate;
      if (!stage) return;
      btn.disabled = true;
      const originalText = btn.textContent;
      btn.textContent = 'QC running...';

      appendBrainstormMsg('system', `Running builder-judge quality gate for ${stage}...`, {});
      appendBrainstormMsg('assistant', '', { thinking: true });

      try {
        const body = {
          session_id: brainstormSessionId,
          stage: stage,
          builder_profile_id: selectedProfileId || undefined,
        };
        const resp = await fetch('/api/builder-judge/quality-gate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await resp.json();
        removeThinkingIndicator();

        if (!resp.ok) {
          appendBrainstormMsg('system', `QC gate failed: ${data.error || 'unknown'}`, { kind: 'provider_error' });
          return;
        }

        // Show the quality-gate result in the builder-judge panel
        renderBJRunResult(data);
        loadBuilderJudgeLoops();

        if (data.status === 'passed') {
          appendBrainstormMsg('system', `QC gate PASSED for ${stage} (score: ${data.final_score}/100). Safe to escalate.`, {});
        } else if (data.status === 'escalated') {
          appendBrainstormMsg('system', `QC gate ESCALATED for ${stage} (last score: ${data.final_score || '—'}/100). Review the draft before escalating.`, {});
        } else {
          appendBrainstormMsg('system', `QC gate: ${data.status} (score: ${data.final_score || '—'}/100).`, {});
        }
      } catch(e) {
        removeThinkingIndicator();
        appendBrainstormMsg('system', `QC gate error: ${e.message}`, { kind: 'provider_error' });
      } finally {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    });
  });
}

// === Worker lanes ===
function renderWorkerLanes(input) {
  const container = $('active-work-groups');
  if (!container) return;
  const presentation = asFirstViewportPresentation(input);
  const all = presentation.worker_lanes || [];
  const totalCount = presentation.total_task_count || 0;
  const count = $('active-work-count');
  if (count) count.textContent = (presentation.active_task_count ?? all.length) + ' active / ' + totalCount + ' total';
  if (all.length === 0) {
    container.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted);font-size:12px;">No active tasks — all ' + totalCount + ' tasks are closed</div>';
    return;
  }
  container.innerHTML = all.map(item => {
    const taskId = item.task_id || item.id || '';
    const status = item.lane || 'new';
    const info = taskStatusInfo(item.display_status || status);
    const verifyInfo = taskStatusInfo(item.verification_status || 'not_run');
    const tone = item.tone || info.tone;
    const actionLabel = item.action_label || 'Inspect task';
    const latestEvent = item.latest_event || null;
    const latest = shortTaskLatest(item, latestEvent);
    const workerLabel = item.worker_model_label || 'unassigned';
    return `<div class="worker-card guided-task-card task-card ${info.toneClass} ${info.railClass} ${esc(status)}${selectedTaskId === taskId ? ' selected' : ''}" data-task-id="${esc(taskId)}" role="listitem">
      <button class="worker-card-main" type="button" data-select-task="${esc(taskId)}">
        <span class="worker-light ${tone}"></span>
        <span class="worker-copy">
          <strong><span class="task-id">${esc(taskId)}</span> ${esc(item.title || 'Untitled task')}</strong>
          <span class="worker-meta"><span class="${info.badgeClass}">${esc(info.label)}</span><span class="worker-meta-text">${esc(workerLabel)} · ${esc(verifyInfo.label)}</span></span>
          ${latestEvent ? `<span class="worker-event">${esc(latestEvent.event)}${latestEvent.summary ? ': ' + esc(latestEvent.summary) : ''}</span>` : ''}
        </span>
      </button>
      <span class="worker-next">${esc(actionLabel)}</span>
      <span class="worker-time">${esc(latest)}</span>
      <span class="worker-actions">
        <button type="button" class="icon-btn task-row-btn" data-select-task="${esc(taskId)}" title="Select in launchpad">Select</button>
        <button type="button" class="icon-btn task-row-btn" data-inspect-task="${esc(taskId)}" title="Inspect task">Inspect</button>
      </span>
    </div>`;
  }).join('');
}

// === Review queue ===
function renderReviewQueue(reviewLoop, tasks) {
  const container = $('guided-review-queue');
  if (!container) return;
  const presentation = reviewLoop && Array.isArray(reviewLoop.review_queue)
    ? reviewLoop
    : buildFirstViewportPresentation({ review_loop: reviewLoop, tasks: tasks || [] });
  const items = presentation.review_queue || [];
  const available = items.length;
  const count = $('review-queue-count');
  if (count) count.textContent = available + ' items';
  if (available === 0) {
    const next = presentation.review_loop?.next_safe_action || '';
    container.innerHTML = '<div class="empty-panel-note">' + esc(presentation.review_loop?.headline || 'No items to review') +
      (next ? '<code>' + esc(shortCommand(next, 120)) + '</code>' : '') + '</div>';
    return;
  }
  container.innerHTML = items.slice(0, 12).map(item => {
    const taskId = item.task_id || item.id || '';
    const laneInfo = taskStatusInfo(item.lane || 'needs_review');
    const priority = item.priority || (item.lane === 'ready_to_promote' || item.lane === 'failed' || item.lane === 'blocked' ? 'high' : 'medium');
    const command = item.command || '';
    const changed = Array.isArray(item.changed_files) ? item.changed_files : [];
    const blockers = Array.isArray(item.blockers) ? item.blockers : [];
    const details = [];
    if (item.operator_summary) details.push(item.operator_summary);
    if (changed.length) details.push(changed.length + ' changed file' + (changed.length === 1 ? '' : 's'));
    if (item.evidence_count) details.push(item.evidence_count + ' evidence path' + (item.evidence_count === 1 ? '' : 's'));
    if (blockers.length) details.push(blockers[0]);
    return `<div class="review-card task-card ${laneInfo.toneClass} ${laneInfo.railClass}" data-task-id="${esc(taskId)}">
      <span class="review-priority ${priority === 'medium' ? 'med' : priority}">${esc(sentenceCase(priority))}</span>
      <button type="button" class="review-main" data-select-task="${esc(taskId)}">
        <strong>${esc(taskId)} · ${esc(item.title || 'Untitled task')} <span class="${laneInfo.badgeClass}">${esc(laneInfo.label)}</span></strong>
        <span>${esc(item.reason || 'Review task')} · ${esc(shortCommand(command || 'Inspect task', 96))}</span>
        ${details.length ? `<em>${esc(details.slice(0, 3).join(' · '))}</em>` : ''}
      </button>
      <button type="button" class="btn btn-sm btn-secondary task-row-btn" data-select-task="${esc(taskId)}">${esc(item.action_label || 'Inspect')}</button>
    </div>`;
  }).join('');
}

// === Evidence stream ===
function renderEvidenceStream(evidence, tasks) {
  const container = $('guided-evidence-stream');
  if (!container) return;
  const presentation = evidence && Array.isArray(evidence.evidence_stream)
    ? evidence
    : buildFirstViewportPresentation({ evidence: evidence || [], tasks: tasks || [] });
  const items = presentation.evidence_stream || [];
  const count = $('evidence-stream-count');
  if (count) count.textContent = items.length + ' items';
  if (items.length === 0) {
    container.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted);font-size:12px;">No evidence yet</div>';
    return;
  }
  container.innerHTML = items.slice(0, 20).map(item => {
    const taskId = item.task_id || '';
    const text = item.text || item.command || item.path || ('task ' + (taskId || '?'));
    const kind = item.kind || 'evidence';
    const evidenceInfo = evidenceStatusInfo(kind, text);
    const ts = item.timestamp || item.created_at || item.generated_at;
    const path = item.path || item.command || '';
    return `<div class="evidence-item task-card ${evidenceInfo.toneClass} ${evidenceInfo.railClass}" data-task-id="${esc(taskId)}">
      <button type="button" class="evidence-main" data-select-task="${esc(taskId)}">
        <span class="evidence-icon ${evidenceInfo.toneClass}">></span>
        <span class="evidence-copy">
          <span class="evidence-text"><strong>${esc(taskId || 'task')}</strong> <span class="${evidenceInfo.badgeClass}">${esc(evidenceInfo.label)}</span> ${esc(shortCommand(text, 110))}</span>
          ${path && path !== text ? `<span class="evidence-path">${esc(shortCommand(path, 120))}</span>` : ''}
        </span>
      </button>
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

// === NEXT TASK LAUNCHPAD ===
function selectTaskInLaunchpad(taskId, opts) {
  if (!taskId) return;
  selectedTaskId = taskId;
  renderOrchestrator(snapshot);
  document.querySelectorAll('.worker-card').forEach(card => {
    card.classList.toggle('selected', card.dataset.taskId === taskId);
  });
  const section = $('orchestrator-section');
  if (section && !opts?.silent) section.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  setTimeout(() => {
    if (opts?.focusShell) {
      const input = $('orchestrator-section')?.querySelector('[data-shell-command]');
      if (input) input.focus();
    } else if (opts?.focusVerify) {
      const input = $('orchestrator-section')?.querySelector('[data-verify-command]');
      if (input) input.focus();
    }
  }, 0);
}

function renderTaskMetadata(task) {
  const lane = task.lane || 'new';
  const local = task.local_worker_lane || {};
  const statusInfo = taskStatusInfo(task.display_status || lane);
  const verifyInfo = taskStatusInfo(task.verification_status || 'not_run');
  const worker = taskWorkerLabel(task);
  const workerShort = worker.length > 30 ? worker.slice(0, 28) + '…' : worker;
  const runtime = `${local.adapter || task.worker || '—'}${local.permission_mode ? ' · ' + local.permission_mode : ''}`;
  const primary = [
    { key: 'status', label: 'Status', html: laneBadge(lane), info: statusInfo },
    { key: 'verification', label: 'Verification', html: verificationBadge(task.verification_status), info: verifyInfo },
    { key: 'worker', label: 'Worker / model', value: workerShort, title: worker, info: taskStatusInfo('running') },
    { key: 'updated', label: 'Updated', value: taskFreshness(task) || 'unknown', info: taskStatusInfo('not_run') },
  ];
  const secondary = [
    { label: 'Workspace', value: task.workspace || '—' },
    { label: 'Runtime', value: runtime },
  ];
  const primaryHtml = primary.map(item => {
    const content = item.html || `<strong title="${esc(item.title || '')}">${esc(item.value || '—')}</strong>`;
    return `<div class="nt-meta-card nt-meta-${esc(item.key)} ${item.info.toneClass} ${item.info.railClass}"><span>${esc(item.label)}</span>${content}</div>`;
  }).join('');
  const secondaryHtml = secondary.map(item => `<span class="nt-meta-mini"><span>${esc(item.label)}</span><strong title="${esc(item.value)}">${esc(item.value)}</strong></span>`).join('');
  return `${primaryHtml}<div class="nt-meta-secondary">${secondaryHtml}</div>`;
}

function renderLatestEvidence(task) {
  const detail = task.detail || {};
  const paths = detail.evidence_paths || [];
  const preview = detail.result_preview || detail.latest_verification_line || detail.latest_worker_line || '';
  if (!paths.length && !preview) {
    return `<details class="nt-evidence-details">
      <summary><span><strong>Latest Evidence</strong><em>No task evidence yet</em></span></summary>
    </details>`;
  }
  const fileKind = (path) => {
    const lower = String(path || '').toLowerCase();
    if (lower.endsWith('.patch')) return { label: 'patch', info: taskStatusInfo('needs_review') };
    if (lower.endsWith('.json') || lower.endsWith('.jsonl')) return { label: 'json', info: taskStatusInfo('worker_log') };
    if (lower.endsWith('.md')) return { label: 'md', info: taskStatusInfo('result') };
    if (lower.endsWith('.log')) return { label: 'log', info: taskStatusInfo('worker_log') };
    return { label: 'file', info: taskStatusInfo('evidence') };
  };
  const pathsHtml = paths.length
    ? `<div class="nt-evidence-list">${paths.slice(0, 4).map(p => {
        const kind = fileKind(p);
        return `<div class="nt-evidence-item ${kind.info.toneClass} ${kind.info.railClass}"><span class="nt-evidence-icon ${kind.info.toneClass}">${esc(kind.label)}</span><code>${esc(p)}</code></div>`;
      }).join('')}</div>`
    : '';
  const countLabel = paths.length
    ? `${paths.length} evidence file${paths.length === 1 ? '' : 's'}`
    : 'Preview available';
  const summaryPath = paths[0] ? shortCommand(paths[0], 78) : shortCommand(preview, 78);
  return `<details class="nt-evidence-details">
    <summary><span><strong>Latest Evidence</strong><em>${esc(countLabel)}</em></span>${summaryPath ? `<code>${esc(summaryPath)}</code>` : ''}</summary>
    <div class="nt-evidence-body">${pathsHtml}${preview ? `<pre class="nt-evidence-preview">${esc(preview)}</pre>` : ''}</div>
  </details>`;
}

function renderPromotionControls(task) {
  const previewAction = taskCapability(task, 'review_preview');
  const promoteAction = taskCapability(task, 'promote');
  if (!previewAction && !promoteAction && task.lane !== 'ready_to_promote' && task.lane !== 'needs_review') return '';
  return `<div class="task-command-box launchpad-command-box">
    <label>Review and promotion</label>
    <textarea data-promotion-note placeholder="Promotion context for the human approval record"></textarea>
    <div class="task-action-row">
      ${previewAction ? `<button class="btn btn-sm btn-secondary" type="button" data-command="${esc(previewAction.command)}">Review preview</button>` : ''}
      ${promoteAction ? `<button class="btn btn-sm btn-primary" type="button" data-command="${esc(promoteAction.command)}">Promote</button>` : ''}
    </div>
  </div>`;
}

function renderWorkerOptions(task) {
  const capability = taskCapabilityAny(task, ['start_shell', 'retry']);
  if (!capability) return '';
  return `<div class="nt-no-workers">
    <p>${esc(capability.label || 'Shell worker')}</p>
    <code>${esc(shortCommand(capability.command, 120))}</code>
  </div>`;
}

function renderReconcileAction(task) {
  // Show reconciliation options for failed/blocked tasks
  const lane = task.lane || 'new';
  if (lane !== 'failed' && lane !== 'blocked') return '';

  const taskId = task.id;
  const retryCapability = taskCapabilityAny(task, ['retry', 'start_shell']);
  const closeCapability = taskCapability(task, 'close');
  const closeCmd = fillCapabilityCommand(
    closeCapability || { command: `devflow task close ${taskId} --outcome evidence-only --reason "<reason>"` },
    { closeOutcome: 'abandoned', closeReason: 'Worker failed, abandoning task' },
  );

  return `<div class="nt-reconcile-action task-tone-red task-rail-red">
    <div class="nt-reconcile-copy">
      <span class="nt-reconcile-label">Reconcile failed task</span>
      <span class="nt-reconcile-note">Retry through the shell control, or close it to clean up.</span>
      ${retryCapability ? `<code class="nt-reconcile-command">${esc(shortCommand(retryCapability.command, 120))}</code>` : '<span class="nt-hint">No retry control available.</span>'}
    </div>
    <button class="btn btn-sm btn-danger" type="button" data-command="${esc(closeCmd)}">
      Close as abandoned
    </button>
  </div>`;
}

function renderLaunchpadActions(task) {
  const lane = task.lane || 'new';
  const primaryCapability = primaryTaskCapability(task);
  const command = primaryCapability?.command || primaryTaskCommand(task);
  const startCapability = taskCapabilityAny(task, ['start_shell', 'retry']);
  const verifyCapability = taskCapability(task, 'verify');
  const cleanupCapability = taskCapability(task, 'cleanup_preview');
  const detail = task.detail || {};
  const evidencePaths = detail.evidence_paths || [];
  const hasImplContext = evidencePaths.some(p => p.includes('implementation-context.md'));
  const showWorkerPanel = lane === 'new' || (commandNeedsShellInput(command, primaryCapability) && lane !== 'closed');

  // If the task has implementation context, show a prominent info panel
  const implContextPanel = hasImplContext && lane !== 'closed'
    ? `<div class="task-command-box nt-primary-action nt-impl-action">
        <label>📋 Implementation plan available</label>
        <p>This task has a spec/plan from the brainstorm pipeline. Pick a worker below to start implementing.</p>
      </div>`
    : '';

  // Worker selection panel — this is the primary action for new tasks
  const workerPanel = showWorkerPanel
    ? `<div class="task-command-box nt-primary-action" id="next-task-shell-panel">
        <label>Start work on ${esc(task.id)}</label>
        <div class="nt-worker-options">
          ${renderWorkerOptions(task)}
        </div>
        <div class="nt-shell-fallback">
          <details open>
            <summary>Or run a raw shell command</summary>
            <div class="inline-command-row">
              <input type="text" data-shell-command placeholder="pytest tests/test_target.py -q">
              <button class="btn btn-secondary btn-sm" type="button" data-task-run-shell="${esc(task.id)}">▶ Run shell</button>
            </div>
            <code>${esc(startCapability?.command || command || `devflow task run ${task.id} --worker shell -- <command>`)}</code>
          </details>
        </div>
      </div>`
    : '';

  const verifyPanel = (lane === 'needs_verification' || commandNeedsVerificationInput(command, verifyCapability || primaryCapability))
    ? `<div class="task-command-box nt-primary-action nt-verify-action" id="next-task-verify-panel">
        <label>Verify task</label>
        <div class="inline-command-row">
          <input type="text" data-verify-command placeholder="git diff --check && pytest -q">
          <button class="btn btn-primary btn-sm" type="button" data-task-verify="${esc(task.id)}">✓ Verify</button>
        </div>
      </div>`
    : '';
  const promotionPanel = renderPromotionControls(task);
  const reconcilePanel = renderReconcileAction(task);
  const closePanel = lane !== 'closed'
    ? `<details class="nt-close-details"><summary><span>Close task</span></summary>
        <div class="nt-close-inner">
          <select data-close-outcome>
            <option value="duplicate">duplicate</option>
            <option value="abandoned">abandoned</option>
            <option value="rejected">rejected</option>
            <option value="evidence-only">evidence-only</option>
          </select>
          <input type="text" data-close-reason placeholder="Reason required">
          <button class="btn btn-sm btn-danger" type="button" data-task-close="${esc(task.id)}">Close</button>
        </div>
      </details>`
    : `<div class="task-action-row"><button class="btn btn-sm btn-secondary" type="button" data-command="${esc(cleanupCapability?.command || `devflow task cleanup ${task.id} --preview`)}">Cleanup preview</button></div>`;
  const utilityButtons = `<details class="nt-more-actions">
    <summary><span>More actions</span></summary>
    <div class="nt-utility-row">
      <button class="btn btn-sm btn-secondary" type="button" data-inspect-task="${esc(task.id)}">Inspect</button>
      ${taskCommandButtons(task)}
    </div>
  </details>`;
  return workerPanel || verifyPanel || promotionPanel || implContextPanel || reconcilePanel
    ? `${implContextPanel}${workerPanel}${reconcilePanel}${verifyPanel}${promotionPanel}${utilityButtons}${closePanel}`
    : `${utilityButtons}${closePanel}`;
}

function renderOrchestrator(snap, presentation) {
  if (!snap) return;

  const firstViewport = presentation || buildFirstViewportPresentation(snap);
  const tasks = snap.tasks || [];
  const activeTasks = tasks.filter(t => t.lane !== 'closed');
  const launchpad = firstViewport.launchpad || {};
  const fallbackTaskId = launchpad.selected_task_id || snap.focus_task_id || activeTasks[0]?.id || tasks[0]?.id || null;
  const selected = tasks.find(t => t.id === selectedTaskId) || tasks.find(t => t.id === fallbackTaskId) || null;
  selectedTaskId = selected?.id || null;

  const title = $('orchestrator-goal-title');
  const directive = $('orchestrator-directive');
  const meta = $('next-task-meta');
  const done = $('next-task-definition-of-done');
  const doneWrap = done?.closest('.next-task-definition');
  const actionSlot = $('next-task-action-slot');
  const latestEvidence = $('next-task-latest-evidence');
  const switcher = $('orchestrator-agent-progress');
  const cmd = $('orchestrator-command');

  if (!selected) {
    if (title) title.innerHTML = 'No task selected';
    if (directive) directive.textContent = 'Create a task from Brainstorm or the CLI to start work.';
    if (meta) meta.innerHTML = '';
    if (done) done.textContent = 'No definition captured yet.';
    if (doneWrap) doneWrap.hidden = true;
    if (cmd) cmd.textContent = snap.next_action?.command || snap.next_action?.label || 'No actions pending';
    if (actionSlot) actionSlot.innerHTML = '';
    if (latestEvidence) latestEvidence.innerHTML = '<div class="next-task-evidence-empty">No evidence yet.</div>';
    if (switcher) {
      const switcherWrap = switcher.closest('.next-task-switcher-wrap');
      if (switcherWrap) switcherWrap.hidden = true;
      switcher.innerHTML = '<div style="color:var(--text-muted);font-size:11px;padding:4px;">No active tasks</div>';
    }
  } else {
    const lane = selected.lane || 'new';
    const command = selected.id === launchpad.selected_task_id
      ? (launchpad.command || primaryTaskCommand(selected))
      : primaryTaskCommand(selected);
    if (title) title.innerHTML = `<span class="nt-task-id">${esc(selected.id)}</span><span class="nt-task-title">${esc(selected.title || 'Untitled task')}</span>`;
    if (directive) {
      const reason = selected.id === launchpad.selected_task_id ? launchpad.reason : selected.next_action?.reason;
      directive.innerHTML = `${laneBadge(lane)} <span class="nt-worker-info">${esc(taskWorkerLabel(selected))}</span>${reason ? ` <span class="nt-reason">· ${esc(reason)}</span>` : ''}`;
    }
    if (meta) meta.innerHTML = renderTaskMetadata(selected);
    if (done) done.textContent = selected.definition_of_done || 'No definition captured yet.';
    if (doneWrap) doneWrap.hidden = !selected.definition_of_done;
    if (cmd) cmd.textContent = command || 'No action pending';
    if (actionSlot) actionSlot.innerHTML = renderLaunchpadActions(selected);
    if (latestEvidence) latestEvidence.innerHTML = renderLatestEvidence(selected);
    if (switcher) {
      const switchTasks = (launchpad.switcher_task_ids || [])
        .map(id => tasks.find(t => t.id === id))
        .filter(Boolean);
      const visibleSwitchTasks = switchTasks.length ? switchTasks : (activeTasks.length ? activeTasks : tasks.slice(0, 6));
      const switcherWrap = switcher.closest('.next-task-switcher-wrap');
      if (switcherWrap) switcherWrap.hidden = visibleSwitchTasks.length <= 1;
      switcher.innerHTML = visibleSwitchTasks.map(t => {
        const isSelected = t.id === selected.id;
        const tLane = t.lane || 'new';
        const info = taskStatusInfo(t.display_status || tLane);
        return `<button type="button" class="task-switcher-row task-card ${info.toneClass} ${info.railClass}${isSelected ? ' selected' : ''}" data-select-task="${esc(t.id)}">
          <span class="worker-light ${info.tone}"></span>
          <span><strong>${esc(t.id)}</strong>${esc(t.title || 'Untitled task')}</span>
          <em class="${info.badgeClass}">${esc(info.label)}</em>
        </button>`;
      }).join('');
    }
  }

  document.querySelectorAll('.worker-card').forEach(card => {
    card.classList.toggle('selected', card.dataset.taskId === selectedTaskId);
  });

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
  setText('orchestrator-goal-id', snap.focus_goal_id || (activeTasks.length ? `${activeTasks.length} tasks` : 'none'));
}

function renderFirstViewport(presentation) {
  renderPipeline();
  renderWorkerLanes(presentation);
  renderReviewQueue(presentation);
  renderEvidenceStream(presentation);
  renderMissionFeed(presentation.mission_feed || []);
  renderOrchestrator(snapshot, presentation);
}

function setText(id, text) {
  const el = $(id);
  if (el) el.textContent = text;
}

// === FOCUS OVERLAY ===
function taskCommandButtons(task) {
  const commands = [];
  const seen = new Set();
  for (const action of taskCapabilities(task)) {
    if (!action.command || action.command.includes('<command>')) continue;
    if ((action.required_inputs || []).length > 0 || action.command.includes('<reason>')) continue;
    if (seen.has(action.command)) continue;
    seen.add(action.command);
    commands.push(`<button class="btn btn-sm ${action.requires_human_approval ? 'btn-primary' : 'btn-secondary'}" type="button" data-command="${esc(action.command)}">${esc(action.label || 'Run command')}</button>`);
  }
  if (task.lane === 'closed' && !commands.some(command => command.includes('cleanup'))) {
    const cleanupCommand = taskCapability(task, 'cleanup_preview')?.command || `devflow task cleanup ${task.id} --preview`;
    commands.push(`<button class="btn btn-sm btn-secondary" type="button" data-command="${esc(cleanupCommand)}">Cleanup preview</button>`);
  }
  return commands.join(' ');
}

function openFocus(type, id, opts) {
  const overlay = $('focus-overlay');
  const content = $('focus-content');
  if (!overlay || !content) return;
  selectedTaskId = id;
  const task = snapshot?.tasks?.find(t => t.id === id);
  if (task) {
    const lane = task.lane || 'new';
    const primaryCapability = primaryTaskCapability(task);
    const command = primaryCapability?.command || primaryTaskCommand(task);
    const startCapability = taskCapabilityAny(task, ['start_shell', 'retry']);
    const verifyCapability = taskCapability(task, 'verify');
    const detail = task.detail || {};
    const local = task.local_worker_lane || {};
    const events = detail.recent_events || [];
    const evidencePaths = detail.evidence_paths || [];
    const shellPanel = commandNeedsShellInput(command, startCapability || primaryCapability) && lane !== 'closed'
      ? `<div class="task-command-box" id="focus-shell-panel">
          <label>Shell command to run in ${esc(task.id)} workspace</label>
          <div class="inline-command-row">
            <input type="text" data-shell-command placeholder="pytest tests/test_target.py -q">
            <button class="btn btn-primary btn-sm" type="button" data-task-run-shell="${esc(task.id)}">Start shell</button>
          </div>
          <code>${esc(startCapability?.command || command)}</code>
        </div>`
      : '';
    const verifyPanel = (lane === 'needs_verification' || commandNeedsVerificationInput(command, verifyCapability || primaryCapability))
      ? `<div class="task-command-box" id="focus-verify-panel">
          <label>Verification shell command</label>
          <div class="inline-command-row">
            <input type="text" data-verify-command placeholder="git diff --check && pytest -q">
            <button class="btn btn-primary btn-sm" type="button" data-task-verify="${esc(task.id)}">Verify</button>
          </div>
        </div>`
      : '';
    const promotePanel = lane === 'ready_to_promote'
      ? `<div class="task-command-box">
          <label>Promotion context</label>
          <textarea data-promotion-note placeholder="Why is this safe to promote?"></textarea>
        </div>`
      : '';
    const closePanel = lane !== 'closed'
      ? `<div class="task-command-box">
          <label>Close task</label>
          <div class="inline-command-row">
            <select data-close-outcome>
              <option value="duplicate">duplicate</option>
              <option value="abandoned">abandoned</option>
              <option value="rejected">rejected</option>
              <option value="evidence-only">evidence-only</option>
            </select>
            <input type="text" data-close-reason placeholder="Reason required">
            <button class="btn btn-secondary btn-sm" type="button" data-task-close="${esc(task.id)}">Close</button>
          </div>
        </div>`
      : '';
    const statusInfo = taskStatusInfo(task.display_status || lane);
    const verifyInfo = taskStatusInfo(task.verification_status || 'not_run');
    content.innerHTML = `<div class="focus-task-head">
        <span class="focus-task-id">${esc(task.id)}</span>
        <h2>${esc(task.title || task.id)}</h2>
        <span class="focus-status ${statusInfo.badgeClass}">${esc(statusInfo.label)}</span>
      </div>
      <div class="focus-grid">
        <div class="${statusInfo.toneClass} ${statusInfo.railClass}"><span>Status</span>${laneBadge(lane)}</div>
        <div><span>Worker / model</span><strong>${esc(taskWorkerLabel(task))}</strong></div>
        <div class="${verifyInfo.toneClass} ${verifyInfo.railClass}"><span>Verification</span>${verificationBadge(task.verification_status)}</div>
        <div><span>Updated</span><strong>${esc(taskFreshness(task) || 'unknown')}</strong></div>
        <div><span>Workspace</span><strong>${esc(task.workspace || '—')}</strong></div>
        <div><span>Runtime</span><strong>${esc(local.adapter || task.worker || '—')}${local.permission_mode ? ' · ' + esc(local.permission_mode) : ''}</strong></div>
      </div>
      <div class="task-command-box">
        <label>Next safe action</label>
        <code>${esc(command || 'No action pending')}</code>
        ${task.next_action?.reason ? `<p>${esc(task.next_action.reason)}</p>` : ''}
      </div>
      ${shellPanel}${verifyPanel}${promotePanel}
      <div class="task-action-row">${taskCommandButtons(task)}</div>
      ${closePanel}
      ${(task.review_blockers || []).length || (task.promotion_blockers || []).length ? `<div class="focus-section"><h3>Blockers</h3>
        <ul>${[...(task.review_blockers || []), ...(task.promotion_blockers || [])].slice(0, 8).map(b => `<li>${esc(b)}</li>`).join('')}</ul>
      </div>` : ''}
      ${events.length ? `<div class="focus-section"><h3>Recent events</h3>
        ${events.slice().reverse().map(ev => `<div class="event-row"><span>${esc(shortTime(ev.timestamp))}</span><strong>${esc(ev.event)}</strong><em>${esc(ev.summary || '')}</em></div>`).join('')}
      </div>` : ''}
      ${evidencePaths.length ? `<div class="focus-section"><h3>Evidence paths</h3>
        ${evidencePaths.slice(0, 10).map(path => `<code class="path-line">${esc(path)}</code>`).join('')}
      </div>` : ''}
      ${detail.latest_worker_line || detail.latest_verification_line || detail.result_preview ? `<div class="focus-section"><h3>Latest output</h3>
        <pre>${esc(detail.result_preview || detail.latest_verification_line || detail.latest_worker_line || '')}</pre>
      </div>` : ''}
      <div id="focus-command-output"></div>`;
  } else {
    content.innerHTML = '<h2 style="margin:0 0 8px;font-size:16px;">Item Detail</h2>' +
      '<p style="color:var(--text-soft);font-size:13px;">ID: ' + esc(id || '&mdash;') + '</p>' +
      '<button class="btn btn-secondary btn-sm" data-action="close">Close</button>';
  }
  overlay.hidden = false;
  if (opts?.focusShell) {
    const input = content.querySelector('[data-shell-command]');
    if (input) input.focus();
  } else if (opts?.focusVerify) {
    const input = content.querySelector('[data-verify-command]');
    if (input) input.focus();
  }
}

function closeFocus() {
  const overlay = $('focus-overlay');
  if (overlay) overlay.hidden = true;
}

// === ACTION EXECUTION ===
function actionResultHtml(result, command) {
  const exitText = result?.timed_out ? 'Timed out' : `Exit ${result?.exit_code ?? 'n/a'}`;
  const statusClass = result?.executed && result?.exit_code === 0 ? 'good' : 'bad';
  const stdout = result?.stdout ? `<pre>${esc(result.stdout)}</pre>` : '';
  const stderr = result?.stderr ? `<pre class="stderr">${esc(result.stderr)}</pre>` : '';
  const message = result?.message || result?.error || '';
  return `<div class="command-result ${statusClass}">
    <div class="command-result-head">
      <strong>${esc(exitText)}</strong>
      <code>${esc(shortCommand(command, 140))}</code>
    </div>
    ${message ? `<p>${esc(message)}</p>` : ''}
    ${stdout}${stderr}
  </div>`;
}

function renderActionPending(command) {
  const html = `<div class="command-result pending">
    <div class="command-result-head"><strong>Running</strong><code>${esc(shortCommand(command, 140))}</code></div>
  </div>`;
  const container = $('guided-action-result');
  if (container) container.innerHTML = html;
  const launchpadOutput = $('next-task-command-output');
  if (launchpadOutput) launchpadOutput.innerHTML = html;
  const focusOutput = $('focus-command-output');
  if (focusOutput) focusOutput.innerHTML = html;
}

function renderActionResult(result, command) {
  const html = actionResultHtml(result, command);
  const container = $('guided-action-result');
  if (container) container.innerHTML = html;
  const launchpadOutput = $('next-task-command-output');
  if (launchpadOutput) launchpadOutput.innerHTML = html;
  const focusOutput = $('focus-command-output');
  if (focusOutput) focusOutput.innerHTML = html;
}

async function runApprovedCommand(command, opts) {
  if (!command || command.includes('<command>')) {
    throw new Error('This action needs a concrete shell command first.');
  }
  renderActionPending(command);
  const body = {
    command,
    human_approved: true,
    approval_phrase: ACTION_APPROVAL_PHRASE,
    approved_command: command,
  };
  if (selectedProjectId) body.project = selectedProjectId;
  if (opts?.contextNote) body.context_note = opts.contextNote;
  const resp = await fetch('/api/actions/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await resp.json();
  renderActionResult(payload, command);
  setTimeout(() => loadSnapshot(selectedProjectId), 500);
  return payload;
}

async function executeAction(taskId, action) {
  const task = snapshot?.tasks?.find(t => t.id === taskId);
  if (!task) return;
  const command = typeof action === 'string' && action.startsWith('devflow ')
    ? action
    : (taskCapability(task, action)?.command || primaryTaskCommand(task));
  try {
    await runApprovedCommand(command, {});
  } catch(e) {
    renderActionResult({ executed: false, exit_code: null, error: e.message || 'Action failed' }, command);
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

function setupTaskSurfaceActions() {
  const closeButton = $('focus-close');
  if (closeButton) closeButton.addEventListener('click', closeFocus);

  document.addEventListener('click', async (e) => {
    const selectButton = e.target.closest('[data-select-task]');
    if (selectButton) {
      e.preventDefault();
      e.stopPropagation();
      const id = selectButton.dataset.selectTask;
      if (id) selectTaskInLaunchpad(id);
      return;
    }

    const inspectButton = e.target.closest('[data-inspect-task]');
    if (inspectButton) {
      e.preventDefault();
      e.stopPropagation();
      const id = inspectButton.dataset.inspectTask;
      if (id) openFocus('task', id, {});
      return;
    }

    const shellButton = e.target.closest('[data-task-run-shell]');
    if (shellButton) {
      e.preventDefault();
      const taskId = shellButton.dataset.taskRunShell;
      const task = snapshot?.tasks?.find(t => t.id === taskId);
      const input = shellButton.closest('.task-command-box')?.querySelector('[data-shell-command]')
        || document.querySelector('[data-shell-command]');
      const shellCommand = (input?.value || '').trim();
      if (!shellCommand) {
        renderActionResult({ executed: false, exit_code: null, error: 'Enter the shell command to run in the task workspace.' }, `devflow task run ${taskId}`);
        input?.focus();
        return;
      }
      try {
        await runApprovedCommand(buildShellRunCommand(taskId, shellCommand, task), {});
      } catch(err) {
        renderActionResult({ executed: false, exit_code: null, error: err.message || 'Shell run failed' }, `devflow task run ${taskId}`);
      }
      return;
    }

    const verifyButton = e.target.closest('[data-task-verify]');
    if (verifyButton) {
      e.preventDefault();
      const taskId = verifyButton.dataset.taskVerify;
      const task = snapshot?.tasks?.find(t => t.id === taskId);
      const input = verifyButton.closest('.task-command-box')?.querySelector('[data-verify-command]')
        || document.querySelector('[data-verify-command]');
      const verifyCommand = (input?.value || '').trim();
      if (!verifyCommand) {
        renderActionResult({ executed: false, exit_code: null, error: 'Enter the verification shell command.' }, `devflow task verify ${taskId}`);
        input?.focus();
        return;
      }
      try {
        await runApprovedCommand(buildVerifyCommand(taskId, verifyCommand, task), {});
      } catch(err) {
        renderActionResult({ executed: false, exit_code: null, error: err.message || 'Verification failed' }, `devflow task verify ${taskId}`);
      }
      return;
    }

    const closeTaskButton = e.target.closest('[data-task-close]');
    if (closeTaskButton) {
      e.preventDefault();
      const taskId = closeTaskButton.dataset.taskClose;
      const task = snapshot?.tasks?.find(t => t.id === taskId);
      const box = closeTaskButton.closest('.task-command-box');
      const outcome = box?.querySelector('[data-close-outcome]')?.value || document.querySelector('[data-close-outcome]')?.value || 'abandoned';
      const reasonInput = box?.querySelector('[data-close-reason]') || document.querySelector('[data-close-reason]');
      const reason = (reasonInput?.value || '').trim();
      if (reason.length < 3) {
        renderActionResult({ executed: false, exit_code: null, error: 'Enter a concrete close reason.' }, `devflow task close ${taskId}`);
        reasonInput?.focus();
        return;
      }
      try {
        await runApprovedCommand(buildCloseCommand(taskId, outcome, reason, task), {});
      } catch(err) {
        renderActionResult({ executed: false, exit_code: null, error: err.message || 'Close failed' }, `devflow task close ${taskId}`);
      }
      return;
    }

    const commandButton = e.target.closest('[data-command]');

    if (commandButton) {
      e.preventDefault();
      const command = commandButton.dataset.command || '';
      const note = command.includes('devflow task promote ')
        ? ((commandButton.closest('.task-command-box')?.querySelector('[data-promotion-note]') || document.querySelector('[data-promotion-note]'))?.value || '').trim()
        : '';
      try {
        await runApprovedCommand(command, { contextNote: note });
      } catch(err) {
        renderActionResult({ executed: false, exit_code: null, error: err.message || 'Command failed' }, command);
      }
    }
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

  // Brainstorm transcript is managed by the chat form, not the snapshot.
  // The first viewport consumes renderable presentation slices with snapshot fallbacks.
  renderFirstViewport(buildFirstViewportPresentation(snapshot));
}

// === INIT ===
// === BUILDER-JUDGE LOOP ===
function setupBuilderJudge() {
  populateBJModelSelectors();
  loadBuilderJudgeLoops();

  const runBtn = $('bj-run-btn');
  if (runBtn) runBtn.addEventListener('click', runBuilderJudgeLoop);

  const refreshBtn = $('bj-refresh-list');
  if (refreshBtn) refreshBtn.addEventListener('click', loadBuilderJudgeLoops);
}

function populateBJModelSelectors() {
  const builderSel = $('bj-builder-model');
  const judgeSel = $('bj-judge-model');
  if (!builderSel || !judgeSel) return;

  // Use availableAgents (populated from /api/agents)
  const agents = availableAgents || [];
  const advisoryAgents = agents.filter(a =>
    a.adapter === 'openai_compatible' || a.adapter === 'ollama_chat'
  );

  const optionsHtml = advisoryAgents.length
    ? advisoryAgents.map(a => `<option value="${esc(a.id)}">${esc(a.label || a.id)} — ${esc(a.model || '')}</option>`).join('')
    : '<option value="deepseek-v4-flash-free-brainstormer">DeepSeek V4 Flash Free</option>';

  builderSel.innerHTML = optionsHtml;
  judgeSel.innerHTML = advisoryAgents.length
    ? advisoryAgents.map(a => `<option value="${esc(a.id)}">${esc(a.label || a.id)} — ${esc(a.model || '')}</option>`).join('')
    : '<option value="glm-5-2-brainstormer">GLM 5.2</option>';

  // Default selections
  builderSel.value = 'deepseek-v4-flash-free-brainstormer';
  judgeSel.value = 'glm-5-2-brainstormer';
}

function setBJStatus(text, cls) {
  const badge = $('bj-status-badge');
  if (!badge) return;
  badge.textContent = text;
  badge.className = 'status-badge ' + (cls || 'online');
}

async function runBuilderJudgeLoop() {
  const dod = ($('bj-definition-of-done')?.value || '').trim();
  if (!dod) {
    setBJStatus('Error', 'warn');
    alert('Definition of Done is required — this is the bar.');
    return;
  }

  const startingPoint = ($('bj-starting-point')?.value || '').trim();
  const builderModel = $('bj-builder-model')?.value || '';
  const judgeModel = $('bj-judge-model')?.value || '';
  const passThreshold = parseInt($('bj-pass-threshold')?.value || '85', 10);
  const maxRounds = parseInt($('bj-max-rounds')?.value || '5', 10);
  const escalate = $('bj-escalate')?.checked ?? true;

  if (builderModel === judgeModel) {
    setBJStatus('Error', 'warn');
    alert('Builder and Judge must be different models. The adversarial gap is the whole point.');
    return;
  }

  const runBtn = $('bj-run-btn');
  if (runBtn) { runBtn.disabled = true; runBtn.textContent = '⏳ Running...'; }
  setBJStatus('Running...', 'warn');

  // Show progress area
  const progressArea = $('bj-progress-area');
  const resultArea = $('bj-result-area');
  const roundsList = $('bj-rounds-list');
  if (progressArea) progressArea.hidden = false;
  if (resultArea) resultArea.hidden = true;
  if (roundsList) roundsList.innerHTML = '<div class="bj-running-msg">Builder writing draft, judge grading... walk away, come back to the result.</div>';

  const body = {
    definition_of_done: dod,
    starting_point: startingPoint || undefined,
    builder_profile_id: builderModel,
    judge_profile_id: judgeModel,
    pass_threshold: passThreshold,
    max_rounds: maxRounds,
    escalate_on_max_rounds: escalate,
    async: true,
  };

  try {
    const resp = await fetch('/api/builder-judge/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await resp.json();

    if (!resp.ok) {
      setBJStatus('Failed', 'warn');
      if (roundsList) roundsList.innerHTML = `<div class="bj-error-msg">${esc(data.error || 'Unknown error')}</div>`;
      return;
    }

    // Poll for updates
    const loopId = data.loop_id;
    await pollBuilderJudgeLoop(loopId);
  } catch(e) {
    setBJStatus('Error', 'warn');
    if (roundsList) roundsList.innerHTML = `<div class="bj-error-msg">Request failed: ${esc(e.message)}</div>`;
  } finally {
    if (runBtn) { runBtn.disabled = false; runBtn.textContent = '▶ Run Loop'; }
  }
}

async function pollBuilderJudgeLoop(loopId) {
  const pollInterval = 3000; // 3 seconds
  const maxPollTime = 600000; // 10 minutes max
  const startTime = Date.now();

  while (true) {
    try {
      const resp = await fetch(`/api/builder-judge/status?loop_id=${encodeURIComponent(loopId)}`);
      const data = await resp.json();

      if (data.status && data.status !== 'running') {
        // Loop finished
        renderBJRunResult(data);
        loadBuilderJudgeLoops();
        return;
      }

      // Still running — render partial progress
      if (data.rounds && data.rounds.length > 0) {
        renderBJRunResult(data);
      }
    } catch(e) { /* ignore poll errors */ }

    if (Date.now() - startTime > maxPollTime) {
      setBJStatus('Timeout', 'warn');
      const roundsList = $('bj-rounds-list');
      if (roundsList) roundsList.innerHTML += '<div class="bj-error-msg">Polling timed out after 10 minutes. Check status manually.</div>';
      return;
    }

    await new Promise(resolve => setTimeout(resolve, pollInterval));
  }
}

function renderBJRunResult(run) {
  const progressArea = $('bj-progress-area');
  const resultArea = $('bj-result-area');
  const roundsList = $('bj-rounds-list');
  const roundSummary = $('bj-round-summary');

  // Render rounds
  const rounds = run.rounds || [];
  if (roundSummary) {
    const scores = rounds.filter(r => r.score != null).map(r => r.score);
    const scoreLine = scores.length ? scores.join(' → ') : '—';
    roundSummary.textContent = `${rounds.length} round(s) · scores: ${scoreLine}`;
  }

  if (roundsList) {
    roundsList.innerHTML = rounds.map(r => {
      const scoreClass = r.score == null ? 'bj-score-unknown' :
        r.score >= (run.config?.pass_threshold || 85) ? 'bj-score-pass' :
        r.score >= 70 ? 'bj-score-warn' : 'bj-score-fail';
      const scoreText = r.score != null ? `${r.score}/100` : 'N/A';
      const issuesHtml = (r.issues || []).length
        ? `<ul class="bj-issues">${r.issues.map(i => `<li>${esc(i)}</li>`).join('')}</ul>`
        : '';
      const passBadge = r.passed ? '<span class="bj-passed-badge">PASSED</span>' : '';
      const errorHtml = r.error ? `<div class="bj-round-error">${esc(r.error)}</div>` : '';

      return `
        <div class="bj-round-card ${scoreClass}">
          <div class="bj-round-header">
            <span class="bj-round-num">Round ${r.round_number}</span>
            <span class="bj-round-score">${scoreText}</span>
            ${passBadge}
          </div>
          <div class="bj-round-models">
            <span>Builder: ${esc(r.builder_model || r.builder_profile_id)}</span>
            <span>Judge: ${esc(r.judge_model || r.judge_profile_id)}</span>
          </div>
          ${r.judge_feedback ? `<div class="bj-judge-feedback">${esc(r.judge_feedback)}</div>` : ''}
          ${issuesHtml}
          ${errorHtml}
        </div>
      `;
    }).join('');
  }

  // Render result
  const statusMap = {
    passed: { label: 'PASSED', cls: 'online' },
    max_rounds: { label: 'MAX ROUNDS', cls: 'warn' },
    escalated: { label: 'ESCALATED', cls: 'warn' },
    failed: { label: 'FAILED', cls: 'warn' },
    running: { label: 'RUNNING', cls: 'warn' },
  };
  const statusInfo = statusMap[run.status] || { label: run.status, cls: 'warn' };
  setBJStatus(statusInfo.label, statusInfo.cls);

  if (run.final_draft || run.status === 'passed' || run.status === 'max_rounds' || run.status === 'escalated') {
    if (resultArea) resultArea.hidden = false;
    const scoreBadge = $('bj-final-score');
    if (scoreBadge) {
      scoreBadge.textContent = run.final_score != null ? `${run.final_score}/100` : '—';
      scoreBadge.className = 'bj-score-badge ' + (run.status === 'passed' ? 'bj-score-pass' : 'bj-score-warn');
    }
    const draftEl = $('bj-final-draft');
    if (draftEl && run.final_draft) {
      draftEl.innerHTML = `<pre class="bj-draft-pre">${esc(run.final_draft)}</pre>`;
    }
    const stopEl = $('bj-stop-reason');
    if (stopEl) stopEl.textContent = run.stop_reason || '';
    const nextEl = $('bj-next-action');
    if (nextEl) nextEl.textContent = run.next_safe_action || '';
  }
}

async function loadBuilderJudgeLoops() {
  const container = $('bj-loops-list');
  if (!container) return;
  try {
    const resp = await fetch('/api/builder-judge/list');
    const data = await resp.json();
    const loops = data.loops || [];
    if (!loops.length) {
      container.innerHTML = '<div class="bj-empty-state">No loops yet. Set the bar and run one.</div>';
      return;
    }
    container.innerHTML = loops.slice(0, 10).map(loop => {
      const statusCls = loop.status === 'passed' ? 'bj-status-pass' :
        loop.status === 'escalated' ? 'bj-status-escalate' :
        loop.status === 'failed' ? 'bj-status-fail' : 'bj-status-other';
      const score = loop.final_score != null ? `${loop.final_score}/100` : '—';
      const dodPreview = (loop.definition_of_done || '').substring(0, 80);
      return `
        <div class="bj-loop-item" data-bj-loop-id="${esc(loop.loop_id)}">
          <div class="bj-loop-item-header">
            <span class="bj-loop-status ${statusCls}">${esc(loop.status)}</span>
            <span class="bj-loop-score">${score}</span>
            <span class="bj-loop-rounds">${loop.rounds_completed} round(s)</span>
          </div>
          <div class="bj-loop-dod">${esc(dodPreview)}${dodPreview.length >= 80 ? '...' : ''}</div>
          <div class="bj-loop-models">
            <span>B: ${esc(loop.builder_profile_id)}</span>
            <span>J: ${esc(loop.judge_profile_id)}</span>
          </div>
        </div>
      `;
    }).join('');

    // Click to view full run
    container.querySelectorAll('[data-bj-loop-id]').forEach(el => {
      el.addEventListener('click', async () => {
        const loopId = el.dataset.bjLoopId;
        try {
          const resp = await fetch(`/api/builder-judge/status?loop_id=${encodeURIComponent(loopId)}`);
          const data = await resp.json();
          if (resp.ok) renderBJRunResult(data);
        } catch(e) { /* ignore */ }
      });
    });
  } catch(e) {
    container.innerHTML = '<div class="bj-empty-state">Failed to load loops.</div>';
  }
}

function init() {
  setupRepoSelector();
  setupModelSelector();
  setupBrainstormForm();
  setupBrainstormDefinitionOfDone();
  setupPipelineButtons();
  setupFilter();
  setupTaskSurfaceActions();
  setupBuilderJudge();

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
