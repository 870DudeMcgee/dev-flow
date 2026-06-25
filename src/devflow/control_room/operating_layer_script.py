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

// === BROWSER TASK CAPABILITIES ===
// Legacy fallback for older snapshots. New task controls/actions should carry intent directly.
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
  const requiredInputs = Array.isArray(raw.required_inputs)
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
  for (const action of task?.actions || []) push(action);
  if (task?.next_action?.command) {
    const fallbackIntent = task.next_action.intent || intentForCommand(task.next_action.command);
    push({ ...task.next_action, label: task.next_action.label || labelForIntent(fallbackIntent) });
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
  const selectedTaskPresentation = selected ? {
    task_id: selected.id,
    title: selected.title || 'Untitled task',
    lane: selected.lane || 'new',
    display_status: selected.display_status || selected.lane || 'new',
    worker_model_label: taskWorkerLabel(selected),
    verification_status: selected.verification_status || 'not_run',
    latest: taskFreshness(selected),
    definition_of_done: selected.definition_of_done || null,
    action_label: selected ? taskActionLabel(selected) : 'Inspect task',
    command: primary?.command || selected.next_action?.command || '',
    reason: selected.next_action?.reason || null,
    evidence_paths: selected.evidence_paths || selected.detail?.evidence_paths || [],
  } : null;
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
    brainstorm: server?.brainstorm || source.brainstorm || null,
    pipeline: server?.pipeline || source.pipeline || { stages: pipelineState?.stages || [] },
    next_task: server?.next_task || selectedTaskPresentation,
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
    // Refresh pipeline state for this session.
    const messages = data.messages || [];
    pipelineState = data.pipeline && Array.isArray(data.pipeline.stages)
      ? data.pipeline
      : {
          stages: [
            { id: 'brainstorm', label: 'Brainstorm', status: messages.length > 0 ? 'complete' : 'pending' },
            { id: 'spec', label: 'Spec', status: data.spec != null ? 'complete' : 'pending' },
            { id: 'plan', label: 'Plan', status: data.plan != null ? 'complete' : 'pending' },
            { id: 'implementation', label: 'Implementation Task', status: Boolean(data.implementation || data.pipeline?.has_implementation) ? 'complete' : 'pending' },
          ],
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
  pipelineState = { stages: [] };
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

// === IDEA GREENHOUSE ===
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

// === PIPELINE ===
let pipelineState = { stages: [] };

async function refreshPipelineState() {
  try {
    const resp = await fetch(`/api/brainstorm/transcript?session_id=${encodeURIComponent(brainstormSessionId)}`);
    const data = await resp.json();
    pipelineState.stages = data.pipeline?.stages || [];
  } catch(e) { /* ignore */ }
  renderPipeline();
}

function isPipelineStageComplete(stage) {
  if (stage?.complete === true || stage?.done === true) return true;
  const status = String(stage?.status || '').toLowerCase();
  return ['complete', 'accepted', 'passed'].includes(status);
}

function getPipelineFirstIncompleteIndex(state) {
  const stages = state?.stages || [];
  return stages.findIndex(stage => !isPipelineStageComplete(stage));
}

function getPipelinePrimaryStage(state) {
  if (state?.primary_stage_id) return state.primary_stage_id;
  const stages = state?.stages || [];
  const next = stages.find(stage => !isPipelineStageComplete(stage));
  if (!next) return null;
  if (next.id === 'brainstorm') return null;
  return next.id || null;
}

function getNextStageLabel(stageId) {
  if (stageId === 'spec') return 'Generate Spec →';
  if (stageId === 'plan') return 'Generate Plan →';
  if (stageId === 'implementation') return 'Create Task →';
  if (stageId === 'task') return 'View Tasks';
  return 'Review →';
}

function getPrimaryActionLabel(state) {
  if (state?.primary_action_label) return state.primary_action_label;
  const stage = getPipelinePrimaryStage(state);
  if (stage) return getNextStageLabel(stage);
  const stages = state?.stages || [];
  const firstIncomplete = stages.find(stage => !isPipelineStageComplete(stage));
  if (firstIncomplete?.id === 'brainstorm') return 'Start Brainstorm';
  const taskExists = stages.find(s => s.id === 'task')?.status !== undefined;
  return taskExists ? 'View Tasks' : 'Review →';
}

function renderPipeline(input) {
  if (input && Array.isArray(input.stages)) {
    pipelineState = input;
  }
  const container = document.getElementById('pipeline-stages-container');
  if (!container) return;
  container.innerHTML = '';

  const primaryStage = getPipelinePrimaryStage(pipelineState);
  const primaryAction = document.createElement('div');
  primaryAction.className = 'pipeline-primary-action';
  const primaryBtn = document.createElement('button');
  primaryBtn.type = 'button';
  primaryBtn.className = 'btn btn-primary btn-lg';
  primaryBtn.dataset.pipelinePrimaryAction = 'true';
  primaryBtn.textContent = getPrimaryActionLabel(pipelineState);
  if (!primaryStage) { primaryBtn.disabled = true; primaryBtn.classList.add('disabled'); }
  primaryAction.appendChild(primaryBtn);
  container.appendChild(primaryAction);

  const firstIncompleteIndex = getPipelineFirstIncompleteIndex(pipelineState);
  pipelineState.stages.forEach((stage, idx) => {
    const isComplete = isPipelineStageComplete(stage);
    const isActive = !isComplete && idx === firstIncompleteIndex;
    const isLocked = !isComplete && !isActive;
    const actionEnabled = stage.id === primaryStage;

    const step = document.createElement('div');
    step.className = 'pipeline-step';
    if (isActive) step.classList.add('active');
    if (isLocked) step.classList.add('locked');
    step.dataset.stage = stage.id;

    // Step number circle
    const stepNumber = document.createElement('div');
    stepNumber.className = 'step-number';
    const numSpan = document.createElement('span');
    numSpan.textContent = String(idx + 1).padStart(2, '0');
    stepNumber.appendChild(numSpan);

    // Connector SVG (skip on last stage)
    if (idx < pipelineState.stages.length - 1) {
      const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.setAttribute('width', '2');
      svg.setAttribute('height', '24');
      svg.setAttribute('class', 'step-connector');
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', '1');
      line.setAttribute('y1', '0');
      line.setAttribute('x2', '1');
      line.setAttribute('y2', '24');
      line.setAttribute('stroke', 'currentColor');
      line.setAttribute('stroke-width', '2');
      svg.appendChild(line);
      stepNumber.appendChild(svg);
    }

    step.appendChild(stepNumber);

    // Step content
    const content = document.createElement('div');
    content.className = 'step-content';

    const row = document.createElement('div');
    row.className = 'step-row';

    const strong = document.createElement('strong');
    strong.textContent = stage.label || sentenceCase(stage.id || 'stage');
    row.appendChild(strong);

    const statusEl = document.createElement('span');
    statusEl.className = 'step-status';
    if (isComplete) {
      statusEl.textContent = 'Done';
      statusEl.classList.add('active');
    } else if (isActive) {
      statusEl.textContent = 'Next';
      statusEl.classList.add('active');
    } else {
      statusEl.textContent = 'Pending';
      statusEl.classList.add('pending');
    }
    row.appendChild(statusEl);

    content.appendChild(row);

    // Step source/action info from StageArtifact
    if (stage.next_action) {
      const actionEl = document.createElement('p');
      actionEl.className = 'step-desc';
      actionEl.textContent = stage.next_action;
      content.appendChild(actionEl);
    }
    if (stage.source) {
      const sourceEl = document.createElement('p');
      sourceEl.className = 'step-source';
      sourceEl.textContent = 'via ' + stage.source;
      sourceEl.style.cssText = 'font-size: 10px; color: var(--text-muted); margin: 2px 0 0;';
      content.appendChild(sourceEl);
    }

    // Step action buttons
    const action = document.createElement('p');
    action.className = 'step-action';

    if (stage.id === 'brainstorm') {
      const btn1 = document.createElement('button');
      btn1.type = 'button';
      btn1.className = 'btn btn-sm btn-primary';
      btn1.dataset.brainstormStage = 'spec';
      btn1.textContent = 'Escalate to Spec →';
      if (!actionEnabled) { btn1.disabled = true; btn1.classList.add('disabled'); }
      action.appendChild(btn1);

      const btn2 = document.createElement('button');
      btn2.type = 'button';
      btn2.className = 'btn btn-sm btn-secondary';
      btn2.dataset.bjQualityGate = 'spec';
      btn2.title = 'Run builder-judge quality gate before escalating';
      btn2.textContent = 'QC Gate';
      if (!actionEnabled) { btn2.disabled = true; btn2.classList.add('disabled'); }
      action.appendChild(btn2);
    } else if (stage.id === 'spec') {
      const btn1 = document.createElement('button');
      btn1.type = 'button';
      btn1.className = 'btn btn-sm btn-secondary';
      btn1.dataset.brainstormStage = 'spec';
      btn1.textContent = 'Generate Spec →';
      if (!actionEnabled) { btn1.disabled = true; btn1.classList.add('disabled'); }
      action.appendChild(btn1);

      const btn2 = document.createElement('button');
      btn2.type = 'button';
      btn2.className = 'btn btn-sm btn-secondary';
      btn2.dataset.bjQualityGate = 'spec';
      btn2.title = 'Run builder-judge quality gate before generating spec';
      btn2.textContent = 'QC Gate';
      if (!actionEnabled) { btn2.disabled = true; btn2.classList.add('disabled'); }
      action.appendChild(btn2);
    } else if (stage.id === 'plan') {
      const btn1 = document.createElement('button');
      btn1.type = 'button';
      btn1.className = 'btn btn-sm btn-secondary';
      btn1.dataset.brainstormStage = 'plan';
      btn1.textContent = 'Generate Plan →';
      if (!actionEnabled) { btn1.disabled = true; btn1.classList.add('disabled'); }
      action.appendChild(btn1);

      const btn2 = document.createElement('button');
      btn2.type = 'button';
      btn2.className = 'btn btn-sm btn-secondary';
      btn2.dataset.bjQualityGate = 'plan';
      btn2.title = 'Run builder-judge quality gate before generating plan';
      btn2.textContent = 'QC Gate';
      if (!actionEnabled) { btn2.disabled = true; btn2.classList.add('disabled'); }
      action.appendChild(btn2);
    } else if (stage.id === 'implementation') {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-sm btn-secondary';
      btn.dataset.brainstormStage = 'implementation';
      btn.textContent = 'Create Task →';
      if (!actionEnabled) { btn.disabled = true; btn.classList.add('disabled'); }
      action.appendChild(btn);
    }

    content.appendChild(action);
    step.appendChild(content);
    container.appendChild(step);
  });
  setupPipelineButtons(container);
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

// === ATOMIC BRAINSTORM -> TASK BRIDGE (Slice 2) ==========================
async function createTaskFromBrainstorm(sessionId, title, options = {}) {
  const body = { session_id: sessionId, title };
  if (options.definition_of_done) body.definition_of_done = options.definition_of_done;
  if (options.source_idea_id) body.source_idea_id = options.source_idea_id;
  const resp = await fetch('/api/brainstorm/create-task', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const raw = await resp.text();
  let payload = {};
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch(e) {
      payload = { error: raw };
    }
  }
  if (!resp.ok) {
    throw new Error(payload.error || payload.message || `create-task returned ${resp.status}`);
  }
  return payload;
}

function useModelForBrainstormStage(stage) {
  return stage === 'spec' || stage === 'plan';
}

function setupPipelineButtons(scope) {
  const root = scope || document;

  root.querySelectorAll('[data-pipeline-primary-action]').forEach(btn => {
    if (btn.dataset.pipelineBound === '1') return;
    btn.dataset.pipelineBound = '1';
    btn.addEventListener('click', async () => {
      const stage = getPipelinePrimaryStage(pipelineState);
      if (!stage) return;
      const stageButton = Array.from(document.querySelectorAll('#pipeline-stages-container [data-brainstorm-stage]'))
        .find(item => item.dataset.brainstormStage === stage && !item.disabled);
      if (stageButton) {
        stageButton.click();
        return;
      }
      btn.disabled = true;
      const originalText = btn.textContent;
      btn.textContent = 'Escalating...';
      try {
        await escalateBrainstormStage(stage, useModelForBrainstormStage(stage));
        await loadSnapshot(selectedProjectId);
        await refreshPipelineState();
        await loadBrainstormSessions();
      } catch(e) {
        appendBrainstormMsg('system', 'Escalation failed: ' + (e.message || 'unknown error'), { kind: 'provider_error' });
      } finally {
        btn.disabled = false;
        btn.textContent = originalText;
      }
    });
  });

  root.querySelectorAll('[data-brainstorm-stage]').forEach(btn => {
    if (btn.dataset.pipelineBound === '1') return;
    btn.dataset.pipelineBound = '1';
    btn.addEventListener('click', async () => {
      const stage = btn.dataset.brainstormStage;
      if (!stage) return;
      btn.disabled = true;
      const originalText = btn.textContent;
      btn.textContent = 'Escalating...';
      const useModel = useModelForBrainstormStage(stage);
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
              // Prefer atomic bridge: single round-trip for task + context
              const implContext = implementationContextFromPipelinePayload(payload);
              let createdTaskId = null;
              let outLine = '';

              if (implContext?.text && implContext.text.trim()) {
                // Use the new /api/brainstorm/create-task bridge
                const dodValue = currentBrainstormDefinitionOfDone();
                const bridgePayload = await createTaskFromBrainstorm(
                  brainstormSessionId,
                  taskAction.title,
                  { definition_of_done: dodValue || undefined }
                );
                if (!bridgePayload || !bridgePayload.task_id) {
                  throw new Error('Brainstorm task bridge did not return a task id');
                }
                createdTaskId = bridgePayload.task_id;
                outLine = `Task ${createdTaskId}: ${taskAction.title}`;
              } else {
                // Fallback to legacy two-step choreography
                const cmd = taskAction.command;
                const actionResult = await runApprovedCommand(cmd, {});
                if (actionResult.executed && actionResult.exit_code === 0) {
                  outLine = (actionResult.stdout || '').trim().split(String.fromCharCode(10))[0];
                  createdTaskId = parseCreatedTaskId(actionResult.stdout);
                  if (!createdTaskId) {
                    throw new Error('Legacy task creation did not return a task id');
                  }
                } else {
                  throw new Error(actionResult.message || actionResult.stderr || 'Legacy task creation failed');
                }
              }

              if (createdTaskId && outLine) {
                const contextTarget = implContext?.target_path_template || '.devflow/workspaces/{task_id}/implementation-context.md';
                const contextPath = contextTarget.replace('{task_id}', createdTaskId);
                const nextMsg = `Task created: ${outLine}. Implementation context target: ${contextPath}. Next: use the Next Task launchpad.`;
                appendBrainstormMsg('system', nextMsg, {});
                await loadSnapshot(selectedProjectId);
                selectTaskInLaunchpad(createdTaskId, { focusShell: true });
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
  root.querySelectorAll('[data-bj-quality-gate]').forEach(btn => {
    if (btn.dataset.pipelineBound === '1') return;
    btn.dataset.pipelineBound = '1';
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
  if (section && !opts?.silent) section.scrollIntoView({ block: 'start', behavior: 'auto' });
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
    <textarea data-promotion-note aria-label="Promotion context note" placeholder="Promotion context for the human approval record"></textarea>
    <div class="task-action-row">
      ${previewAction ? `<button class="btn btn-sm btn-readonly" type="button" data-command="${esc(previewAction.command)}" data-action-intent="readonly" aria-label="Open promotion review preview">Review preview</button>` : ''}
      ${promoteAction ? `<button class="btn btn-sm btn-primary" type="button" data-command="${esc(promoteAction.command)}" data-action-intent="safe" aria-label="Promote task after review">Promote</button>` : ''}
    </div>
  </div>`;
}

function renderWorkerOptions(task) {
  const options = Array.isArray(task?.worker_options) ? task.worker_options : [];
  const aiOptions = options.filter(option => option?.worker_id && option.worker_id !== 'shell');
  if (aiOptions.length) {
    return aiOptions.map(option => {
      const blockedReason = option.blocked_reason || '';
      const enabled = option.enabled !== false && !blockedReason;
      const actionKind = option.action_kind || (option.command ? 'serial_packet' : 'inspect');
      const runtime = option.runtime_kind || '';
      const command = option.command || '';
      const profile = option.hermes_profile || option.worker_id;
      const label = option.label || sentenceCase(option.worker_id || 'worker');
      const modelLine = [option.provider, option.model].filter(Boolean).join(' · ');
      const safeWorkerId = String(option.worker_id || 'worker').replace(/[^a-z0-9_-]+/gi, '-');
      const blockedHelpId = `nt-worker-blocked-${task?.id || 'task'}-${safeWorkerId}`;
      const ariaLabel = enabled
        ? `${label} worker action. Press Enter or Space to open packet form.`
        : `${label} unavailable: ${blockedReason || option.reason || 'worker option is disabled'}`;
      const describedBy = !enabled && blockedReason ? ` aria-describedby="${esc(blockedHelpId)}"` : '';
      const recommended = enabled ? 'Recommended worker' : 'Worker unavailable';
      const copy = enabled && actionKind === 'serial_packet'
        ? `Creates a bounded serial packet for ${profile}. Launch remains outside browser; verifier is final proof.`
        : (option.reason || 'Worker option is visible for operator review.');
      const commandHtml = command
        ? `<div class="nt-copy-command-row nt-worker-command-row">
            <code class="nt-worker-command">${esc(shortCommand(command, 140))}</code>
            <button class="btn btn-sm btn-readonly" type="button" data-copy-command="${esc(command)}" data-copy-kind="terminal_command" aria-label="Copy terminal command for ${esc(label)}">Copy</button>
          </div>`
        : '';
      const disabledClass = enabled ? '' : ' is-disabled';
      const disabledHelp = !enabled && blockedReason
        ? `<p class="nt-worker-blocked" id="${esc(blockedHelpId)}"><strong>Unavailable:</strong> ${esc(blockedReason)}</p>`
        : '';
      return `<article class="nt-worker-card${disabledClass}" role="button" tabindex="0" aria-disabled="${enabled ? 'false' : 'true'}" aria-label="${esc(ariaLabel)}"${describedBy} data-worker-option-card="ai" data-worker-id="${esc(option.worker_id)}" data-worker-label="${esc(label)}" data-worker-provider="${esc(option.provider || '')}" data-worker-model="${esc(option.model || '')}" data-worker-enabled="${enabled ? 'true' : 'false'}" data-worker-action-kind="${esc(actionKind)}" data-worker-runtime="${esc(runtime)}" data-worker-command="${esc(command)}" data-worker-blocked-reason="${esc(blockedReason)}">
        <div class="nt-worker-card-head">
          <span class="nt-worker-badge">${esc(recommended)}</span>
          <strong>${esc(label)}</strong>
        </div>
        ${modelLine ? `<p class="nt-worker-model">${esc(modelLine)}</p>` : ''}
        <p class="nt-worker-copy">${esc(copy)}</p>
        ${disabledHelp}
        ${commandHtml}
      </article>`;
    }).join('');
  }
  const capability = taskCapabilityAny(task, ['start_shell', 'retry']);
  if (!capability) return '';
  return `<div class="nt-no-workers">
    <p>${esc(capability.label || 'Shell worker')}</p>
    <code>${esc(shortCommand(capability.command, 120))}</code>
  </div>`;
}

function selectedLaunchpadTask() {
  return snapshot?.tasks?.find(t => t.id === selectedTaskId) || null;
}

function findWorkerOptionForCard(card, task) {
  const workerId = card?.dataset?.workerId || '';
  const options = Array.isArray(task?.worker_options) ? task.worker_options : [];
  return options.find(option => String(option?.worker_id || '') === workerId) || null;
}

function serialPacketPanelForCard(card) {
  const scopedPanel = card?.closest('.task-command-box')?.querySelector('[data-serial-packet-panel]');
  return scopedPanel || $('next-task-packet-panel') || $('focus-task-packet-panel');
}

function hideSerialPacketPanel(panel) {
  const target = panel || $('next-task-packet-panel') || $('focus-task-packet-panel');
  if (!target) return;
  target.hidden = true;
  target.innerHTML = '';
}

function workerCardBlockedReason(card, option) {
  return option?.blocked_reason || card?.dataset?.workerBlockedReason || option?.reason || 'Worker is currently unavailable.';
}

function splitAllowedFileInput(value) {
  const newline = String.fromCharCode(10);
  return String(value || '')
    .replace(/,/g, newline)
    .split(newline)
    .map(part => part.trim())
    .filter(Boolean);
}

function stripSerialPacketPlaceholderArgs(command) {
  return String(command || '')
    .replace(/\\s+--allowed-file\\s+<allowed-file>/g, '')
    .replace(/\\s+--verify\\s+<verification-command>/g, '')
    .trim();
}

function materializeSerialPacketCommand(command, values) {
  const base = stripSerialPacketPlaceholderArgs(command);
  const allowedFiles = splitAllowedFileInput(values?.allowedFiles);
  const verifyCommand = String(values?.verifyCommand || '').trim();
  if (!base) throw new Error('Serial packet base command is missing.');
  if (!allowedFiles.length) throw new Error('Enter at least one allowed file path.');
  if (!verifyCommand) throw new Error('Enter a verification command.');
  let concrete = base;
  for (const filePath of allowedFiles) {
    concrete += ` --allowed-file ${shellQuote(filePath)}`;
  }
  concrete += ` --verify ${shellQuote(verifyCommand)}`;
  if (/<[^>]+>/.test(concrete)) {
    throw new Error('Serial packet command still contains placeholder values.');
  }
  return concrete;
}

function serialPacketFormValues(panel) {
  return {
    allowedFiles: panel?.querySelector('[data-packet-allowed-files]')?.value || '',
    verifyCommand: panel?.querySelector('[data-packet-verify-command]')?.value || '',
  };
}

function updateSerialPacketPanelState(panel) {
  if (!panel) return null;
  const preview = panel.querySelector('[data-packet-command-preview]');
  const submit = panel.querySelector('[data-create-serial-packet]');
  const copyButton = panel.querySelector('[data-copy-command][data-copy-kind="packet_preview"]');
  const baseCommand = panel.dataset.packetBaseCommand || '';
  let concrete = '';
  try {
    concrete = materializeSerialPacketCommand(baseCommand, serialPacketFormValues(panel));
    panel.dataset.packetCommand = concrete;
    if (preview) preview.textContent = concrete;
    if (copyButton) copyButton.dataset.copyCommand = concrete;
    if (submit) submit.disabled = false;
  } catch(err) {
    delete panel.dataset.packetCommand;
    if (preview) preview.textContent = baseCommand;
    if (copyButton) copyButton.dataset.copyCommand = baseCommand;
    if (submit) submit.disabled = true;
  }
  return concrete || null;
}

function openSerialPacketPanel(card) {
  const panel = serialPacketPanelForCard(card);
  const task = selectedLaunchpadTask();
  const option = findWorkerOptionForCard(card, task);
  const enabled = card?.dataset?.workerEnabled === 'true' && option?.enabled !== false && !option?.blocked_reason;
  const actionKind = option?.action_kind || card?.dataset?.workerActionKind || '';
  const command = option?.command || card?.dataset?.workerCommand || '';

  if (!panel) return;
  if (!enabled) {
    hideSerialPacketPanel(panel);
    const reason = workerCardBlockedReason(card, option);
    renderActionResult({ executed: false, exit_code: null, error: reason }, command || option?.worker_id || card?.dataset?.workerId || 'worker option');
    return;
  }
  if (actionKind !== 'serial_packet') {
    hideSerialPacketPanel(panel);
    renderActionResult({ executed: false, exit_code: null, error: 'This worker option does not expose serial-packet creation yet.' }, command || option?.worker_id || 'worker option');
    return;
  }

  const workerId = option?.worker_id || card?.dataset?.workerId || 'worker';
  const label = option?.label || card?.dataset?.workerLabel || sentenceCase(workerId);
  const provider = option?.provider || card?.dataset?.workerProvider || 'provider';
  const model = option?.model || card?.dataset?.workerModel || 'model';
  const runtime = option?.runtime_kind || card?.dataset?.workerRuntime || 'hermes-profile';
  const profile = option?.hermes_profile || workerId;
  const recommendedAllowedFiles = Array.isArray(option?.recommended_allowed_files)
    ? option.recommended_allowed_files.join(String.fromCharCode(10))
    : '';
  const recommendedVerificationCommand = Array.isArray(option?.recommended_verification_commands)
    ? (option.recommended_verification_commands[0] || '')
    : '';
  const baseCommand = command || `devflow agent serial-packet --phase implementer --provider ${shellQuote(provider)} --model ${shellQuote(model)} --task-id ${shellQuote(task?.id || '<task-id>')} --worker-id ${shellQuote(workerId)} --runtime ${shellQuote(runtime)} --hermes-profile ${shellQuote(profile)} --allowed-file <allowed-file> --verify <verification-command>`;
  panel.innerHTML = `<div class="nt-packet-panel-inner" role="form" aria-label="Create serial packet for ${esc(label)}">
    <div class="nt-packet-heading">
      <span class="nt-worker-badge">Packet setup</span>
      <strong>Create serial packet</strong>
      <em>${esc(label)}</em>
    </div>
    <p class="nt-worker-copy">Create packet writes bounded serial-run evidence only. It does not launch Hermes, run a model, verify work, stage, commit, or push.</p>
    <div class="nt-packet-grid">
      <label>Allowed files<textarea data-packet-allowed-files aria-label="Allowed files for serial packet" placeholder="src/path/to/file.py, src/second_file.py"></textarea></label>
      <label>Verification command<input type="text" data-packet-verify-command aria-label="Verification command for serial packet" placeholder="env PYTHONPATH=src:. .venv/bin/python -m pytest tests/test_target.py -q"></label>
    </div>
    <div class="nt-packet-meta">
      <span>Task <strong>${esc(task?.id || 'unknown')}</strong></span>
      <span>Runtime <strong>${esc(runtime)}</strong></span>
      <span>Profile <strong>${esc(profile)}</strong></span>
      <span>Model <strong>${esc([provider, model].filter(Boolean).join(' · '))}</strong></span>
    </div>
    <div class="nt-command-preview">
      <span>Command preview</span>
      <code data-packet-command-preview>${esc(baseCommand)}</code>
      <button class="btn btn-sm btn-readonly" type="button" data-copy-command="${esc(baseCommand)}" data-copy-kind="packet_preview" aria-label="Copy packet command preview">Copy</button>
    </div>
    <button class="btn btn-primary btn-sm" type="button" data-create-serial-packet data-packet-create-submit data-action-intent="safe" aria-label="Create serial packet for ${esc(task?.id || 'task')}" disabled>Create serial packet</button>
  </div>`;
  panel.dataset.packetBaseCommand = baseCommand;
  delete panel.dataset.packetCommand;
  const allowedInput = panel.querySelector('[data-packet-allowed-files]');
  const verifyInput = panel.querySelector('[data-packet-verify-command]');
  if (allowedInput) allowedInput.value = recommendedAllowedFiles;
  if (verifyInput) verifyInput.value = recommendedVerificationCommand;
  panel.hidden = false;
  updateSerialPacketPanelState(panel);
  panel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  if (allowedInput) allowedInput.focus();
}

function serialRuntimeManualCommand(serial) {
  const latest = serial?.latest_run || null;
  if (!latest?.run_id) return '';
  const profile = serial?.hermes_profile || latest.hermes_profile || '';
  if ((serial?.runtime_kind || latest.runtime_kind) === 'hermes-profile' && profile) {
    return `devflow agent hermes-run ${shellQuote(latest.run_id)} --profile ${shellQuote(profile)} --dry-run`;
  }
  const runDir = latest.run_dir || `.devflow/local-agent-runs/${latest.run_id}`;
  return `cd ${shellQuote(runDir)} && ./completion-verifier.py`;
}

function serialRuntimeStatusInfo(serial) {
  const latest = serial?.latest_run || null;
  const status = serial?.verification_status && serial.verification_status !== 'not_run'
    ? serial.verification_status
    : (serial?.run_state || latest?.state || serial?.status || 'none');
  return taskStatusInfo(status);
}

function renderSerialRuntimePanel(serial) {
  const panel = $('serial-runtime-panel');
  if (!panel) return;
  const data = serial || {};
  const latest = data.latest_run || null;
  const info = serialRuntimeStatusInfo(data);
  panel.className = `serial-runtime-panel ${info.toneClass} ${info.railClass}`;

  if (!latest) {
    panel.innerHTML = `<div class="serial-runtime-head">
      <div class="serial-runtime-title"><strong>Worker Runtime</strong></div>
      <span class="${taskStatusInfo('none').badgeClass}">No packet yet</span>
    </div>
    <p class="serial-runtime-empty">No packet yet — create one from a worker card.</p>
    <div class="serial-runtime-next"><span>next safe action</span>${esc(data.next_safe_action || 'Create a packet from a worker card before launching local workers.')}</div>`;
    return;
  }

  const runId = latest.run_id || 'unknown-run';
  const runtimeKind = data.runtime_kind || latest.runtime_kind || 'manual';
  const hermesProfile = data.hermes_profile || latest.hermes_profile || '—';
  const launchStatus = data.launch_status || latest.launch_status || 'not_started';
  const verificationStatus = data.verification_status || latest.verification_status || 'not_run';
  const runState = data.run_state || latest.state || data.status || 'unknown';
  const evidencePaths = Array.isArray(latest.evidence_paths) ? latest.evidence_paths : [];
  const manualCommand = serialRuntimeManualCommand(data);
  const evidenceHtml = evidencePaths.length
    ? evidencePaths.slice(0, 8).map(path => `<code>${esc(path)}</code>`).join('')
    : '<em class="nt-hint">No evidence paths recorded yet.</em>';
  const commandHtml = manualCommand
    ? `<div class="serial-runtime-command">
        <span>dry-run/manual command</span>
        <code>${esc(manualCommand)}</code>
        <button class="btn btn-sm btn-readonly" type="button" data-copy-serial-command="${esc(manualCommand)}" data-action-intent="readonly" aria-label="Copy dry-run or manual runtime command">Copy</button>
      </div>`
    : '';

  panel.innerHTML = `<div class="serial-runtime-head">
    <div class="serial-runtime-title"><strong>Worker Runtime</strong><code>${esc(runId)}</code></div>
    <span class="${info.badgeClass}">${esc(info.label)}</span>
  </div>
  <div class="serial-runtime-grid">
    <div class="serial-runtime-field"><span>current run id</span><code>${esc(runId)}</code></div>
    <div class="serial-runtime-field"><span>runtime kind</span><code>${esc(runtimeKind)}</code></div>
    <div class="serial-runtime-field"><span>Hermes profile</span><code>${esc(hermesProfile)}</code></div>
    <div class="serial-runtime-field"><span>run state</span><code>${esc(runState)}</code></div>
    <div class="serial-runtime-field"><span>launch status</span><code>${esc(launchStatus)}</code></div>
    <div class="serial-runtime-field"><span>verification status</span><code>${esc(verificationStatus)}</code></div>
  </div>
  <div class="serial-runtime-evidence"><span>evidence links/paths</span><div class="serial-runtime-evidence-list">${evidenceHtml}</div></div>
  <div class="serial-runtime-next"><span>next safe action</span>${esc(data.next_safe_action || 'Review packet evidence before any manual launch.')}</div>
  ${commandHtml}`;
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
    <button class="btn btn-sm btn-danger" type="button" data-command="${esc(closeCmd)}" data-action-intent="destructive" aria-label="Close failed task as abandoned">
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
  const shellCommandTemplate = startCapability?.command || command || `devflow task run ${task.id} --worker shell -- <command>`;
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
        <div class="task-command-box nt-packet-panel" id="next-task-packet-panel" data-serial-packet-panel hidden aria-live="polite"></div>
        <div class="nt-shell-fallback">
          <details>
            <summary>Or run a raw shell command</summary>
            <div class="inline-command-row">
              <input type="text" data-shell-command aria-label="Shell command for ${esc(task.id)}" placeholder="pytest tests/test_target.py -q">
              <button class="btn btn-primary btn-sm" type="button" data-task-run-shell="${esc(task.id)}" data-action-intent="safe" aria-label="Run shell command for ${esc(task.id)}">▶ Run shell</button>
            </div>
            <div class="nt-copy-command-row">
              <code>${esc(shellCommandTemplate)}</code>
              <button class="btn btn-readonly btn-sm" type="button" data-copy-command="${esc(shellCommandTemplate)}" data-copy-kind="terminal_command" data-action-intent="readonly" aria-label="Copy terminal command for ${esc(task.id)}">Copy</button>
            </div>
          </details>
        </div>
      </div>`
    : '';

  const verifyPanel = (lane === 'needs_verification' || commandNeedsVerificationInput(command, verifyCapability || primaryCapability))
    ? `<div class="task-command-box nt-primary-action nt-verify-action" id="next-task-verify-panel">
        <label>Verify task</label>
        <div class="inline-command-row">
          <input type="text" data-verify-command aria-label="Verification command for ${esc(task.id)}" placeholder="git diff --check && pytest -q">
          <button class="btn btn-caution btn-sm" type="button" data-task-verify="${esc(task.id)}" data-action-intent="verify" aria-label="Run verification for ${esc(task.id)}">✓ Verify</button>
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
          <input type="text" data-close-reason aria-label="Close reason for ${esc(task.id)}" placeholder="Reason required">
          <button class="btn btn-sm btn-danger" type="button" data-task-close="${esc(task.id)}" data-action-intent="destructive" aria-label="Close ${esc(task.id)}">Close</button>
        </div>
      </details>`
    : `<div class="task-action-row"><button class="btn btn-sm btn-readonly" type="button" data-command="${esc(cleanupCapability?.command || `devflow task cleanup ${task.id} --preview`)}" data-action-intent="readonly" aria-label="Preview cleanup for ${esc(task.id)}">Cleanup preview</button></div>`;
  const utilityButtons = `<details class="nt-more-actions">
    <summary><span>More actions</span></summary>
    <div class="nt-utility-row">
      <button class="btn btn-sm btn-readonly" type="button" data-inspect-task="${esc(task.id)}" data-action-intent="readonly" aria-label="Inspect ${esc(task.id)}">Inspect</button>
      ${taskCommandButtons(task)}
    </div>
  </details>`;
  return workerPanel || verifyPanel || promotionPanel || implContextPanel || reconcilePanel
    ? `${implContextPanel}${workerPanel}${reconcilePanel}${verifyPanel}${promotionPanel}${utilityButtons}${closePanel}`
    : `${utilityButtons}${closePanel}`;
}

function reviewActionForNextSteps(firstViewport, selected) {
  const queue = Array.isArray(firstViewport?.review_queue) ? firstViewport.review_queue : [];
  if (!queue.length) return null;
  return queue.find(item => ['ready_to_promote', 'needs_review', 'needs_verification'].includes(item?.lane || ''))
    || queue.find(item => item?.task_id !== selected?.id)
    || queue[0];
}

function recommendedWorkerForNextSteps(task) {
  const options = Array.isArray(task?.worker_options) ? task.worker_options : [];
  return options.find(option => option?.action_kind === 'serial_packet' && option.enabled !== false && !option.blocked_reason)
    || options.find(option => option?.worker_id && option.worker_id !== 'shell' && option.enabled !== false && !option.blocked_reason)
    || null;
}

function latestEvidenceForNextSteps(task, firstViewport) {
  const paths = task?.detail?.evidence_paths || task?.evidence_paths || [];
  if (paths.length) {
    return { task_id: task.id, label: 'Latest evidence', text: paths[0], path: paths[0] };
  }
  const stream = Array.isArray(firstViewport?.evidence_stream) ? firstViewport.evidence_stream : [];
  return stream.find(item => item?.task_id === task?.id) || stream[0] || null;
}

function serialRuntimeLabelForNextSteps(serial) {
  const latest = serial?.latest_run || null;
  if (!latest) return 'No packet yet';
  const status = serial?.verification_status || latest.verification_status || serial?.run_state || latest.state || 'packet ready';
  return `${latest.run_id || 'packet'} · ${status}`;
}

function renderOperatorNextSteps(firstViewport, selected, snap) {
  const host = $('operator-next-steps');
  if (!host) return;
  if (!selected) {
    host.innerHTML = `<div class="operator-next-steps-head">
      <strong>What can I do next?</strong>
      <span>Create or select an active task to unlock launchpad actions.</span>
    </div>`;
    return;
  }

  const worker = recommendedWorkerForNextSteps(selected);
  const serial = snap?.serial_local_agent_run || {};
  const evidence = latestEvidenceForNextSteps(selected, firstViewport);
  const review = reviewActionForNextSteps(firstViewport, selected);
  const selectedInfo = taskStatusInfo(selected.display_status || selected.lane || 'new');
  const workerText = worker
    ? `${worker.label || sentenceCase(worker.worker_id)}${worker.provider || worker.model ? ` · ${[worker.provider, worker.model].filter(Boolean).join(' / ')}` : ''}`
    : 'No AI worker action available for this task.';
  const workerButton = worker?.action_kind === 'serial_packet'
    ? `<button class="btn btn-sm btn-primary" type="button" data-open-next-worker-card="${esc(worker.worker_id)}" data-action-intent="safe" aria-label="Open packet form for ${esc(worker.label || worker.worker_id)}">Open packet form</button>`
    : '';
  const evidenceText = evidence?.path || evidence?.text || 'No evidence yet';
  const reviewTaskId = review?.task_id || review?.id || '';
  const reviewText = review
    ? `${reviewTaskId} · ${review.title || 'Review item'}${review.action_label ? ` · ${review.action_label}` : ''}`
    : 'No review or verification action queued.';
  const reviewButton = reviewTaskId
    ? `<button class="btn btn-sm btn-caution" type="button" data-select-task="${esc(reviewTaskId)}" data-action-intent="verify" aria-label="Open review action for ${esc(reviewTaskId)}">Open review action</button>`
    : '';

  host.innerHTML = `<div class="operator-next-steps-head">
    <strong>What can I do next?</strong>
    <span>Use the launchpad first; open detail only when you need depth.</span>
  </div>
  <div class="operator-next-steps-grid">
    <article class="operator-next-step task-card ${selectedInfo.toneClass} ${selectedInfo.railClass}" data-next-step-card="active_task" aria-label="Active task ${esc(selected.id)}">
      <span>Active task selector</span>
      <strong>${esc(selected.id)} · ${esc(selected.title || 'Untitled task')}</strong>
      <button class="btn btn-sm btn-readonly" type="button" data-select-task="${esc(selected.id)}" data-action-intent="readonly" aria-label="Keep ${esc(selected.id)} selected">Keep selected</button>
    </article>
    <article class="operator-next-step task-card ${worker ? 'task-tone-green task-rail-green' : 'task-tone-gray task-rail-gray'}" data-next-step-card="recommended_worker" aria-label="Recommended worker action">
      <span>Recommended worker action</span>
      <strong>${esc(workerText)}</strong>
      ${workerButton || '<em>No worker lever for this task.</em>'}
    </article>
    <article class="operator-next-step task-card task-tone-blue task-rail-blue" data-next-step-card="serial_runtime" aria-label="Serial runtime status">
      <span>Serial runtime status</span>
      <strong>${esc(serialRuntimeLabelForNextSteps(serial))}</strong>
    </article>
    <article class="operator-next-step task-card task-tone-gray task-rail-gray" data-next-step-card="latest_evidence" aria-label="Latest evidence">
      <span>Latest evidence</span>
      <strong>${esc(shortCommand(evidenceText, 90))}</strong>
      <button class="btn btn-sm btn-readonly" type="button" data-select-task="${esc(selected.id)}" data-action-intent="readonly" aria-label="Review evidence for ${esc(selected.id)}">Review task evidence</button>
    </article>
    <article class="operator-next-step task-card ${review ? 'task-tone-orange task-rail-orange' : 'task-tone-gray task-rail-gray'}" data-next-step-card="review_action" aria-label="Review or verification action">
      <span>Review / verify action</span>
      <strong>${esc(shortCommand(reviewText, 90))}</strong>
      ${reviewButton || '<em>Nothing waiting for review.</em>'}
    </article>
  </div>`;
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

  renderOperatorNextSteps(firstViewport, selected, snap);
  renderSerialRuntimePanel(snap.serial_local_agent_run || {});

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

function shouldUsePresentationPipeline(pipeline) {
  return Boolean(
    pipeline
    && Array.isArray(pipeline.stages)
    && (!pipeline.session_id || pipeline.session_id === brainstormSessionId || !(pipelineState?.stages || []).length)
  );
}

function renderFirstViewport(presentation) {
  renderPipeline(shouldUsePresentationPipeline(presentation?.pipeline) ? presentation.pipeline : null);
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
    const intent = action.requires_human_approval ? 'safe' : 'readonly';
    const klass = intent === 'safe' ? 'btn-primary' : 'btn-readonly';
    commands.push(`<button class="btn btn-sm ${klass}" type="button" data-command="${esc(action.command)}" data-action-intent="${intent}" aria-label="${esc(action.label || 'Run command')}">${esc(action.label || 'Run command')}</button>`);
  }
  if (task.lane === 'closed' && !commands.some(command => command.includes('cleanup'))) {
    const cleanupCommand = taskCapability(task, 'cleanup_preview')?.command || `devflow task cleanup ${task.id} --preview`;
    commands.push(`<button class="btn btn-sm btn-readonly" type="button" data-command="${esc(cleanupCommand)}" data-action-intent="readonly" aria-label="Cleanup preview">Cleanup preview</button>`);
  }
  return commands.join(' ');
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


function openFocus(type, id, opts) {
  const overlay = $('focus-overlay');
  const content = $('focus-content');
  if (!overlay || !content) return;
  if (type === 'idea') {
    const idea = findIdeaCard(id);
    if (idea) {
      selectedTaskId = null;
      content.innerHTML = renderIdeaDetail(idea);
      overlay.hidden = false;
      return;
    }
  }
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
    const focusWorkerPanel = (lane !== 'closed' && Array.isArray(task.worker_options) && task.worker_options.length)
      ? `<div class="task-command-box nt-primary-action" id="focus-worker-panel">
          <label>AI worker controls</label>
          <div class="nt-worker-options">
            ${renderWorkerOptions(task)}
          </div>
          <div class="task-command-box nt-packet-panel" id="focus-task-packet-panel" data-serial-packet-panel hidden aria-live="polite"></div>
        </div>`
      : '';
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
      ${focusWorkerPanel}${shellPanel}${verifyPanel}${promotePanel}
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
function actionResultTargets() {
  const ids = ['guided-action-result', 'next-task-command-output', 'focus-command-output'];
  const seen = new Set();
  return ids
    .map(id => $(id))
    .filter(el => {
      if (!el || seen.has(el)) return false;
      seen.add(el);
      return true;
    });
}

function truncateActionOutput(value, limit) {
  const text = String(value || '');
  const max = limit || 2400;
  if (text.length <= max) return text;
  return text.slice(0, max) + `\n… output truncated (${text.length - max} more chars)`;
}

function actionResultState(result) {
  if (result?.timed_out) return 'timeout';
  if (result?.validation) return 'validation_error';
  if (result?.classification && !result?.executed) return 'blocked';
  if (!result?.executed) return 'error';
  return result?.exit_code === 0 ? 'succeeded' : 'failed';
}

function actionStateMeta(state, result) {
  if (state === 'pending') return { label: 'Pending', className: 'pending' };
  if (state === 'succeeded') return { label: `Succeeded · Exit ${result?.exit_code ?? 0}`, className: 'good' };
  if (state === 'failed') return { label: `Command failed · Exit ${result?.exit_code ?? 'n/a'}`, className: 'bad' };
  if (state === 'timeout') return { label: 'Timed out', className: 'bad' };
  if (state === 'blocked') return { label: 'Blocked by policy', className: 'blocked' };
  if (state === 'validation_error') return { label: 'Validation error', className: 'validation' };
  return { label: 'Action error', className: 'bad' };
}

function actionResultHtml(result, command, forcedState) {
  const state = forcedState || actionResultState(result || {});
  const meta = actionStateMeta(state, result || {});
  const classification = result?.classification || null;
  const safetyClass = classification?.safety_class || '';
  const classificationReason = classification?.why_not_auto_runnable || '';
  const message = result?.message || result?.error || classificationReason || '';
  const commandText = shortCommand(command || classification?.command || 'action', 180);
  const field = result?.field ? `<span class="command-result-field">${esc(result.field)}</span>` : '';
  const safety = safetyClass ? `<span class="command-result-classification">${esc(safetyClass)}</span>` : '';
  const stdout = result?.stdout ? `<pre>${esc(truncateActionOutput(result.stdout))}</pre>` : '';
  const stderr = result?.stderr ? `<pre class="stderr">${esc(truncateActionOutput(result.stderr))}</pre>` : '';
  const truncated = result?.output_truncated ? '<p class="command-result-truncated">Output was truncated by the action API.</p>' : '';
  return `<div class="command-result ${meta.className}" data-action-state="${esc(state)}">
    <div class="command-result-head">
      <strong>${esc(meta.label)}</strong>
      ${safety}${field}
      <code>${esc(commandText)}</code>
    </div>
    ${message ? `<p>${esc(message)}</p>` : ''}
    ${classificationReason && classificationReason !== message ? `<p>${esc(classificationReason)}</p>` : ''}
    ${stdout}${stderr}${truncated}
  </div>`;
}

function renderActionSurface(result, command, forcedState) {
  const html = actionResultHtml(result || {}, command, forcedState);
  for (const target of actionResultTargets()) {
    target.innerHTML = html;
  }
  return html;
}

function renderActionPending(command) {
  return renderActionSurface({ executed: false, message: 'Waiting for the approved command result.' }, command, 'pending');
}

function renderActionError({ message, field, command } = {}) {
  return renderActionSurface(
    { executed: false, validation: true, error: message || 'Action validation failed.', field: field || null },
    command || 'action',
    'validation_error',
  );
}

function renderActionResult(result, command) {
  return renderActionSurface(result || { executed: false, error: 'Action failed.' }, command);
}

async function runApprovedCommand(command, opts) {
  if (!command || /<[^>]+>/.test(command)) {
    const error = new Error('This action needs concrete command inputs first.');
    error.actionRendered = true;
    renderActionError({ message: error.message, field: 'command', command: command || 'action' });
    throw error;
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
  try {
    const resp = await fetch('/api/actions/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const payload = await resp.json();
    renderActionResult(payload, command);
    setTimeout(() => loadSnapshot(selectedProjectId), 500);
    return payload;
  } catch(err) {
    if (!err?.actionRendered) {
      renderActionError({ message: err.message || 'Action request failed.', command });
    }
    throw err;
  }
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
    if (!e?.actionRendered) renderActionError({ message: e.message || 'Action failed', command });
  }
}

// === ACTION RESULT UTILITIES ===
function rememberApprovedActionResult(result) {
  const message = `Action done: ${result?.action || 'executed'} on ${result?.task_id || 'task'}`;
  renderActionSurface({ executed: true, exit_code: 0, message }, result?.command || result?.action || 'approved action', 'succeeded');
  setTimeout(() => {
    const container = $('guided-action-result');
    if (container) container.innerHTML = '';
  }, 5000);
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

async function copyCommandFromButton(button, command) {
  const text = command || button?.dataset?.copyCommand || button?.dataset?.copySerialCommand || '';
  if (text && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text).catch(() => {});
  }
  const original = button?.textContent || 'Copy';
  if (button) {
    button.textContent = 'Copied';
    setTimeout(() => { button.textContent = original; }, 1200);
  }
}

function setupTaskSurfaceActions() {
  const closeButton = $('focus-close');
  if (closeButton) closeButton.addEventListener('click', closeFocus);

  document.addEventListener('click', async (e) => {
    const genericCopyButton = e.target.closest('[data-copy-command]');
    if (genericCopyButton) {
      e.preventDefault();
      e.stopPropagation();
      await copyCommandFromButton(genericCopyButton, genericCopyButton.dataset.copyCommand || '');
      return;
    }

    const copySerialButton = e.target.closest('[data-copy-serial-command]');
    if (copySerialButton) {
      e.preventDefault();
      e.stopPropagation();
      await copyCommandFromButton(copySerialButton, copySerialButton.dataset.copySerialCommand || '');
      return;
    }

    const openNextWorkerButton = e.target.closest('[data-open-next-worker-card]');
    if (openNextWorkerButton) {
      e.preventDefault();
      e.stopPropagation();
      const workerId = openNextWorkerButton.dataset.openNextWorkerCard || '';
      const cards = Array.from(document.querySelectorAll('#next-task-action-slot [data-worker-option-card]'));
      const card = cards.find(item => item?.dataset?.workerId === workerId) || null;
      if (card) {
        openSerialPacketPanel(card);
      } else {
        renderActionError({ message: 'Recommended worker card is not available in the launchpad.', field: 'worker_action', command: workerId || 'worker option' });
      }
      return;
    }

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

    const ideaCard = e.target.closest('[data-inspect-idea]');
    if (ideaCard && !e.target.closest('button,a,input,textarea,select,[data-command]')) {
      e.preventDefault();
      e.stopPropagation();
      const id = ideaCard.dataset.inspectIdea;
      if (id) openFocus('idea', id, {});
      return;
    }

    const createPacketButton = e.target.closest('[data-create-serial-packet]');
    if (createPacketButton) {
      e.preventDefault();
      e.stopPropagation();
      const panel = createPacketButton.closest('[data-serial-packet-panel]');
      try {
        const command = materializeSerialPacketCommand(panel?.dataset?.packetBaseCommand || '', serialPacketFormValues(panel));
        await runApprovedCommand(command, {});
      } catch(err) {
        if (!err?.actionRendered) renderActionError({ message: err.message || 'Serial packet creation failed', field: 'serial_packet', command: panel?.dataset?.packetBaseCommand || 'devflow agent serial-packet' });
      }
      return;
    }

    const workerOptionCard = e.target.closest('[data-worker-option-card]');
    if (workerOptionCard) {
      e.preventDefault();
      e.stopPropagation();
      openSerialPacketPanel(workerOptionCard);
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
        renderActionError({ message: 'Enter the shell command to run in the task workspace.', field: 'shell_command', command: `devflow task run ${taskId}` });
        input?.focus();
        return;
      }
      try {
        await runApprovedCommand(buildShellRunCommand(taskId, shellCommand, task), {});
      } catch(err) {
        if (!err?.actionRendered) renderActionError({ message: err.message || 'Shell run failed', command: `devflow task run ${taskId}` });
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
        renderActionError({ message: 'Enter the verification shell command.', field: 'verification_command', command: `devflow task verify ${taskId}` });
        input?.focus();
        return;
      }
      try {
        await runApprovedCommand(buildVerifyCommand(taskId, verifyCommand, task), {});
      } catch(err) {
        if (!err?.actionRendered) renderActionError({ message: err.message || 'Verification failed', command: `devflow task verify ${taskId}` });
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
        renderActionError({ message: 'Enter a concrete close reason.', field: 'close_reason', command: `devflow task close ${taskId}` });
        reasonInput?.focus();
        return;
      }
      try {
        await runApprovedCommand(buildCloseCommand(taskId, outcome, reason, task), {});
      } catch(err) {
        if (!err?.actionRendered) renderActionError({ message: err.message || 'Close failed', command: `devflow task close ${taskId}` });
      }
      return;
    }

    const classifyButton = e.target.closest('[data-idea-classify-submit]');
    if (classifyButton) {
      e.preventDefault();
      const ideaId = classifyButton.dataset.ideaClassifySubmit;
      const idea = findIdeaCard(ideaId);
      if (!idea) {
        setIdeaDetailStatus('Idea not found in current snapshot.', 'error');
        return;
      }
      try {
        await classifyIdeaFromDetail(idea);
      } catch(err) {
        setIdeaDetailStatus(shortCommand(err.message || 'Classification failed', 80), 'error');
      }
      return;
    }

    const parkButton = e.target.closest('[data-idea-park-submit]');
    if (parkButton) {
      e.preventDefault();
      const ideaId = parkButton.dataset.ideaParkSubmit;
      const idea = findIdeaCard(ideaId);
      if (!idea) {
        setIdeaDetailStatus('Idea not found in current snapshot.', 'error');
        return;
      }
      try {
        await _submitParkOrArchive(idea, 'park');
      } catch(err) {
        setIdeaDetailStatus(shortCommand(err.message || 'Park failed', 80), 'error');
      }
      return;
    }

    const archiveButton = e.target.closest('[data-idea-archive-submit]');
    if (archiveButton) {
      e.preventDefault();
      const ideaId = archiveButton.dataset.ideaArchiveSubmit;
      const idea = findIdeaCard(ideaId);
      if (!idea) {
        setIdeaDetailStatus('Idea not found in current snapshot.', 'error');
        return;
      }
      try {
        await _submitParkOrArchive(idea, 'archive');
      } catch(err) {
        setIdeaDetailStatus(shortCommand(err.message || 'Archive failed', 80), 'error');
      }
      return;
    }

    const brainstormButton = e.target.closest('[data-idea-brainstorm]');
    if (brainstormButton) {
      e.preventDefault();
      const ideaId = brainstormButton.dataset.ideaBrainstorm;
      if (!/^I-[0-9]{4}$/.test(ideaId)) return;
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
          return;
        }
        localStorage.setItem('devflow-brainstorm-session', data.session_id);
        brainstormSessionId = data.session_id;
        setIdeaDetailStatus('Session: ' + data.session_id, 'success', statusId);
        setActiveNav('brainstorm');
        closeFocus();
        await loadBrainstormTranscript(data.session_id);
        appendBrainstormMsg('system', 'Brainstorm session started from ' + ideaId + '. Next: add context or escalate to Spec when the idea is clear.', {});
        loadBrainstormSessions();
        refreshPipelineState();
        const input = $('brainstorm-message');
        if (input) input.focus();
      } catch(e) {
        setIdeaDetailStatus(e.message || 'Failed to start brainstorm.', 'error', statusId);
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
      return;
    }
  });

  document.addEventListener('input', (e) => {
    const packetInput = e.target.closest?.('[data-packet-allowed-files], [data-packet-verify-command]');
    if (!packetInput) return;
    updateSerialPacketPanelState(packetInput.closest('[data-serial-packet-panel]'));
  });

  document.addEventListener('keydown', (e) => {
    const workerOptionCard = e.target.closest?.('[data-worker-option-card]');
    if (workerOptionCard && ['Enter', ' ', 'Spacebar'].includes(e.key) && !e.target.closest?.('button,a,input,textarea,select')) {
      e.preventDefault();
      openSerialPacketPanel(workerOptionCard);
      return;
    }
    const ideaCard = e.target.closest?.('[data-inspect-idea]');
    if (!ideaCard || !['Enter', ' '].includes(e.key)) return;
    e.preventDefault();
    const id = ideaCard.dataset.inspectIdea;
    if (id) openFocus('idea', id, {});
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
  renderIdeaGreenhouse(snapshot?.idea_greenhouse || null);
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
  setupIdeaGreenhouse();
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
