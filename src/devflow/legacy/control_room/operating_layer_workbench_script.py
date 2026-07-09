from __future__ import annotations


WORKBENCH_JS = """// === UNIFIED CHAT WORKBENCH ===
const WORKBENCH_STAGES = ['idea', 'brainstorm', 'spec', 'plan', 'implement'];

function workbenchStageLabel(stage) {
  const labels = {
    idea: 'Idea',
    brainstorm: 'Brainstorm',
    spec: 'Spec',
    plan: 'Plan',
    implement: 'Implement',
  };
  return labels[stage] || sentenceCase(stage);
}

function workbenchStageRank(stage) {
  const idx = WORKBENCH_STAGES.indexOf(stage);
  return idx < 0 ? 0 : idx;
}

function gateTone(item) {
  if (item?.ready) return 'good';
  const status = String(item?.status || '').toLowerCase();
  if (status === 'missing' || status === 'blocked') return 'warn';
  return 'neutral';
}

function renderWorkbenchGateAction(item) {
  const action = item?.setup_action || null;
  if (!action) return '';
  if (action.command) {
    return `<button class="btn btn-sm btn-readonly" type="button" data-copy-command="${esc(action.command)}" data-copy-kind="terminal_command" title="${esc(action.detail || '')}">Copy setup</button>`;
  }
  if (action.gate === 'ponytail') {
    return `<button class="btn btn-sm btn-secondary" type="button" data-workbench-setup-gate="ponytail" title="${esc(action.detail || '')}">Record approval</button>`;
  }
  return '';
}

function renderWorkbench(workbench) {
  const stagePath = $('workbench-stage-path');
  const gateStrip = $('workbench-gate-strip');
  const nextAction = $('workbench-next-action');
  const result = $('workbench-implement-result');
  if (!stagePath || !gateStrip || !nextAction) return;
  const data = workbench || {};
  const activeStage = data.stage || 'idea';
  const activeRank = workbenchStageRank(activeStage);
  const artifactPaths = data.artifact_paths || {};

  stagePath.innerHTML = WORKBENCH_STAGES.map((stage, index) => {
    const state = index < activeRank ? 'done' : index === activeRank ? 'active' : 'pending';
    const path = artifactPaths[stage] || '';
    return `<span class="workbench-stage-chip ${state}" data-workbench-stage="${esc(stage)}" title="${esc(path || workbenchStageLabel(stage))}">
      <strong>${esc(workbenchStageLabel(stage))}</strong>
      ${path ? `<code>${esc(path)}</code>` : ''}
    </span>`;
  }).join('');

  const gates = Array.isArray(data.gate_status?.items) ? data.gate_status.items : [];
  gateStrip.innerHTML = gates.map(item => {
    const tone = gateTone(item);
    return `<article class="workbench-gate-card ${tone}">
      <div>
        <strong>${esc(item.label || item.id || 'Gate')}</strong>
        <span>${esc(item.detail || item.status || '')}</span>
        <em>${esc(item.source || '')}</em>
      </div>
      ${renderWorkbenchGateAction(item)}
    </article>`;
  }).join('') || '<div class="workbench-gate-card neutral"><div><strong>Gates</strong><span>No gate data yet.</span></div></div>';

  const canImplement = activeStage === 'implement' && data.gate_status?.ready && data.session_id;
  const createProject = !data.project_id;
  const activeLoops = Array.isArray(data.active_loop_ids) ? data.active_loop_ids : [];
  const loopHtml = activeLoops.length
    ? `<button class="btn btn-sm btn-secondary" type="button" data-workbench-open-loop="${esc(activeLoops[0])}">Open latest loop</button>`
    : '';
  nextAction.innerHTML = `<div>
    <span>Next action</span>
    <strong>${esc(data.next_action || 'Capture an idea or continue Brainstorm.')}</strong>
    ${data.session_id ? `<code>${esc(data.session_id)}</code>` : ''}
  </div>
  <div class="workbench-next-buttons">
    ${createProject ? '<button class="btn btn-sm btn-secondary" type="button" data-workbench-create-project>Make this real</button>' : ''}
    ${canImplement ? '<button class="btn btn-sm btn-primary" type="button" data-workbench-implement>Implement</button>' : ''}
    ${loopHtml}
  </div>`;

  if (result && !result.dataset.preserve) {
    result.innerHTML = lastWorkbenchLoopId
      ? `<span>Latest implementation loop</span><button class="btn btn-sm btn-secondary" type="button" data-workbench-open-loop="${esc(lastWorkbenchLoopId)}">${esc(lastWorkbenchLoopId)}</button>`
      : '';
  }
}

async function recordPonytailApproval(button) {
  if (!window.confirm('Record Ponytail plugin approval after installing the DietrichGebert/ponytail Codex plugin and reviewing lifecycle hooks?')) {
    return;
  }
  if (button) button.disabled = true;
  try {
    const body = {
      gate: 'ponytail',
      human_approved: true,
      approval_phrase: ACTION_APPROVAL_PHRASE,
      approved_source: 'DietrichGebert/ponytail',
      reviewed_lifecycle_hooks: true,
    };
    if (selectedProjectId) body.project = selectedProjectId;
    const resp = await fetch('/api/gates/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    const target = $('workbench-implement-result');
    if (target) {
      target.dataset.preserve = '1';
      target.innerHTML = `<div class="workbench-result-card ${resp.ok ? 'good' : 'warn'}"><strong>${esc(data.status || 'Ponytail')}</strong><span>${esc(data.message || data.error || '')}</span></div>`;
    }
    await loadSnapshot(selectedProjectId);
  } catch(e) {
    const target = $('workbench-implement-result');
    if (target) {
      target.dataset.preserve = '1';
      target.innerHTML = `<div class="workbench-result-card warn"><strong>Ponytail setup failed</strong><span>${esc(e.message || 'unknown error')}</span></div>`;
    }
  } finally {
    if (button) button.disabled = false;
  }
}

async function createWorkbenchProject() {
  const name = window.prompt('Project name');
  if (!name || !name.trim()) return;
  const target = $('workbench-implement-result');
  if (target) {
    target.dataset.preserve = '1';
    target.innerHTML = '<div class="workbench-result-card neutral"><strong>Creating project...</strong></div>';
  }
  try {
    const resp = await fetch('/api/workbench/project', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() }),
    });
    const data = await resp.json();
    if (target) {
      const project = data.project || {};
      target.innerHTML = `<div class="workbench-result-card ${resp.ok ? 'good' : 'warn'}"><strong>${esc(resp.ok ? 'Project created' : 'Project blocked')}</strong><span>${esc(data.error || project.project_id || '')}</span>${project.path ? `<code>${esc(project.path)}</code>` : ''}</div>`;
    }
    if (resp.ok && data.project?.project_id) {
      selectedProjectId = data.project.project_id;
      await loadSnapshot(selectedProjectId);
    }
  } catch(e) {
    if (target) target.innerHTML = `<div class="workbench-result-card warn"><strong>Project failed</strong><span>${esc(e.message || 'unknown error')}</span></div>`;
  }
}

async function runWorkbenchImplement(button) {
  const workbench = snapshot?.workbench || {};
  const sessionId = workbench.session_id || brainstormSessionId;
  if (!sessionId) {
    renderActionError({ message: 'Workbench needs an active brainstorm session first.', command: 'workbench implement' });
    return;
  }
  const builderModel = $('bj-builder-model')?.value || selectedProfileId || '';
  const judgeModel = $('bj-judge-model')?.value || '';
  const target = $('workbench-implement-result');
  if (target) {
    target.dataset.preserve = '1';
    target.innerHTML = '<div class="workbench-result-card neutral"><strong>Sending to builder-judge...</strong><span>Implement will write implementation.md only after the judge passes it.</span></div>';
  }
  const original = button?.textContent || '';
  if (button) {
    button.disabled = true;
    button.textContent = 'Running...';
  }
  try {
    const body = {
      session_id: sessionId,
      definition_of_done: currentBrainstormDefinitionOfDone() || undefined,
      builder_profile_id: builderModel || undefined,
      judge_profile_id: judgeModel || undefined,
      pass_threshold: parseInt($('bj-pass-threshold')?.value || '85', 10),
      max_rounds: parseInt($('bj-max-rounds')?.value || '3', 10),
      async: true,
    };
    if (selectedProjectId) body.project = selectedProjectId;
    const resp = await fetch('/api/workbench/implement', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) {
      if (target) target.innerHTML = `<div class="workbench-result-card warn"><strong>Implement blocked</strong><span>${esc(data.error || 'Gate evidence is missing.')}</span></div>`;
      return;
    }
    lastWorkbenchLoopId = data.loop_id || '';
    if (lastWorkbenchLoopId) localStorage.setItem('devflow-workbench-loop-id', lastWorkbenchLoopId);
    if (target) {
      target.innerHTML = `<div class="workbench-result-card good"><strong>Builder-judge started</strong><span>${esc(data.next_action || 'Loop running.')}</span><code>${esc(data.loop_id || '')}</code></div>`;
    }
    if (data.loop_id) await pollBuilderJudgeLoop(data.loop_id);
    await loadSnapshot(selectedProjectId);
    await refreshPipelineState();
  } catch(e) {
    if (target) target.innerHTML = `<div class="workbench-result-card warn"><strong>Implement failed</strong><span>${esc(e.message || 'unknown error')}</span></div>`;
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

function setupWorkbenchActions() {
  document.addEventListener('click', async (e) => {
    const gateButton = e.target.closest('[data-workbench-setup-gate]');
    if (gateButton) {
      e.preventDefault();
      e.stopPropagation();
      if (gateButton.dataset.workbenchSetupGate === 'ponytail') {
        await recordPonytailApproval(gateButton);
      }
      return;
    }

    const createButton = e.target.closest('[data-workbench-create-project]');
    if (createButton) {
      e.preventDefault();
      e.stopPropagation();
      await createWorkbenchProject();
      return;
    }

    const implementButton = e.target.closest('[data-workbench-implement]');
    if (implementButton) {
      e.preventDefault();
      e.stopPropagation();
      await runWorkbenchImplement(implementButton);
      return;
    }

    const loopButton = e.target.closest('[data-workbench-open-loop]');
    if (loopButton) {
      e.preventDefault();
      e.stopPropagation();
      const loopId = loopButton.dataset.workbenchOpenLoop || lastWorkbenchLoopId || '';
      if (loopId) {
        document.querySelector('[data-tools-tab="builder-judge"]')?.click();
        const resp = await fetch(`/api/builder-judge/status?loop_id=${encodeURIComponent(loopId)}`).catch(() => null);
        const data = resp ? await resp.json().catch(() => null) : null;
        if (resp?.ok && data) renderBJRunResult(data);
        document.querySelector('#builder-judge-section')?.scrollIntoView({ block: 'start', behavior: 'smooth' });
      }
    }
  });
}
"""
