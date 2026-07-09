from __future__ import annotations


PIPELINE_JS = """// === PIPELINE ===
let pipelineState = { stages: [] };

async function refreshPipelineState() {
  try {
    const resp = await fetch(`/api/brainstorm/transcript?session_id=${encodeURIComponent(brainstormSessionId)}`);
    const data = await resp.json();
    if (data.session_id || data.pipeline?.session_id) {
      setActiveBrainstormSession(data.session_id || data.pipeline.session_id);
    }
    pipelineState = data.pipeline && Array.isArray(data.pipeline.stages)
      ? data.pipeline
      : { session_id: data.session_id || brainstormSessionId, stages: [] };
  } catch(e) { /* ignore */ }
  renderPipeline();
}

function isPipelineStageComplete(stage) {
  if (stage?.complete === true || stage?.done === true) return true;
  const status = String(stage?.status || '').toLowerCase();
  return ['complete', 'accepted', 'passed', 'draft'].includes(status);
}

function getPipelineFirstIncompleteIndex(state) {
  const stages = state?.stages || [];
  return stages.findIndex(stage => !isPipelineStageComplete(stage));
}

function getPipelinePrimaryStage(state) {
  if (state?.primary_stage_id) return state.primary_stage_id;
  const stages = state?.stages || [];
  const next = stages.find(stage => !isPipelineStageComplete(stage));
  const implementation = stages.find(stage => stage.id === 'implementation');
  if (!next && implementation && isPipelineStageComplete(implementation) && !(state?.created_task_ids || []).length) return 'task';
  if (!next) return null;
  if (next.id === 'brainstorm') return null;
  return next.id || null;
}

function getNextStageLabel(stageId) {
  if (stageId === 'spec') return 'Generate Spec →';
  if (stageId === 'plan') return 'Generate Plan →';
  if (stageId === 'implementation') return 'Implement →';
  if (stageId === 'task') return 'Create Task →';
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

function getPipelineStageById(state, stageId) {
  return (state?.stages || []).find(stage => stage.id === stageId) || null;
}

function getPipelineCurrentStage(state) {
  const primaryStageId = getPipelinePrimaryStage(state);
  if (primaryStageId) return getPipelineStageById(state, primaryStageId);
  const stages = state?.stages || [];
  return stages.find(stage => !isPipelineStageComplete(stage)) || stages[stages.length - 1] || null;
}

function getPipelineStageEvidencePath(stage) {
  if (!stage) return '';
  if (stage.artifact_path) return stage.artifact_path;
  if (Array.isArray(stage.evidence_paths) && stage.evidence_paths.length) return stage.evidence_paths[0];
  return '';
}

function getPipelineNearestEvidencePath(state) {
  const stages = state?.stages || [];
  if (!stages.length) return '';
  const activeStage = getPipelineCurrentStage(state);
  const activeIndex = Math.max(0, stages.findIndex(stage => stage.id === activeStage?.id));
  for (let idx = activeIndex; idx >= 0; idx -= 1) {
    const path = getPipelineStageEvidencePath(stages[idx]);
    if (path) return path;
  }
  for (const stage of stages) {
    const path = getPipelineStageEvidencePath(stage);
    if (path) return path;
  }
  return '';
}

function currentBrainstormProfileLabel() {
  const selected = selectedProfileId
    ? availableAgents.find(agent => agent.id === selectedProfileId)
    : null;
  return selected?.label || selected?.model || $('model-selector-label')?.textContent || 'DeepSeek V4 Flash Free';
}

function getPipelinePrimaryContext(state) {
  const currentStage = getPipelineCurrentStage(state);
  return {
    session: state?.session_id || brainstormSessionId || 'New brainstorm',
    profile: currentBrainstormProfileLabel(),
    currentStage: currentStage?.label || sentenceCase(currentStage?.id || 'brainstorm'),
    nextAction: getPrimaryActionLabel(state),
    evidencePath: getPipelineNearestEvidencePath(state) || 'No artifact yet',
  };
}

function appendPipelineContextItem(container, className, label, value) {
  const item = document.createElement('div');
  item.className = 'pipeline-context-item ' + className;
  const labelEl = document.createElement('span');
  labelEl.textContent = label;
  const valueEl = document.createElement('strong');
  valueEl.textContent = value;
  item.appendChild(labelEl);
  item.appendChild(valueEl);
  container.appendChild(item);
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
  const context = getPipelinePrimaryContext(pipelineState);
  const contextEl = document.createElement('div');
  contextEl.className = 'pipeline-primary-context';
  appendPipelineContextItem(contextEl, 'pipeline-session', 'Active brainstorm session', context.session);
  appendPipelineContextItem(contextEl, 'pipeline-profile', 'Model/profile', context.profile);
  appendPipelineContextItem(contextEl, 'pipeline-current-stage', 'Current stage', context.currentStage);
  appendPipelineContextItem(contextEl, 'pipeline-next-action', 'Next action', context.nextAction);
  appendPipelineContextItem(contextEl, 'pipeline-evidence-path', 'Evidence/artifact', context.evidencePath);
  primaryAction.appendChild(contextEl);
  container.appendChild(primaryAction);

  const firstIncompleteIndex = getPipelineFirstIncompleteIndex(pipelineState);
  pipelineState.stages.forEach((stage, idx) => {
    const isComplete = isPipelineStageComplete(stage);
    const isActive = !isComplete && idx === firstIncompleteIndex;
    const isLocked = !isComplete && !isActive;

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

    const evidencePath = getPipelineStageEvidencePath(stage);
    if (evidencePath) {
      const evidenceEl = document.createElement('p');
      evidenceEl.className = 'step-evidence';
      evidenceEl.textContent = 'Evidence: ' + evidencePath;
      content.appendChild(evidenceEl);
    }
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

async function createTaskFromAcceptedImplementation(control) {
  const btn = control || null;
  const originalText = btn?.textContent || '';
  const defaultTitle = snapshot?.workbench?.artifact_paths?.implement
    ? 'Workbench implementation'
    : 'Brainstorm implementation';
  const title = window.prompt('Task title', defaultTitle);
  if (!title || !title.trim()) return;
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Creating task...';
  }
  try {
    const bridgePayload = await createTaskFromBrainstorm(
      brainstormSessionId,
      title.trim(),
      { definition_of_done: currentBrainstormDefinitionOfDone() || undefined }
    );
    if (!bridgePayload || !bridgePayload.task_id) {
      throw new Error('Brainstorm task bridge did not return a task id');
    }
    const launchpad = bridgePayload.launchpad || {};
    const contextPath = bridgePayload.context_path || '.devflow/workspaces/' + bridgePayload.task_id + '/implementation-context.md';
    appendBrainstormMsg('system', `Task created: ${bridgePayload.task_id}. Implementation context target: ${contextPath}. Next: ${launchpad.action_label || 'use the Next Task launchpad'}.`, {});
    await loadSnapshot(selectedProjectId);
    selectTaskInLaunchpad(bridgePayload.task_id, { focusShell: launchpad.focus_shell !== false });
  } catch(e) {
    appendBrainstormMsg('system', 'Task creation error: ' + (e.message || 'unknown'), { kind: 'provider_error' });
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }
}

async function runPipelinePrimaryStage(stage, control) {
  if (!stage) return;
  if (stage === 'implementation') {
    await runWorkbenchImplement(control || null);
    return;
  }
  if (stage === 'task') {
    await createTaskFromAcceptedImplementation(control || null);
    return;
  }
  const btn = control || null;
  const originalText = btn?.textContent || '';
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Escalating...';
  }
  const useModel = useModelForBrainstormStage(stage);
  if (useModel) {
    const modelLabel = currentBrainstormProfileLabel();
    appendBrainstormMsg('assistant', '', { thinking: true });
    appendBrainstormMsg('system', `Generating ${stage} with ${modelLabel}...`, {});
  }
  try {
    const payload = await escalateBrainstormStage(stage, useModel);
    if (useModel) removeThinkingIndicator();
    if (payload.status === 'ready') {
      const stageLabel = payload.stage ? payload.stage.charAt(0).toUpperCase() + payload.stage.slice(1) : 'Stage';
      const detail = pipelineDetailFromPayload(payload);
      const taskAction = taskActionFromPipelinePayload(payload);
      if (payload.stage === 'implementation' && taskAction) {
        appendBrainstormMsg('system', 'Implementation artifact is ready. Use Create Task after builder-judge acceptance.', {});
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
    } else if (payload.error) {
      appendBrainstormMsg('system', payload.error, { kind: 'provider_error' });
    }
    await loadSnapshot(selectedProjectId);
    await refreshPipelineState();
    await loadBrainstormSessions();
  } catch(e) {
    removeThinkingIndicator();
    appendBrainstormMsg('system', 'Escalation failed: ' + (e.message || 'unknown error'), { kind: 'provider_error' });
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }
}

function setupPipelineButtons(scope) {
  const root = scope || document;

  root.querySelectorAll('[data-pipeline-primary-action]').forEach(btn => {
    if (btn.dataset.pipelineBound === '1') return;
    btn.dataset.pipelineBound = '1';
    btn.addEventListener('click', async () => {
      const stage = getPipelinePrimaryStage(pipelineState);
      if (!stage) return;
      await runPipelinePrimaryStage(stage, btn);
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
"""
