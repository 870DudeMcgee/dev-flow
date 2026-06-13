from __future__ import annotations

APP_JS = """let snapshot = null;
let selectedTaskId = null;
let selectedGoalSelection = null;
let selectedMapNode = null;
let selectedProjectId = null;
let selectedProjectName = null;
let selectedProjectPathStatus = null;
let selectedActionCommand = null;
let actionRunState = null;
let lastApprovedActionResult = null;
let verificationCommandInputs = {};
let promotionContextInputs = {};
let selectedSpecDocumentKey = null;
let agentsExpanded = false;
let globalFilter = "";
let currentPage = "orchestrator";

const APPROVAL_PHRASE = "I approve this exact Dev-Flow command";
const laneLimit = ["blocked", "running", "needs_verification", "ready_to_promote", "new"];
const pageSections = {
  orchestrator: ["orchestrator", "command"],
  map: ["command", "map", "context"],
  lanes: ["command", "lanes", "context"],
  goals: ["command", "goals", "context"],
  specs: ["command", "specs"],
  gates: ["command", "gates", "context"],
  attention: ["command", "attention", "inbox"],
  inbox: ["command", "inbox", "attention"],
  projects: ["command", "projects"],
  actions: ["command", "actions", "context"],
  evidence: ["command", "evidence", "context"],
  promotion: ["command", "promotion", "context"],
};
const pageNames = {
  orchestrator: "Overview",
  map: "Map",
  lanes: "Workers",
  goals: "Goals",
  specs: "Specs",
  gates: "Progress",
  attention: "Alerts",
  inbox: "Inbox",
  projects: "Projects",
  actions: "Actions",
  evidence: "Evidence",
  promotion: "Review",
};
const sectionState = {
  actions: "collapsed",
  inbox: "collapsed",
  goals: "collapsed",
  specs: "collapsed",
  gates: "collapsed",
  promotion: "collapsed",
  evidence: "collapsed",
};

async function loadSnapshot(projectId = selectedProjectId) {
  const url = projectId ? `/api/snapshot?project=${encodeURIComponent(projectId)}` : "/api/snapshot";
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ error: "Snapshot unavailable" }));
    selectedProjectId = null;
    selectedProjectName = null;
    selectedProjectPathStatus = null;
    throw new Error(payload.error || "Snapshot unavailable");
  }
  snapshot = await response.json();
  if (selectedTaskId && !taskById(selectedTaskId)) selectedTaskId = null;
  if (selectedGoalSelection && !goalSelectionPayload()) selectedGoalSelection = null;
  selectedTaskId = selectedTaskId || snapshot.focus_task_id || firstVisibleTaskId();
  render();
}

function byId(id) {
  return document.getElementById(id);
}

function taskById(id) {
  return snapshot.tasks.find((task) => task.id === id);
}

function goalById(goalId) {
  return (snapshot.goal_board || []).find((goal) => goal.goal_id === goalId);
}

function goalSelectionPayload() {
  if (!selectedGoalSelection) return null;
  const goal = goalById(selectedGoalSelection.goalId);
  if (!goal) return null;
  if (selectedGoalSelection.type === "goal") return { type: "goal", goal, item: goal };
  const batches = [
    ...(goal.parallel_batches || []),
    ...(goal.worker_batches || []),
    ...(goal.verification_batches || []),
  ];
  if (selectedGoalSelection.type === "batch") {
    const batch = batches.find((item) => item.batch_id === selectedGoalSelection.id);
    return batch ? { type: "batch", goal, item: batch } : null;
  }
  const lane = (goal.lanes || []).find((item) => item.slice_id === selectedGoalSelection.id);
  return lane ? { type: "lane", goal, item: lane } : null;
}

function selectedGoalTaskIds() {
  const payload = goalSelectionPayload();
  if (!payload) return [];
  if (payload.type === "goal") {
    return Array.from(new Set((payload.goal.lanes || []).flatMap((lane) => lane.linked_task_ids || [])));
  }
  return Array.from(new Set([...(payload.item.task_ids || []), ...(payload.item.linked_task_ids || [])]));
}

function selectedGoalTasks() {
  const ids = new Set(selectedGoalTaskIds());
  return snapshot.tasks.filter((task) => ids.has(task.id));
}

function selectedGoalGateReceipts() {
  const ids = new Set(selectedGoalTaskIds());
  return filterGateReceipts(snapshot.gate_receipts.filter((gate) => ids.has(gate.task_id)));
}

function selectedGoalEvidence() {
  const ids = new Set(selectedGoalTaskIds());
  return snapshot.evidence.filter((item) => ids.has(item.task_id));
}

function scopedFocusTaskId() {
  const tasks = visibleTasksForMapScope();
  return tasks.length ? tasks[0].id : null;
}

function visibleTasksForMapScope() {
  let tasks = snapshot.tasks;
  if (selectedMapNode === "workers") return applyGlobalTaskFilter(snapshot.tasks.filter((task) => laneLimit.includes(task.lane)));
  if (selectedMapNode === "gates") {
    const ids = new Set(visibleGateReceipts().map((gate) => gate.task_id));
    tasks = snapshot.tasks.filter((task) => ids.has(task.id));
    return applyGlobalTaskFilter(tasks);
  }
  if (selectedMapNode === "promotion") {
    const ids = new Set(snapshot.promotion_desk.map((item) => item.task_id));
    tasks = snapshot.tasks.filter((task) => ids.has(task.id));
    return applyGlobalTaskFilter(tasks);
  }
  if (selectedMapNode === "inbox") {
    const ids = new Set((snapshot.inbox || []).map((item) => item.task_id).filter(Boolean));
    tasks = snapshot.tasks.filter((task) => ids.has(task.id));
    return applyGlobalTaskFilter(tasks);
  }
  return applyGlobalTaskFilter(tasks);
}

function applyGlobalTaskFilter(tasks) {
  if (!globalFilter.trim()) return tasks;
  return tasks.filter((task) => taskMatchesFilter(task, globalFilter));
}

function taskMatchesFilter(task, query) {
  const haystack = [
    task.id,
    task.title,
    task.status,
    task.display_status,
    task.lane,
    task.worker,
    task.workspace,
    task.verification_status,
    task.latest,
    task.log_path,
    task.result_path,
  ].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes(query.trim().toLowerCase());
}

function filteredTaskIds() {
  return new Set(applyGlobalTaskFilter(snapshot.tasks).map((task) => task.id));
}

function filterGateReceipts(gates) {
  if (!globalFilter.trim()) return gates;
  const ids = filteredTaskIds();
  return gates.filter((gate) => ids.has(gate.task_id));
}

function visibleGateReceipts() {
  const selectedIds = selectedGoalTaskIds();
  const selectedSet = new Set(selectedIds);
  if (selectedIds.length) {
    return filterGateReceipts(snapshot.gate_receipts.filter((gate) => selectedSet.has(gate.task_id)));
  }
  if (selectedMapNode === "gates") return filterGateReceipts(snapshot.gate_receipts);
  if (selectedMapNode === "promotion") {
    const ids = new Set(snapshot.promotion_desk.map((item) => item.task_id));
    return filterGateReceipts(snapshot.gate_receipts.filter((gate) => ids.has(gate.task_id)));
  }
  return filterGateReceipts(snapshot.gate_receipts);
}

function visibleEvidence() {
  const selectedIds = selectedGoalTaskIds();
  const selectedSet = new Set(selectedIds);
  if (selectedIds.length) return snapshot.evidence.filter((item) => selectedSet.has(item.task_id));
  if (["workers", "gates", "promotion", "inbox"].includes(selectedMapNode)) {
    const ids = new Set(visibleTasksForMapScope().map((task) => task.id));
    return snapshot.evidence.filter((item) => ids.has(item.task_id));
  }
  return (snapshot.evidence || []);
}

function firstVisibleTaskId() {
  const visible = new Set(laneLimit);
  const task = applyGlobalTaskFilter(snapshot.tasks).find((item) => visible.has(item.lane));
  return task ? task.id : null;
}

function repoLabel(path) {
  const parts = String(path || "").split("/").filter(Boolean);
  return parts[parts.length - 1] || path || "Repository";
}

function render() {
  if (!snapshot) return;
  currentPage = normalizePage(currentPage);
  byId("repo-label").textContent = selectedProjectId ? "Selected Project" : "Repository";
  byId("repo-title").textContent = repoLabel(snapshot.project.root);
  byId("repo-title").title = snapshot.project.root;
  byId("branch-pill").textContent = `branch ${snapshot.project.branch || "unknown"}`;
  byId("tree-pill").textContent = snapshot.project.working_tree === "clean"
    ? "all systems operational"
    : `tree ${snapshot.project.working_tree || "unknown"}`;
  byId("total-tasks").textContent = snapshot.health.total_tasks;
  byId("active-tasks").textContent = snapshot.health.active_tasks;
  byId("blocked-tasks").textContent = snapshot.health.blocked_tasks;
  byId("verify-tasks").textContent = snapshot.health.needs_verification;
  byId("next-action").textContent = (snapshot.next_action && snapshot.next_action.command) || "None";
  renderOrchestrator();
  renderGlobalFilterState();
  renderOperatingMap();
  renderContextBar();
  renderLanes();
  renderInspector();
  renderActions();
  renderGoalBoard();
  renderSpecs();
  renderGates();
  renderProjects();
  renderInbox();
  renderQuestions();
  renderPromotion();
  renderEvidence();
  renderAttention();
  applySectionState();
  applyPageVisibility();
  updateActiveNav(currentSection());
}

function renderOperatingMap() {
  const nodes = operatingMapNodes();
  byId("map-status").textContent = selectedMapNode ? `Scoped: ${selectedMapNode}` : mapStatus(nodes);
  const list = byId("map-list");
  list.innerHTML = "";
  nodes.forEach((node) => {
    const anchor = document.createElement("a");
    anchor.className = `map-node ${node.tone} ${selectedMapNode === node.key ? "selected" : ""}`;
    anchor.href = node.href;
    anchor.setAttribute("aria-label", `${node.label}: ${node.value}, ${node.detail}`);
    anchor.setAttribute("aria-current", selectedMapNode === node.key ? "true" : "false");
    anchor.innerHTML = `
      <span>${escapeHtml(node.label)}</span>
      <strong>${escapeHtml(node.value)}</strong>
      <p>${escapeHtml(node.detail)}</p>
    `;
    anchor.addEventListener("click", (event) => {
      event.preventDefault();
      selectedMapNode = selectedMapNode === node.key ? null : node.key;
      selectedGoalSelection = null;
      selectedTaskId = scopedFocusTaskId() || selectedTaskId;
      render();
      document.querySelector(node.href)?.scrollIntoView({ block: "start" });
    });
    list.appendChild(anchor);
  });
}

function renderOrchestrator() {
  const goal = currentOrchestratorGoal();
  const readyBatches = goal
    ? (goal.ready_parallel_batch_count || 0)
      + (goal.ready_worker_batch_count || 0)
      + (goal.ready_verification_batch_count || 0)
    : 0;
  const blocked = goal ? (goal.blocked_lane_count || 0) : snapshot.health.blocked_tasks;
  const queue = goal ? goal.total_slices : snapshot.health.total_tasks;
  const directive = goal
    ? goal.next_action || snapshot.next_action.reason || "No current directive"
    : snapshot.next_action.reason || "No current goal is projected yet";
  const command = goal && goal.next_action ? goal.next_action : snapshot.next_action.command || "None";
  byId("orchestrator-goal-title").textContent = goal ? goal.title : repoLabel(snapshot.project.root);
  byId("orchestrator-directive").textContent = directive;
  byId("orchestrator-command").textContent = command;
  byId("orchestrator-queue").textContent = queue || 0;
  byId("orchestrator-ready").textContent = readyBatches;
  byId("orchestrator-blocked").textContent = blocked || 0;
  byId("orchestrator-evidence").textContent = visibleEvidence().length;
  byId("orchestrator-goal-id").textContent = goal ? goal.goal_id : "none";
  byId("orchestrator-freshness").textContent = (snapshot.freshness && snapshot.freshness.status) ? snapshot.freshness.status : "unknown";
  byId("orchestrator-sync").textContent = (snapshot.warnings && snapshot.warnings.length) ? "Needs review" : "Uplink synced";
  byId("orchestrator-time").textContent = shortTime(snapshot.generated_at);
  byId("orchestrator-health-label").textContent = blocked ? "Attention" : readyBatches ? "Ready" : "Nominal";
  renderOrchestratorAgentProgress(goal);
  renderOrchestratorHealthBars(goal);
  renderMissionFeed(goal);
}

function currentOrchestratorGoal() {
  const selected = goalSelectionPayload();
  if (selected) return selected.goal;
  const enrichGoal = (goal) => {
    if (!goal) return null;
    const card = (snapshot.goals || []).find((item) => item.goal_id === goal.goal_id);
    if (card && (!goal.title || goal.title === goal.goal_id)) return { ...goal, title: card.title || goal.title };
    return goal;
  };
  if (snapshot.focus_goal_id) {
    const focus = goalById(snapshot.focus_goal_id);
    if (focus) return enrichGoal(focus);
    const focusCard = (snapshot.goals || []).find((item) => item.goal_id === snapshot.focus_goal_id);
    if (focusCard) return focusCard;
  }
  return enrichGoal((snapshot.goal_board || [])[0]) || (snapshot.goals || [])[0] || null;
}

function renderOrchestratorAgentProgress(goal) {
  const list = byId("orchestrator-agent-progress");
  const count = byId("agent-progress-count");
  if (!list || !count) return;
  const summaries = snapshot.worker_activity || [];
  count.textContent = `${summaries.length} ${summaries.length === 1 ? "worker" : "workers"}`;
  list.innerHTML = "";
  summaries.forEach((agent) => {
    const progress = agent.verified_percent || 0;
    const state = agent.state_class || "idle";
    const outputVolume = agent.recent_output_count || 0;
    const row = document.createElement("button");
    row.type = "button";
    row.className = `agent-progress-row ${state}`;
    row.setAttribute("role", "listitem");
    row.setAttribute("aria-label", `${agent.name}: ${agent.state}, ${progress}% complete, ${agent.task_count} tasks, ${outputVolume} recent outputs`);
    row.innerHTML = `
      <span class="agent-progress-code">${escapeHtml(agent.code)}</span>
      <span class="agent-progress-main">
        <span class="agent-progress-top">
          <strong>${escapeHtml(agent.name)}</strong>
          <em>${escapeHtml(agent.state)}</em>
        </span>
        <span class="agent-progress-track" aria-hidden="true"><i style="--progress:${progress}%"></i></span>
        <span class="agent-progress-meta">
          <span>${progress}% complete</span>
          <span>${agent.task_count} tasks</span>
          <span>${outputVolume} output</span>
        </span>
      </span>
    `;
    row.addEventListener("click", () => {
      selectedMapNode = "workers";
      selectedGoalSelection = null;
      selectedTaskId = agent.first_task_id || selectedTaskId;
      agentsExpanded = true;
      render();
      byId("lanes")?.scrollIntoView({ block: "start" });
    });
    list.appendChild(row);
  });
}

function agentProgressState(agent, tasks) {
  if (agent.laneName === "blocked" && tasks.length) return "blocked";
  if (tasks.some((task) => isFailedTask(task))) return "blocked";
  if (tasks.length && tasks.every((task) => isVerifiedOrReadyTask(task))) return "complete";
  if (agent.state === "Running") return "active";
  return "idle";
}

function agentProgressPercent(agent, tasks) {
  if (!tasks.length) return 0;
  const complete = tasks.filter((task) => isVerifiedOrReadyTask(task)).length;
  const running = tasks.filter((task) => laneLimit.includes(task.lane) && task.lane !== "closed").length;
  const eventBoost = Math.min(20, tasks.reduce((total, task) => total + ((task.detail && task.detail.recent_events) ? task.detail.recent_events.length : 0), 0) * 2);
  return Math.max(12, Math.min(100, Math.round((complete / tasks.length) * 76 + (running ? 18 : 8) + eventBoost)));
}

function normalizedWorker(worker) {
  const value = String(worker || "").trim();
  if (!value || value === "unassigned" || value === "unknown") return null;
  return value;
}

function workerProfile(worker) {
  const profiles = {
    shell: {
      code: "SH",
      name: "Shell worker",
      description: "Runs the command DevFlow was given inside the task workspace.",
      tone: "violet",
    },
    "devflow-manual-codex-worker": {
      code: "CDX",
      name: "Manual Codex worker",
      description: "A human-launched Codex handoff that writes task evidence back to DevFlow.",
      tone: "blue",
    },
    "qwopus-implementer": {
      code: "QWO",
      name: "Qwopus implementer",
      description: "Local Ollama worker evidence for implementation proposals.",
      tone: "mint",
    },
    "qwen-planner": {
      code: "QWN",
      name: "Local Qwen planner",
      description: "Local Ollama planning output captured as evidence.",
      tone: "gold",
    },
    "gemma-reviewer": {
      code: "GEM",
      name: "Gemma reviewer",
      description: "Local Ollama review output captured as evidence.",
      tone: "pink",
    },
  };
  return profiles[worker] || {
    code: workerCode(worker),
    name: plainWorkerName(worker),
    description: "DevFlow worker evidence grouped by the worker id recorded on tasks.",
    tone: "blue",
  };
}

function workerCode(worker) {
  return String(worker || "wrk")
    .split(/[^a-zA-Z0-9]+/)
    .filter(Boolean)
    .map((part) => part[0])
    .join("")
    .slice(0, 3)
    .toUpperCase() || "WRK";
}

function plainWorkerName(worker) {
  return String(worker || "worker")
    .split(/[-_]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function workerState(tasks, activeTasks) {
  const openTasks = tasks.filter((task) => String(task.lane || "").toLowerCase() !== "closed");
  if (activeTasks.length) return "Running";
  if (openTasks.some((task) => task.lane === "blocked" || isFailedTask(task))) return "Needs attention";
  if (openTasks.some((task) => ["new", "needs_verification", "ready_to_promote"].includes(task.lane))) return "Waiting";
  return "Recorded";
}

function stateClassForWorkerState(state) {
  if (state === "Running") return "active";
  if (state === "Needs attention") return "blocked";
  if (state === "Recorded") return "complete";
  return "idle";
}

function isFailedTask(task) {
  return String(task.verification_status || "").toLowerCase().includes("fail")
    || String(task.display_status || "").toLowerCase().includes("failed");
}

function isVerifiedOrReadyTask(task) {
  return String(task.verification_status || "").toLowerCase().includes("pass")
    || Boolean(task.promotion_ready || task.merge_ready)
    || String(task.lane || "").toLowerCase() === "closed";
}

function renderOrchestratorHealthBars(goal) {
  const bars = byId("orchestrator-health-bars");
  if (!bars) return;
  bars.innerHTML = "";
  const total = Math.max(1, snapshot.health.total_tasks || 1);
  const active = Math.round((snapshot.health.active_tasks / total) * 100);
  const verify = Math.round((snapshot.health.needs_verification / total) * 100);
  const blocked = Math.round((snapshot.health.blocked_tasks / total) * 100);
  const goalReady = goal ? Math.min(100, Math.round(((goal.ready_parallel_lane_count || 0) / Math.max(1, goal.total_slices || 1)) * 100)) : 0;
  [
    ["Active", active, "teal"],
    ["Verify", verify, "gold"],
    ["Blocked", blocked, "pink"],
    ["Goal ready", goalReady, "violet"],
  ].forEach(([label, value, tone]) => {
    const row = document.createElement("div");
    row.className = `health-row ${tone}`;
    row.innerHTML = `<span>${escapeHtml(label)}</span><div><i style="width:${value}%"></i></div><strong>${value}%</strong>`;
    bars.appendChild(row);
  });
}

function renderMissionFeed(goal) {
  const list = byId("mission-feed-list");
  const count = byId("mission-feed-count");
  if (!list || !count) return;
  const items = snapshot.mission_feed || [];
  count.textContent = `${items.length} ${items.length === 1 ? "update" : "updates"}`;
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = `<div class="empty">No mission-critical output yet</div>`;
    return;
  }
  items.forEach((item) => {
    const button = document.createElement("button");
    const feedLabel = plainFeedLabel(item);
    const feedDetail = plainFeedDetail(item);
    button.type = "button";
    button.className = `mission-feed-item ${item.tone || "event"}`;
    button.setAttribute("role", "listitem");
    button.setAttribute("aria-label", `${feedLabel}: ${item.title}. ${feedDetail}`);
    button.innerHTML = `
      <span class="feed-label">${escapeHtml(feedLabel)}</span>
      <strong class="feed-title">${escapeHtml(item.title)}</strong>
      <span class="feed-detail">${escapeHtml(feedDetail)}</span>
      <span class="feed-command">${escapeHtml(item.command || "inspect")}</span>
    `;
    button.addEventListener("click", () => handleMissionFeedItem(item));
    list.appendChild(button);
  });
}

function plainFeedLabel(item) {
  return plainDisplayText(item.label || "Work update");
}

function plainFeedDetail(item) {
  const detail = String(item.detail || "");
  const labels = {
    task_cleanup_applied: "Task cleanup was applied.",
    task_cleanup_previewed: "Task cleanup preview was recorded.",
    task_created: "Task entered the queue.",
    task_closed: "Task was closed and kept as evidence.",
    verification_passed: "Verification passed.",
    verification_failed: "Verification failed.",
    worker_finished: "Worker output was recorded.",
    worker_failed: "Worker failed. Inspect the worker log.",
  };
  if (labels[detail]) return labels[detail];
  if (/^[a-z0-9]+(?:_[a-z0-9]+)+$/.test(detail)) return plainDisplayText(detail);
  return detail || "Work evidence was recorded.";
}

function handleMissionFeedItem(item) {
  const taskId = item.task_id || item.taskId;
  if (taskId && taskById(taskId)) {
    selectedTaskId = taskId;
    selectedGoalSelection = null;
    agentsExpanded = true;
    setCurrentPage("lanes", { updateHash: true });
    return;
  }
  byId("orchestrator-command")?.focus?.();
  setCurrentPage("orchestrator", { updateHash: true });
}

function renderGlobalFilterState() {
  const count = applyGlobalTaskFilter(snapshot.tasks).length;
  if (byId("global-filter").value !== globalFilter) byId("global-filter").value = globalFilter;
  byId("filter-count").textContent = globalFilter.trim() ? `${count}/${snapshot.tasks.length}` : "All";
}

function operatingMapNodes() {
  const goals = snapshot.goal_board || [];
  const readyGoalBatches = goals.reduce((total, goal) => total
    + (goal.ready_parallel_batch_count || 0)
    + (goal.ready_worker_batch_count || 0)
    + (goal.ready_verification_batch_count || 0), 0);
  const blockedGoalLanes = goals.reduce((total, goal) => total + (goal.blocked_lane_count || 0), 0);
  const activeLaneCount = snapshot.lanes.filter((lane) => lane.task_ids.length > 0).length;
  const filteredWorkerTasks = applyGlobalTaskFilter(snapshot.tasks.filter((task) => laneLimit.includes(task.lane)));
  const gateOpen = snapshot.gate_receipts.filter((gate) => gate.next_gate !== "closed").length;
  const projectSummary = snapshot.multi_project;
  return [
    {
      key: "goals",
      label: "Goals",
      value: String(goals.length),
      detail: readyGoalBatches ? `${readyGoalBatches} ready batches` : `${blockedGoalLanes} blocked lanes`,
      href: "#goals",
      tone: readyGoalBatches ? "verify" : blockedGoalLanes ? "attention" : "",
    },
    {
      key: "inbox",
      label: "Inbox",
      value: String((snapshot.inbox || []).length),
      detail: (snapshot.inbox || []).length ? "human attention" : "clear",
      href: "#inbox",
      tone: (snapshot.inbox || []).length ? "attention" : "",
    },
    {
      key: "workers",
      label: "Workers",
      value: globalFilter.trim() ? String(filteredWorkerTasks.length) : String(snapshot.health.active_tasks),
      detail: globalFilter.trim() ? "filter matches" : `${activeLaneCount} active lanes`,
      href: "#lanes",
      tone: snapshot.health.blocked_tasks ? "attention" : "",
    },
    {
      key: "gates",
      label: "Progress",
      value: String(snapshot.gate_receipts.length),
      detail: gateOpen ? `${gateOpen} open` : "all closed",
      href: "#gates",
      tone: gateOpen ? "verify" : "",
    },
    {
      key: "promotion",
      label: "Review",
      value: String(snapshot.promotion_desk.length),
      detail: snapshot.promotion_desk.length ? "ready review" : "none ready",
      href: "#promotion",
      tone: snapshot.promotion_desk.length ? "verify" : "",
    },
    {
      key: "projects",
      label: "Projects",
      value: projectSummary ? String(projectSummary.active_projects) : "0",
      detail: projectSummary ? `${projectSummary.total_projects} registered` : "registry off",
      href: "#projects",
      tone: projectSummary && projectSummary.missing_projects ? "attention" : "",
    },
  ];
}

function mapStatus(nodes) {
  const attention = nodes.filter((node) => node.tone === "attention").length;
  const verify = nodes.filter((node) => node.tone === "verify").length;
  if (attention) return `${attention} attention`;
  if (verify) return `${verify} ready`;
  return "Clear";
}

function renderContextBar() {
  const context = currentContext();
  byId("context-title").textContent = context.title;
  byId("context-detail").textContent = context.detail;
  byId("clear-context-button").disabled = !context.active;
  byId("clear-context-button").setAttribute("aria-disabled", context.active ? "false" : "true");
}

function currentContext() {
  const goalSelection = goalSelectionPayload();
  if (goalSelection) {
    return {
      active: true,
      title: selectionTitle(goalSelection),
      detail: `${selectedGoalTaskIds().length} linked tasks / ${goalSelection.type} scope`,
    };
  }
  if (selectedMapNode) {
    return {
      active: true,
      title: `Operating Map: ${mapNodeLabel(selectedMapNode)}`,
      detail: mapScopeDetail(selectedMapNode),
    };
  }
  return {
    active: false,
    title: "All work",
    detail: "Whole operating layer",
  };
}

function mapNodeLabel(key) {
  const node = operatingMapNodes().find((item) => item.key === key);
  return node ? node.label : key;
}

function mapScopeDetail(key) {
  if (key === "gates") return `${visibleGateReceipts().length} task readiness receipts`;
  if (key === "workers") return `${visibleTasksForMapScope().length} worker-lane tasks`;
  if (key === "promotion") return `${snapshot.promotion_desk.length} tasks ready for review`;
  if (key === "inbox") return `${(snapshot.inbox || []).length} inbox items`;
  if (key === "goals") return `${(snapshot.goal_board || []).length} goals`;
  if (key === "projects") return snapshot.multi_project ? `${snapshot.multi_project.total_projects} registered projects` : "project registry unavailable";
  return "Scoped view";
}

function clearContext() {
  selectedMapNode = null;
  selectedGoalSelection = null;
  selectedTaskId = snapshot.focus_task_id || firstVisibleTaskId();
  render();
}

function renderLanes() {
  const board = byId("lane-board");
  board.innerHTML = "";
  const selectedTaskIds = selectedGoalTaskIds();
  const selectedTaskSet = new Set(selectedTaskIds);
  const scopedTaskIds = new Set(visibleTasksForMapScope().map((task) => task.id));
  const filteredIds = filteredTaskIds();
  const hasMapTaskScope = ["workers", "gates", "promotion", "inbox"].includes(selectedMapNode);
  const visibleLaneTasks = [];
  snapshot.lanes
    .filter((lane) => laneLimit.includes(lane.name))
    .forEach((lane) => {
      const column = document.createElement("section");
      column.className = "lane";
      let taskIds = selectedTaskIds.length ? lane.task_ids.filter((taskId) => selectedTaskSet.has(taskId)) : lane.task_ids;
      if (hasMapTaskScope) taskIds = taskIds.filter((taskId) => scopedTaskIds.has(taskId));
      taskIds = taskIds.filter((taskId) => filteredIds.has(taskId));
      column.innerHTML = `<div class="lane-header"><strong>${lane.label}</strong><span>${taskIds.length}</span></div>`;
      taskIds.forEach((taskId) => {
        const task = taskById(taskId);
        if (!task) return;
        visibleLaneTasks.push(task);
        column.appendChild(taskRow(task, selectedTaskIds.length > 0));
      });
      if (!taskIds.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.style.padding = "12px";
        empty.textContent = globalFilter.trim()
          ? "No filter matches"
          : selectedTaskIds.length || hasMapTaskScope
            ? "No scoped tasks"
            : "None";
        column.appendChild(empty);
      }
      board.appendChild(column);
    });
  renderAgentCollective(visibleLaneTasks, agentActivityScopeTasks());
}

function agentActivityScopeTasks() {
  if (selectedGoalSelection) return selectedGoalTasks();
  if (["gates", "promotion", "inbox"].includes(selectedMapNode)) return visibleTasksForMapScope();
  return applyGlobalTaskFilter(snapshot.tasks);
}

function renderAgentCollective(activeLaneTasks, activityTasks) {
  const canvas = document.querySelector(".agents-canvas");
  const workspace = byId("lanes");
  if (canvas) {
    canvas.classList.toggle("expanded", agentsExpanded);
    canvas.classList.toggle("collapsed", !agentsExpanded);
  }
  if (workspace) {
    workspace.classList.toggle("agents-collapsed", !agentsExpanded);
    workspace.classList.toggle("agents-expanded", agentsExpanded);
  }
  const toggle = byId("agent-stack-toggle");
  if (toggle) {
    toggle.textContent = agentsExpanded ? "Collapse" : "Expand";
    toggle.setAttribute("aria-expanded", agentsExpanded ? "true" : "false");
  }
  const summaries = agentSummaries(activeLaneTasks, activityTasks);
  const activeAgents = summaries.filter((agent) => agent.status === "Running").length;
  const idleAgents = summaries.filter((agent) => agent.status === "Waiting").length;
  const dormantAgents = summaries.filter((agent) => !["Running", "Waiting"].includes(agent.status)).length;
  byId("agent-active-count").textContent = activeAgents;
  byId("agent-idle-count").textContent = idleAgents;
  byId("agent-dormant-count").textContent = dormantAgents;

  const cards = byId("agent-cards");
  cards.innerHTML = "";
  summaries.forEach((agent) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `agent-card ${agent.tone} ${agent.taskCount ? "has-work" : "idle"}`;
    card.setAttribute("aria-label", `${agent.name}: ${agent.taskCount} tasks, ${agent.successRate}% verified or ready`);
    card.innerHTML = `
      <div class="agent-card-top">
        <span>${escapeHtml(agent.code)}</span>
        <strong>${escapeHtml(agent.state)}</strong>
      </div>
      <h3>${escapeHtml(agent.name)}</h3>
      <p>${escapeHtml(agent.description)}</p>
      <div class="agent-spark" aria-hidden="true">
        ${agent.spark.map((value) => `<span style="--spark:${value}"></span>`).join("")}
      </div>
      <div class="agent-card-metrics">
        <div><strong>${agent.taskCount}</strong><span>tasks</span></div>
        <div><strong>${agent.successRate}%</strong><span>verified</span></div>
        <div><strong>${escapeHtml(agent.worker)}</strong><span>worker</span></div>
      </div>
      <small>${escapeHtml(agent.latest)}</small>
    `;
    card.addEventListener("click", () => {
      selectedMapNode = "workers";
      selectedGoalSelection = null;
      selectedTaskId = agent.firstTaskId || selectedTaskId;
      render();
      byId("lanes")?.scrollIntoView({ block: "start" });
    });
    cards.appendChild(card);
  });
  renderAgentLog(activityTasks);
}

function agentSummaries(activeLaneTasks, activityTasks) {
  const activeIds = new Set(activeLaneTasks.map((task) => task.id));
  const grouped = new Map();
  activityTasks.forEach((task) => {
    const worker = normalizedWorker(task.worker);
    if (!worker) return;
    if (!grouped.has(worker)) grouped.set(worker, []);
    grouped.get(worker).push(task);
  });
  const workerSummaries = Array.from(grouped.entries()).map(([worker, tasks], index) => {
    const profile = workerProfile(worker);
    const activeTasks = tasks.filter((task) => activeIds.has(task.id));
    const failed = tasks.filter((task) => isFailedTask(task)).length;
    const verified = tasks.filter((task) => isVerifiedOrReadyTask(task)).length;
    const successRate = tasks.length ? Math.round((verified / tasks.length) * 100) : 0;
    const latestTask = activeTasks.find((task) => task.latest) || tasks.find((task) => task.latest) || tasks[0];
    const state = workerState(tasks, activeTasks);
    return {
      ...profile,
      laneName: `worker:${worker}`,
      state,
      status: state,
      stateClass: stateClassForWorkerState(state),
      taskCount: tasks.length,
      successRate,
      verified,
      worker,
      tasks,
      firstTaskId: activeTasks[0] ? activeTasks[0].id : tasks[0] ? tasks[0].id : null,
      latest: latestTask ? `${latestTask.id}: ${plainTaskStatusLine(latestTask)}` : "No task evidence yet",
      spark: sparkValues(tasks.length, verified, failed, index),
    };
  });
  if (workerSummaries.length) {
    return workerSummaries
      .sort((a, b) => Number(b.status === "Running") - Number(a.status === "Running") || b.taskCount - a.taskCount)
      .slice(0, 6);
  }
  return statusBucketSummaries(activeLaneTasks, activityTasks);
}

function statusBucketSummaries(activeLaneTasks, activityTasks) {
  const activeTaskByLane = new Map();
  laneLimit.forEach((laneName) => activeTaskByLane.set(laneName, []));
  activeLaneTasks.forEach((task) => {
    if (activeTaskByLane.has(task.lane)) activeTaskByLane.get(task.lane).push(task);
  });
  return laneLimit.map((laneName, index) => {
    const laneTasks = activeTaskByLane.get(laneName) || [];
    const profile = agentProfile(laneName);
    const profileTasks = profileActivityTasks(laneName, laneTasks, activityTasks);
    const failed = profileTasks.filter((task) => isFailedTask(task)).length;
    const verified = profileTasks.filter((task) => isVerifiedOrReadyTask(task)).length;
    const successRate = profileTasks.length ? Math.round((verified / profileTasks.length) * 100) : 0;
    const latestTask = profileTasks.find((task) => task.latest) || profileTasks[0];
    const state = laneTasks.length ? "Waiting" : profileTasks.length ? "Recorded" : "No tasks";
    return {
      ...profile,
      laneName,
      state,
      status: state,
      stateClass: stateClassForWorkerState(state),
      taskCount: profileTasks.length,
      successRate,
      verified,
      firstTaskId: laneTasks[0] ? laneTasks[0].id : profileTasks[0] ? profileTasks[0].id : null,
      latest: latestTask ? `${latestTask.id}: ${plainTaskStatusLine(latestTask)}` : profile.emptyDetail,
      spark: sparkValues(profileTasks.length, verified, failed, index),
      tasks: profileTasks,
    };
  });
}

function profileActivityTasks(laneName, laneTasks, activityTasks) {
  const matches = activityTasks.filter((task) => {
    if (task.lane === laneName) return true;
    if (laneName === "running") return Boolean(task.worker) && task.worker !== "unassigned";
    if (laneName === "needs_verification") return task.verification_status && task.verification_status !== "missing";
    if (laneName === "ready_to_promote") return Boolean(task.promotion_ready || task.merge_ready);
    if (laneName === "blocked") {
      const text = `${task.status} ${task.display_status} ${task.latest}`.toLowerCase();
      return text.includes("block") || text.includes("human");
    }
    return false;
  });
  return uniqueTasks([...laneTasks, ...matches]);
}

function uniqueTasks(tasks) {
  const seen = new Set();
  return tasks.filter((task) => {
    if (!task || seen.has(task.id)) return false;
    seen.add(task.id);
    return true;
  });
}

function agentProfile(laneName) {
  const profiles = {
    blocked: {
      code: "BLK",
      name: "Needs user input",
      description: "Tasks blocked by a question, failed evidence, or a human decision.",
      emptyState: "No tasks",
      emptyDetail: "No blocked tasks",
      tone: "pink",
      worker: "not assigned",
    },
    running: {
      code: "WRK",
      name: "Work running",
      description: "Tasks currently being worked on inside DevFlow workspaces.",
      emptyState: "No tasks",
      emptyDetail: "No running work",
      tone: "violet",
      worker: "assigned worker",
    },
    needs_verification: {
      code: "VER",
      name: "Needs verification",
      description: "Tasks waiting for a verification command or fresh proof.",
      emptyState: "No tasks",
      emptyDetail: "No tasks need verification",
      tone: "gold",
      worker: "verification",
    },
    ready_to_promote: {
      code: "REV",
      name: "Ready for review",
      description: "Verified work waiting for a review preview and human approval.",
      emptyState: "No tasks",
      emptyDetail: "No work is ready for review",
      tone: "mint",
      worker: "human approval",
    },
    new: {
      code: "NEW",
      name: "Not started",
      description: "Fresh tasks waiting for assignment, context, or a first run.",
      emptyState: "No tasks",
      emptyDetail: "No new tasks",
      tone: "blue",
      worker: "not assigned",
    },
  };
  return profiles[laneName] || {
    code: laneName.slice(0, 3).toUpperCase(),
    name: plainWorkerName(laneName),
    description: "Task status bucket.",
    emptyState: "No tasks",
    emptyDetail: "No activity",
    tone: "blue",
    worker: "not assigned",
  };
}

function dominantWorker(tasks) {
  const counts = new Map();
  tasks.forEach((task) => {
    const worker = task.worker || "unknown";
    counts.set(worker, (counts.get(worker) || 0) + 1);
  });
  return Array.from(counts.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] || null;
}

function sparkValues(taskCount, verified, failed, offset) {
  return Array.from({ length: 7 }, (_, index) => {
    const base = taskCount ? 34 + Math.min(42, taskCount * 7) : 14;
    const signal = verified * 6 - failed * 8 + ((index + offset) % 4) * 9;
    return Math.max(12, Math.min(92, base + signal));
  });
}

function renderAgentLog(tasks) {
  const rows = agentActivityRows(tasks);
  byId("agent-log-count").textContent = `${rows.length} ${rows.length === 1 ? "entry" : "entries"}`;
  const log = byId("agent-log-list");
  log.innerHTML = "";
  if (!rows.length) {
    log.innerHTML = `<div class="empty">No recent worker activity in this scope</div>`;
    return;
  }
  rows.forEach((row) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "agent-log-row";
    item.innerHTML = `
      <span>${escapeHtml(row.time)}</span>
      <strong>${escapeHtml(row.agent)}</strong>
      <p>${escapeHtml(row.task)}</p>
      <em>${escapeHtml(row.status)}</em>
    `;
    item.addEventListener("click", () => {
      selectedTaskId = row.taskId;
      selectedGoalSelection = null;
      selectedMapNode = null;
      render();
    });
    log.appendChild(item);
  });
}

function plainTaskStatusLabel(task) {
  const lane = String(task.lane || "").toLowerCase();
  if (lane === "blocked") return "Needs attention";
  if (lane === "running") return "Worker active";
  if (lane === "needs_verification") return "Verification next";
  if (lane === "ready_to_promote") return "Ready for review";
  if (lane === "new") return "Ready to start";
  if (lane === "closed") return "Closed";
  return "Task state";
}

function plainTaskStatusLine(task) {
  const lane = String(task.lane || "").toLowerCase();
  const status = String(task.status || task.display_status || "").toLowerCase();
  const verification = String(task.verification_status || "").toLowerCase();
  if (lane === "closed" || status.includes("closed")) return "Closed for evidence. No active worker is needed.";
  if (lane === "blocked" || status.includes("blocked")) return "Human input or repair is needed before work continues.";
  if (lane === "running" || status.includes("running")) return "A worker is running in the isolated workspace.";
  if (lane === "needs_verification") return "Worker output is recorded. Verification is the next gate.";
  if (lane === "ready_to_promote") return "Verification passed. Review and promotion preview are next.";
  if (verification.includes("fail")) return "Verification failed. Inspect the verify log before continuing.";
  if (verification.includes("pass")) return "Verification passed. Review readiness is available.";
  if (lane === "new" || status === "new") return "Task is queued and ready for a worker command.";
  return plainDisplayText(task.display_status || task.status || task.latest || "Task evidence recorded.");
}

function plainEventLabel(eventName) {
  const labels = {
    task_created: "Task created",
    task_updated: "Task updated",
    task_closed: "Task closed",
    worker_started: "Worker started",
    worker_finished: "Worker finished",
    worker_failed: "Worker failed",
    verification_started: "Verification started",
    verification_passed: "Verification passed",
    verification_failed: "Verification failed",
    task_verified: "Task verified",
    task_promoted: "Task promoted",
    patch_applied: "Patch applied",
  };
  return labels[eventName] || plainDisplayText(eventName || "event recorded");
}

function plainEventSummary(event, task) {
  const eventName = String(event.event || "");
  const labels = {
    task_created: "Task entered the queue and is ready for assignment.",
    task_updated: "Task state changed. Inspect task details for evidence.",
    task_closed: "Task was closed and kept as evidence.",
    worker_started: "Worker execution started in the task workspace.",
    worker_finished: "Worker output was recorded for review.",
    worker_failed: "Worker failed. Inspect the worker log before retrying.",
    verification_started: "Verification started for this task.",
    verification_passed: "Verification passed and review can continue.",
    verification_failed: "Verification failed. Inspect the verify log.",
    task_verified: "Verification passed and evidence is recorded.",
    task_promoted: "Task was promoted after human approval.",
    patch_applied: "Patch evidence was applied to the isolated workspace.",
  };
  if (labels[eventName]) return labels[eventName];
  return plainTaskStatusLine(task);
}

function plainDisplayText(value) {
  return String(value || "recorded")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\\s+/g, " ")
    .trim()
    .replace(/^./, (letter) => letter.toUpperCase());
}

function agentActivityRows(tasks) {
  const rows = [];
  tasks.forEach((task) => {
    const events = task.detail && task.detail.recent_events ? task.detail.recent_events : [];
    if (!events.length) {
      rows.push({
        taskId: task.id,
        time: "latest",
        agent: task.worker || laneAgentName(task.lane),
        task: task.title,
        status: plainTaskStatusLine(task),
        timestamp: "",
      });
      return;
    }
    events.slice(-2).forEach((event) => {
      rows.push({
        taskId: task.id,
        time: shortTime(event.timestamp),
        agent: task.worker || laneAgentName(task.lane),
        task: `${task.id} - ${task.title}`,
        status: plainEventSummary(event, task),
        timestamp: event.timestamp || "",
      });
    });
  });
  return rows
    .sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)))
    .slice(0, 7);
}

function laneAgentName(laneName) {
  return agentProfile(laneName).name;
}

function shortTime(timestamp) {
  if (!timestamp) return "latest";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "latest";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function taskRow(task, isGoalFiltered = false) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = `task-row ${task.id === selectedTaskId ? "selected" : ""} ${isGoalFiltered ? "goal-filtered" : ""}`;
  row.innerHTML = `
    <strong>${task.id} - ${escapeHtml(task.title)}</strong>
    <div class="work-status-card">
      <span>${escapeHtml(plainTaskStatusLabel(task))}</span>
      <strong>${escapeHtml(plainTaskStatusLine(task))}</strong>
    </div>
    <div class="task-meta">
      <span>${escapeHtml(task.worker)}</span>
      <span>${escapeHtml(task.verification_status)}</span>
      <span>${escapeHtml(task.display_status)}</span>
    </div>
  `;
  row.addEventListener("click", () => {
    selectedTaskId = task.id;
    selectedGoalSelection = null;
    selectedMapNode = null;
    render();
  });
  return row;
}

function renderInspector() {
  const selection = goalSelectionPayload();
  if (selection) {
    renderGoalInspector(selection);
    return;
  }
  const task = taskById(selectedTaskId);
  byId("selected-task-id").textContent = task ? task.id : "None";
  byId("selected-title").textContent = task ? task.title : "Select a task";
  byId("selected-command").textContent = task && task.next_action ? task.next_action.command || "None" : "None";
  const details = byId("selected-details");
  details.innerHTML = "";
  renderTaskDetail(task);
  if (!task) return;
  [
    ["Status", task.display_status],
    ["Worker", task.worker],
    ["Verify", task.verification_status],
    ["Workspace", task.workspace],
    ["Log", task.log_path || "None"],
    ["Result", task.result_path || "None"],
  ].forEach(([key, value]) => {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key;
    dd.textContent = value;
    details.append(dt, dd);
  });
}

function renderGoalInspector(selection) {
  const goal = selection.goal;
  const item = selection.item;
  const linkedTasks = selectedGoalTasks();
  const gates = selectedGoalGateReceipts();
  const evidence = selectedGoalEvidence();
  byId("selected-task-id").textContent = selection.type === "goal" ? goal.goal_id : item.batch_id || item.slice_id;
  byId("selected-title").textContent = selectionTitle(selection);
  byId("selected-command").textContent = firstActionCommand(item) || goal.next_action || "None";
  const details = byId("selected-details");
  details.innerHTML = "";
  const rows = selectionRows(selection);
  rows.forEach(([key, value]) => {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = key;
    dd.textContent = value;
    details.append(dt, dd);
  });
  const summary = byId("detail-summary");
  const events = byId("detail-events");
  summary.innerHTML = "";
  events.innerHTML = "";
  byId("detail-event-count").textContent = linkedTasks.length + gates.length + evidence.length;
  [
    ["Recommendation", item.recommendation || item.reason || goal.next_action || "None"],
    ["Commands", commandList(item).join("\\n") || "None"],
    ["Blockers", (item.blockers || []).join("\\n") || "None"],
    ["Shared files", (item.shared_files || []).join("\\n") || "None"],
    ["Linked tasks", linkedTasks.map((task) => `${task.id} - ${task.display_status}`).join("\\n") || "None"],
    ["Task progress", gates.map(gateSummary).join("\\n") || "No linked task progress"],
    ["Evidence", evidence.map(evidenceSummary).join("\\n") || "No linked evidence"],
  ].forEach(([label, value]) => {
    const detail = document.createElement("div");
    detail.className = "detail-item";
    detail.innerHTML = `<strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span>`;
    summary.appendChild(detail);
  });
  if (!linkedTasks.length) {
    events.innerHTML = `<div class="empty">No linked task evidence yet</div>`;
    return;
  }
  linkedTasks.slice(0, 5).forEach((task) => {
    const event = document.createElement("div");
    event.className = "event-item";
    const preview = task.detail && task.detail.result_preview
      ? task.detail.result_preview
      : task.latest || task.display_status;
    event.innerHTML = `
      <strong>${escapeHtml(task.id)} evidence</strong>
      <span>${escapeHtml(preview || "No evidence preview")}</span>
    `;
    events.appendChild(event);
  });
}

function selectionTitle(selection) {
  if (selection.type === "goal") return `${selection.goal.goal_id} - ${selection.goal.title}`;
  if (selection.type === "batch") return `${selection.item.batch_id} - ${selection.item.kind} batch`;
  return `${selection.item.slice_id} - ${selection.item.title}`;
}

function selectionRows(selection) {
  const item = selection.item;
  if (selection.type === "goal") {
    return [
      ["Type", "Goal"],
      ["State", item.loop_state],
      ["Slices", String(item.total_slices)],
      ["Ready", String(item.ready_parallel_lane_count)],
      ["Blocked", String(item.blocked_lane_count)],
    ];
  }
  if (selection.type === "batch") {
    return [
      ["Type", `${item.kind} batch`],
      ["Lanes", (item.lane_ids || []).join(", ") || "None"],
      ["Tasks", (item.task_ids || []).join(", ") || "None"],
      ["Commands", String(item.command_count)],
      ["Scope", item.verification_scope || "None"],
    ];
  }
  return [
    ["Type", "Goal slice"],
    ["State", item.lane_state],
    ["Risk", item.risk],
    ["Mode", item.execution_mode],
    ["Blocks", (item.blockers || []).join(", ") || "None"],
    ["Tasks", (item.linked_task_ids || []).join(", ") || "None"],
  ];
}

function firstActionCommand(item) {
  const actions = item && item.actions ? item.actions : [];
  return actions.length ? actions[0].command : item.command || null;
}

function commandList(item) {
  const commands = [
    ...((item.actions || []).map((action) => action.command)),
    ...(item.commands || []),
    item.command,
  ].filter(Boolean);
  return Array.from(new Set(commands));
}

function gateSummary(gate) {
  const complete = ["intake", "worker_evidence", "verification", "promotion_readiness", "human_decision"]
    .filter((step) => gate[step]).length;
  return `${gate.task_id}: ${complete}/5 required steps done, next ${plainNextStep(gate.next_gate)}`;
}

function plainNextStep(nextGate) {
  const labels = {
    run_worker: "run a worker",
    verify: "verify the task",
    verification: "verify the task",
    promotion_preview: "prepare review preview",
    promotion_readiness: "prepare review",
    human_decision: "human review",
    closed: "closed",
  };
  return labels[nextGate] || String(nextGate || "unknown").replaceAll("_", " ");
}

function evidenceSummary(item) {
  return `${item.task_id}: ${item.log_path || item.result_path || item.verification_log_path || item.verification_command || "evidence"}`;
}

function renderTaskDetail(task) {
  const summary = byId("detail-summary");
  const events = byId("detail-events");
  summary.innerHTML = "";
  events.innerHTML = "";
  byId("detail-event-count").textContent = task && task.detail ? task.detail.recent_events.length : 0;
  if (!task || !task.detail) {
    summary.innerHTML = `<div class="empty">Select a task</div>`;
    return;
  }
  const detail = task.detail;
  [
    ["Verification", verificationLabel(detail.verification)],
    ["Worker log", detail.latest_worker_line || "None"],
    ["Verify log", detail.latest_verification_line || "None"],
    ["Result", detail.result_preview || "None"],
    ["Evidence", detail.evidence_paths.length ? detail.evidence_paths.join("\\n") : "None"],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "detail-item";
    item.innerHTML = `<strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span>`;
    summary.appendChild(item);
  });
  if (!detail.recent_events.length) {
    events.innerHTML = `<div class="empty">No events</div>`;
  } else {
    detail.recent_events.forEach((event) => {
      const item = document.createElement("div");
      item.className = "event-item";
      item.innerHTML = `
        <strong>${escapeHtml(plainEventLabel(event.event))}</strong>
        <span class="event-status-card">
          <span>${escapeHtml(shortTime(event.timestamp))}</span>
          <strong>${escapeHtml(plainEventSummary(event, task))}</strong>
        </span>
      `;
      events.appendChild(item);
    });
  }
}

function verificationLabel(verification) {
  if (!verification) return "missing";
  if (verification.exit_code === null || verification.exit_code === undefined) return verification.status;
  return `${verification.status} / exit ${verification.exit_code}`;
}

function renderActions() {
  const task = taskById(selectedTaskId);
  const selection = goalSelectionPayload();
  const scopedActions = mapScopedActions();
  const actions = selection
    ? selection.item.actions || []
    : selectedMapNode && scopedActions.length
      ? scopedActions
      : task
        ? task.actions || []
        : snapshot.action_rail || [];
  byId("action-count").textContent = actions.length;
  const list = byId("action-list");
  const preview = byId("action-preview");
  list.innerHTML = "";
  preview.innerHTML = "";
  if (!sectionExpanded("actions")) return;
  if (!actions.length) {
    list.innerHTML = `<div class="empty">None</div>`;
    renderActionPreview(null);
    return;
  }
  const visibleActions = actions.slice(0, 8);
  const preservedResult = preservedActionResultForSelectedTask(visibleActions);
  const renderedActions = preservedResult ? [preservedResult.action, ...visibleActions].slice(0, 8) : visibleActions;
  if (!renderedActions.some((action) => action.command === selectedActionCommand)) {
    selectedActionCommand = renderedActions[0].command;
  }
  renderedActions.forEach((action) => {
    const item = document.createElement("button");
    item.type = "button";
    const selected = action.command === selectedActionCommand;
    item.className = `action-item ${selected ? "selected" : ""}`;
    item.setAttribute("aria-pressed", selected ? "true" : "false");
    item.setAttribute("aria-label", `Preview ${action.label}`);
    const safety = action.supervisor_may_auto_run ? "read-only" : "approval required";
    item.innerHTML = `
      <strong>${escapeHtml(action.label)}</strong>
      <span class="label">${escapeHtml(safety)} / ${escapeHtml(action.safety_class)}</span>
      <code>${escapeHtml(action.command)}</code>
    `;
    item.addEventListener("click", () => {
      selectedActionCommand = action.command;
      renderActions();
    });
    list.appendChild(item);
  });
  renderActionPreview(renderedActions.find((action) => action.command === selectedActionCommand) || renderedActions[0]);
}

function renderActionPreview(action) {
  const preview = byId("action-preview");
  preview.innerHTML = "";
  if (!action) {
    preview.innerHTML = `<div class="empty">Select an action to inspect command safety</div>`;
    return;
  }
  const mayAutoRun = action.supervisor_may_auto_run ? "Supervisor read-only safe" : "Human approval required";
  const approval = action.requires_human_approval ? "approval required" : "no approval required";
  const isRunning = actionRunState && actionRunState.command === action.command && actionRunState.status === "running";
  const preservedResult =
    lastApprovedActionResult && lastApprovedActionResult.command === action.command
      ? lastApprovedActionResult
      : null;
  const actionResult =
    actionRunState && actionRunState.command === action.command ? actionRunState : preservedResult;
  const isApprovedVerification = isTaskVerificationAction(action);
  const isApprovedPromotion = isTaskPromotionAction(action);
  const verificationCommand = (verificationCommandInputs[action.command] || "").trim();
  const promotionContext = promotionContextInputs[action.command] || "";
  const effectiveCommand = isApprovedVerification && verificationCommand ? approvedVerificationCommand(action) : action.command;
  const canRun =
    action.supervisor_may_auto_run ||
    (isApprovedVerification && verificationCommand) ||
    isApprovedPromotion;
  const executeLabel = action.supervisor_may_auto_run
    ? "Execute read-only command"
    : (isApprovedVerification ? "Approve and run verification" : (isApprovedPromotion ? "Approve & promote" : "Approval required in CLI"));
  const controlLabel = isApprovedVerification
    ? "This approved action runs only the exact verification command shown above."
    : (isApprovedPromotion
      ? "Promotes only the exact command shown; optional context is saved with the decision."
      : (action.supervisor_may_auto_run ? "Runs locally through Dev-Flow guardrails" : "Use the trusted CLI after explicit approval"));
  const verificationControl = isApprovedVerification
    ? `
      <label class="approved-verification-control">
        <span class="label">Verification shell command</span>
        <input type="text" data-verification-command value="${escapeHtml(verificationCommand)}" placeholder="test -f result.txt">
      </label>
    `
    : "";
  const promotionControl = isApprovedPromotion
    ? `
      <label class="approved-promotion-control">
        <span class="label">Context note</span>
        <textarea data-promotion-context rows="3" placeholder="Add reviewer context for this promotion...">${escapeHtml(promotionContext)}</textarea>
      </label>
    `
    : "";
  const resultMarkup = actionResult && actionResult.status !== "running"
    ? renderActionResult(actionResult)
    : "";
  preview.innerHTML = `
    <div class="section-heading">
      <span>Command Preview</span>
      <strong>${escapeHtml(action.scope || "scope")}</strong>
    </div>
    <div class="action-preview-grid">
      <div>
        <span>Label</span>
        <strong>${escapeHtml(action.label)}</strong>
      </div>
      <div>
        <span>Safety</span>
        <strong>${escapeHtml(action.safety_class)}</strong>
      </div>
      <div>
        <span>Execution</span>
        <strong>${escapeHtml(mayAutoRun)}</strong>
      </div>
      <div>
        <span>Approval</span>
        <strong>${escapeHtml(approval)}</strong>
      </div>
    </div>
    <code>${escapeHtml(effectiveCommand)}</code>
    <p>${escapeHtml(action.reason || "This command is supervisor-classified as safe for this local control layer.")}</p>
    ${verificationControl}
    ${promotionControl}
    <div class="action-execute-row">
      <button type="button" class="action-run-button" data-run-action ${canRun && !isRunning ? "" : "disabled"}>
        ${escapeHtml(isRunning ? "Running..." : executeLabel)}
      </button>
      <span class="label">${escapeHtml(controlLabel)}</span>
    </div>
    ${isRunning ? '<div class="action-result"><strong>Running command...</strong></div>' : resultMarkup}
  `;
  const verificationInput = preview.querySelector("[data-verification-command]");
  if (verificationInput) {
    verificationInput.addEventListener("input", (event) => {
      verificationCommandInputs[action.command] = event.target.value;
      renderActionPreview(action);
    });
  }
  const promotionContextInput = preview.querySelector("[data-promotion-context]");
  if (promotionContextInput) {
    promotionContextInput.addEventListener("input", (event) => {
      promotionContextInputs[action.command] = event.target.value;
    });
  }
  const runButton = preview.querySelector("[data-run-action]");
  if (runButton && canRun) {
    runButton.addEventListener("click", () =>
      executeAction(action, { approvedVerification: isApprovedVerification, approvedPromotion: isApprovedPromotion })
    );
  }
}

function isTaskVerificationAction(action) {
  return Boolean(
    action &&
      action.safety_class === "approval_required_worker_runtime" &&
      /^devflow task verify\\s+/.test(action.command || "")
  );
}

function isTaskPromotionAction(action) {
  return Boolean(
    action &&
      action.safety_class === "approval_required_git" &&
      /^devflow task promote\\s+/.test(action.command || "")
  );
}

function approvedVerificationCommand(action) {
  const shellCommand = (verificationCommandInputs[action.command] || "").trim();
  const quoted = quoteShellArgument(shellCommand);
  if ((action.command || "").includes("\\"<command>\\"")) return action.command.replace("\\"<command>\\"", quoted);
  if ((action.command || "").includes("<command>")) return action.command.replace("<command>", quoted);
  return `${action.command} --shell ${quoted}`;
}

function quoteShellArgument(value) {
  return `"${String(value).replace(/\\\\/g, "\\\\\\\\").replace(/"/g, "\\\\\\"")}"`;
}

function renderActionResult(result) {
  if (result.status === "blocked") {
    return `
      <div class="action-result">
        <strong>Approval gate</strong>
        <p>${escapeHtml(result.message || "This command requires human approval and was not executed.")}</p>
      </div>
    `;
  }
  if (result.status === "error") {
    return `
      <div class="action-result">
        <strong>Command error</strong>
        <p>${escapeHtml(result.message || "The command could not be executed.")}</p>
      </div>
    `;
  }
  const payload = result.payload || {};
  const output = [payload.stdout, payload.stderr].filter(Boolean).join("\\n");
  const status = payload.timed_out ? "Timed out" : `Exit ${payload.exit_code}`;
  return `
    <div class="action-result">
      <strong>${escapeHtml(status)}</strong>
      ${payload.output_truncated ? "<p>Output was truncated.</p>" : ""}
      <pre>${escapeHtml(output || "No output")}</pre>
    </div>
  `;
}

function rememberApprovedActionResult(action, runState) {
  if (!action || !runState || runState.status === "running") return;
  lastApprovedActionResult = {
    ...runState,
    action: { ...action, label: "Last approved command" },
    projectId: selectedProjectId,
    taskId: selectedTaskId,
  };
}

function preservedActionResultForSelectedTask(actions) {
  if (!lastApprovedActionResult) return null;
  if (lastApprovedActionResult.projectId !== selectedProjectId) return null;
  if (lastApprovedActionResult.taskId !== selectedTaskId) return null;
  if (actions.some((action) => action.command === lastApprovedActionResult.command)) return null;
  return lastApprovedActionResult;
}

async function executeAction(action, options = {}) {
  const command = options.approvedVerification ? approvedVerificationCommand(action) : action.command;
  const body = { command, project: selectedProjectId };
  let refreshedSnapshot = false;
  if (options.approvedVerification || options.approvedPromotion) {
    body.human_approved = true;
    body.approval_phrase = APPROVAL_PHRASE;
    body.approved_command = command;
    if (options.approvedPromotion) {
      body.context_note = promotionContextInputs[action.command] || "";
    }
  }
  actionRunState = { command: action.command, status: "running" };
  renderActionPreview(action);
  try {
    const response = await fetch("/api/actions/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({ error: "Action unavailable" }));
    if (!response.ok && payload.executed === false) {
      actionRunState = {
        command: action.command,
        status: "blocked",
        message: payload.message || payload.error || "Action requires approval",
        payload,
      };
    } else if (!response.ok) {
      actionRunState = {
        command: action.command,
        status: "error",
        message: payload.error || payload.stderr || "Action failed",
        payload,
      };
    } else {
      actionRunState = { command: action.command, status: "complete", payload };
    }
    if ((options.approvedVerification || options.approvedPromotion) && payload.executed === true) {
      await refreshSnapshotAfterApprovedAction(action);
      refreshedSnapshot = true;
    }
  } catch (error) {
    actionRunState = {
      command: action.command,
      status: "error",
      message: error instanceof Error ? error.message : "Action failed",
    };
  }
  if (!refreshedSnapshot) renderActionPreview(action);
}

async function refreshSnapshotAfterApprovedAction(action) {
  const priorTaskId = selectedTaskId;
  const priorRunState =
    actionRunState && actionRunState.command === action.command ? { ...actionRunState } : null;
  if (priorRunState) rememberApprovedActionResult(action, priorRunState);
  await loadSnapshot(selectedProjectId);
  if (priorTaskId && taskById(priorTaskId)) selectedTaskId = priorTaskId;
  if (lastApprovedActionResult && lastApprovedActionResult.taskId === selectedTaskId) {
    selectedActionCommand = lastApprovedActionResult.command;
    actionRunState = lastApprovedActionResult;
  } else {
    const refreshedAction = (taskById(selectedTaskId)?.actions || []).find((item) => item.command === action.command);
    if (refreshedAction) selectedActionCommand = refreshedAction.command;
  }
  render();
}

function mapScopedActions() {
  if (selectedMapNode === "goals") return (snapshot.goal_board || []).flatMap((goal) => goal.actions || []).slice(0, 8);
  if (selectedMapNode === "inbox") return (snapshot.inbox || []).map((item) => item.action).filter(Boolean).slice(0, 8);
  if (selectedMapNode === "projects") return snapshot.action_rail || [];
  if (selectedMapNode === "promotion") {
    return snapshot.promotion_desk.map((item) => ({
      label: "Review preview",
      command: item.command,
      scope: "task",
      safety_class: "pure_read_only",
      requires_human_approval: false,
      supervisor_may_auto_run: true,
      reason: null,
    })).slice(0, 8);
  }
  if (selectedMapNode === "gates" || selectedMapNode === "workers") {
    return visibleTasksForMapScope().flatMap((task) => task.actions || []).slice(0, 8);
  }
  return [];
}

function renderGoalBoard() {
  const goals = snapshot.goal_board || [];
  byId("goal-board-count").textContent = goals.length;
  const list = byId("goal-board-list");
  list.innerHTML = "";
  if (!sectionExpanded("goals")) return;
  if (!goals.length) {
    list.innerHTML = `<div class="empty">None</div>`;
    return;
  }
  goals.slice(0, 6).forEach((goal) => {
    const card = document.createElement("article");
    card.className = "goal-card goal-page-card";
    const batches = [
      ...(goal.parallel_batches || []),
      ...(goal.worker_batches || []),
      ...(goal.verification_batches || []),
    ].slice(0, 4);
    const blockers = (goal.blocked_lanes || []).slice(0, 3);
    const lanes = (goal.lanes || []).slice(0, 12);
    const completion = goal.total_slices
      ? Math.round((goal.completed_slice_count / goal.total_slices) * 100)
      : 0;
    card.innerHTML = `
      <div class="goal-page-top">
        <div>
          <span class="label">${escapeHtml(goal.goal_id)}</span>
          <h3>${escapeHtml(goal.title)}</h3>
          <p>${escapeHtml(plainGoalState(goal.loop_state))} / ${escapeHtml(plainGoalState(goal.goal_state))}</p>
        </div>
        <div class="goal-progress-summary" aria-label="${completion}% complete">
          <strong>${completion}%</strong>
          <span>${goal.completed_slice_count}/${goal.total_slices} slices done</span>
          <i style="--goal-progress:${completion}%"></i>
        </div>
      </div>
      <div class="goal-metrics">
        <div class="goal-metric"><span>Done</span><strong>${goal.completed_slice_count}</strong></div>
        <div class="goal-metric"><span>Active tasks</span><strong>${goal.active_task_count}</strong></div>
        <div class="goal-metric"><span>Ready lanes</span><strong>${goal.ready_parallel_lane_count}</strong></div>
        <div class="goal-metric"><span>Blocked</span><strong>${goal.blocked_lane_count}</strong></div>
      </div>
      <div class="goal-page-layout">
        <div class="goal-lane-panel">
          <div class="goal-panel-heading">
            <span>Goal slices</span>
            <strong>${lanes.length}</strong>
          </div>
          <div class="goal-lane-grid">
            ${lanes.map((lane) => `
              <button class="goal-select goal-lane-row ${laneStateClass(lane)} ${isSelectedGoalItem(goal.goal_id, "lane", lane.slice_id) ? "selected" : ""}" type="button" data-goal="${escapeHtml(goal.goal_id)}" data-type="lane" data-id="${escapeHtml(lane.slice_id)}" aria-pressed="${isSelectedGoalItem(goal.goal_id, "lane", lane.slice_id) ? "true" : "false"}" aria-label="Select ${escapeHtml(lane.slice_id)} ${escapeHtml(lane.title)}">
                <span>${escapeHtml(lane.slice_id)}</span>
                <strong>${escapeHtml(lane.title)}</strong>
                <small>${escapeHtml(plainGoalState(lane.lane_state))} / ${escapeHtml(lane.risk || "risk unknown")}</small>
                <em>${escapeHtml((lane.linked_task_ids || []).join(", ") || "No linked task")}</em>
                <p>${escapeHtml(lane.recommendation || "No recommendation recorded.")}</p>
              </button>
            `).join("") || '<div class="empty">No goal slices projected</div>'}
          </div>
        </div>
        <aside class="goal-next-panel">
          <div class="goal-panel-heading">
            <span>Next safe action</span>
            <strong>${batches.length ? `${batches.length} batch${batches.length === 1 ? "" : "es"}` : "manual"}</strong>
          </div>
          <code>${escapeHtml(goal.next_action || "None")}</code>
          <div class="goal-mini-list">
            <span>Ready batches</span>
            ${batches.map((batch) => `
              <button class="goal-select goal-mini-row ${isSelectedGoalItem(goal.goal_id, "batch", batch.batch_id) ? "selected" : ""}" type="button" data-goal="${escapeHtml(goal.goal_id)}" data-type="batch" data-id="${escapeHtml(batch.batch_id)}" aria-pressed="${isSelectedGoalItem(goal.goal_id, "batch", batch.batch_id) ? "true" : "false"}" aria-label="Select ${escapeHtml(batch.batch_id)} ${escapeHtml(batch.kind)} batch">
                <strong>${escapeHtml(batch.batch_id)}</strong>
                <small>${escapeHtml(batch.kind)} / ${batch.command_count} commands</small>
              </button>
            `).join("") || '<div class="empty">No ready batches</div>'}
          </div>
          <div class="goal-mini-list">
            <span>Blocked work</span>
            ${blockers.map((lane) => `
              <button class="goal-select goal-mini-row blocked ${isSelectedGoalItem(goal.goal_id, "lane", lane.slice_id) ? "selected" : ""}" type="button" data-goal="${escapeHtml(goal.goal_id)}" data-type="lane" data-id="${escapeHtml(lane.slice_id)}" aria-pressed="${isSelectedGoalItem(goal.goal_id, "lane", lane.slice_id) ? "true" : "false"}" aria-label="Select blocked ${escapeHtml(lane.slice_id)} ${escapeHtml(lane.title)}">
                <strong>${escapeHtml(lane.slice_id)}</strong>
                <small>${escapeHtml((lane.blockers || []).join(", ") || "Needs review")}</small>
              </button>
            `).join("") || '<div class="empty">No blocked goal slices</div>'}
          </div>
        </aside>
      </div>
    `;
    card.addEventListener("click", (event) => {
      const button = event.target.closest(".goal-select");
      if (!button) {
        selectedGoalSelection = { goalId: goal.goal_id, type: "goal", id: goal.goal_id };
      } else {
        selectedGoalSelection = {
          goalId: button.dataset.goal,
          type: button.dataset.type,
          id: button.dataset.id,
        };
      }
      selectedTaskId = null;
      const linked = selectedGoalTaskIds();
      if (linked.length) selectedTaskId = linked[0];
      render();
    });
    list.appendChild(card);
  });
}

function isSelectedGoalItem(goalId, type, id) {
  return selectedGoalSelection
    && selectedGoalSelection.goalId === goalId
    && selectedGoalSelection.type === type
    && selectedGoalSelection.id === id;
}

function plainGoalState(state) {
  const labels = {
    planning_review: "Planning review",
    ready_for_task_creation: "Ready for task creation",
    ready_to_create_task: "Ready to create task",
    ready_to_run_or_verify: "Ready to run or verify",
    repair_or_verify: "Repair or verify",
    ready_to_promote: "Ready for review",
    closed: "Closed",
    complete: "Complete",
  };
  return labels[state] || String(state || "unknown").replaceAll("_", " ");
}

function laneStateClass(lane) {
  const state = String(lane.lane_state || "").toLowerCase();
  if (state.includes("block")) return "blocked";
  if (state.includes("closed") || state.includes("complete")) return "done";
  if (state.includes("ready")) return "ready";
  return "planned";
}

function renderSpecs() {
  const documents = specDocuments();
  const availableDocuments = documents.filter((doc) => doc.status !== "missing");
  byId("spec-count").textContent = documents.length || snapshot.spec_board.length;
  const list = byId("spec-list");
  list.innerHTML = "";
  if (!sectionExpanded("specs")) return;
  if (!snapshot.spec_board.length) {
    list.innerHTML = `
      <div class="library-shell">
        <div class="library-hero">
          <span>Worker Output</span>
          <h2>Library.</h2>
          <p>No spec documents are projected yet.</p>
        </div>
      </div>
    `;
    return;
  }
  const selected = selectedSpecDocument(documents);
  list.innerHTML = `
    <div class="library-shell">
      <div class="library-hero">
        <div>
          <span>Worker Output</span>
          <h2>Library.</h2>
        </div>
        <button type="button" class="library-new-doc" data-toggle-section="actions">New Doc</button>
      </div>
      <div class="library-stats">
        <div><span>Total Docs</span><strong>${documents.length}</strong><small>projected artifacts</small></div>
        <div><span>Available</span><strong>${availableDocuments.length}</strong><small>readable references</small></div>
        <div><span>Goals</span><strong>${snapshot.spec_board.length}</strong><small>active spec roots</small></div>
        <div><span>Latest</span><strong>${escapeHtml(selected ? selected.title : "None")}</strong><small>${escapeHtml(selected ? selected.kind : "no documents")}</small></div>
      </div>
      <div class="library-workspace">
        <aside class="library-sidebar">
          <div class="library-chips">
            ${libraryKinds(documents).map((kind) => `<span>${escapeHtml(kind)}</span>`).join("")}
          </div>
          <div id="library-doc-list" class="library-doc-list"></div>
        </aside>
        <article id="library-reader" class="library-reader"></article>
      </div>
    </div>
  `;
  renderLibraryDocumentList(documents, selected);
  renderLibraryReader(selected);
  const newDoc = list.querySelector(".library-new-doc");
  newDoc?.addEventListener("click", () => {
    sectionState.actions = "expanded";
    setCurrentPage("actions", { updateHash: true });
  });
}

function specDocuments() {
  const documents = [];
  snapshot.spec_board.forEach((goal) => {
    documents.push({
      key: `goal:${goal.goal_id}`,
      kind: "goal",
      title: goal.title,
      subtitle: goal.goal_id,
      path: goal.spec_path,
      source: "goal spec",
      status: goal.state,
      goal,
      slices: goal.slices || [],
      reference: null,
    });
    (goal.references || []).forEach((reference, index) => {
      documents.push({
        key: `ref:${goal.goal_id}:${index}:${reference.path}`,
        kind: reference.kind,
        title: reference.title,
        subtitle: goal.goal_id,
        path: reference.path,
        source: reference.source,
        status: reference.status,
        goal,
        slices: goal.slices || [],
        reference,
      });
    });
  });
  return documents;
}

function selectedSpecDocument(documents) {
  if (!documents.length) return null;
  let selected = documents.find((doc) => doc.key === selectedSpecDocumentKey);
  if (!selected) selected = documents.find((doc) => doc.status !== "missing") || documents[0];
  selectedSpecDocumentKey = selected.key;
  return selected;
}

function libraryKinds(documents) {
  const kinds = ["all", ...Array.from(new Set(documents.map((doc) => doc.kind)))];
  return kinds.slice(0, 6);
}

function renderLibraryDocumentList(documents, selected) {
  const target = byId("library-doc-list");
  if (!target) return;
  target.innerHTML = "";
  documents.slice(0, 14).forEach((doc) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `library-doc ${selected && selected.key === doc.key ? "selected" : ""}`;
    button.setAttribute("aria-pressed", selected && selected.key === doc.key ? "true" : "false");
    button.innerHTML = `
      <span>${escapeHtml(doc.kind)}</span>
      <strong>${escapeHtml(doc.title)}</strong>
      <small>${escapeHtml(doc.subtitle)} / ${escapeHtml(doc.status)}</small>
    `;
    button.addEventListener("click", () => {
      selectedSpecDocumentKey = doc.key;
      renderSpecs();
    });
    target.appendChild(button);
  });
}

function renderLibraryReader(doc) {
  const reader = byId("library-reader");
  if (!reader) return;
  if (!doc) {
    reader.innerHTML = `<div class="empty">Select a document to read</div>`;
    return;
  }
  const slices = (doc.slices || []).slice(0, 6);
  reader.innerHTML = `
    <div class="library-reader-top">
      <span>${escapeHtml(doc.kind)}</span>
      <strong>${escapeHtml(doc.status)}</strong>
    </div>
    <h3>${escapeHtml(doc.title)}</h3>
    <p>${escapeHtml(doc.path)}</p>
    <div class="library-reader-meta">
      <div><span>Goal</span><strong>${escapeHtml(doc.goal.goal_id)}</strong></div>
      <div><span>Source</span><strong>${escapeHtml(doc.source)}</strong></div>
      <div><span>Slices</span><strong>${slices.length}</strong></div>
    </div>
    <div class="library-slice-map">
      ${slices.map((slice) => `
        <div class="library-slice ${slice.state === "blocked" ? "blocked" : ""}">
          <span>${escapeHtml(slice.slice_id)}</span>
          <strong>${escapeHtml(slice.title)}</strong>
          <small>${escapeHtml(slice.state)}${slice.risk ? ` / ${escapeHtml(slice.risk)}` : ""}</small>
        </div>
      `).join("") || '<div class="empty">No slices projected</div>'}
    </div>
    <code>${escapeHtml(doc.reference ? doc.reference.path : doc.goal.spec_path)}</code>
  `;
}

function renderGates() {
  const selectedIds = selectedGoalTaskIds();
  const gates = visibleGateReceipts();
  byId("gate-count").textContent = gates.length;
  const summary = byId("progress-summary-grid");
  const list = byId("gate-list");
  const review = byId("task-review-panel");
  summary.innerHTML = "";
  list.innerHTML = "";
  if (review) review.innerHTML = "";
  if (!sectionExpanded("gates")) return;
  if (!gates.length) {
    summary.innerHTML = "";
    if (review) review.innerHTML = "";
    list.innerHTML = `<div class="empty">${selectedIds.length ? "No linked task progress" : "None"}</div>`;
    return;
  }
  renderProgressSummary(gates, summary);
  renderTaskReviewPanel(review);
  gates.slice(0, 12).forEach((gate) => {
    list.appendChild(renderProgressTask(gate));
  });
}

function renderProgressSummary(gates, target) {
  const counts = {
    open: gates.filter((gate) => gate.next_gate !== "closed").length,
    worker: gates.filter((gate) => gate.next_gate === "run_worker").length,
    verify: gates.filter((gate) => gate.next_gate === "verify").length,
    review: gates.filter((gate) => ["promotion_preview", "human_decision"].includes(gate.next_gate)).length,
  };
  [
    ["Open tasks", counts.open],
    ["Need worker", counts.worker],
    ["Need verify", counts.verify],
    ["Ready review", counts.review],
  ].forEach(([label, value]) => {
    const card = document.createElement("div");
    card.className = "progress-summary-card";
    card.innerHTML = `<span>${escapeHtml(label)}</span><strong>${value}</strong>`;
    target.appendChild(card);
  });
}

function renderTaskReviewPanel(target) {
  if (!target) return;
  const task = taskById(selectedTaskId) || (visibleTasks()[0] || null);
  target.innerHTML = "";
  if (!task) {
    target.innerHTML = `<div class="empty">Select a task to review</div>`;
    return;
  }
  const review = task.detail && task.detail.review_summary ? task.detail.review_summary : [];
  const promoteAction = (task.actions || []).find((action) => isTaskPromotionAction(action));
  const promoteCommand = promoteAction ? promoteAction.command : "";
  const contextValue = promoteCommand ? (promotionContextInputs[promoteCommand] || "") : "";
  const actionResult = promoteAction && actionRunState && actionRunState.command === promoteAction.command ? actionRunState : null;
  const isPromoting = Boolean(actionResult && actionResult.status === "running");
  const summaryItems = review.length
    ? review
    : [
        { label: "Task", value: `${task.id} - ${task.title}` },
        { label: "Status", value: task.display_status || task.status },
        { label: "Verification", value: task.verification_status || "missing" },
        { label: "Next action", value: task.next_action ? task.next_action.command : "None" },
      ];
  const reviewByLabel = Object.fromEntries(summaryItems.map((item) => [item.label, item.value || "None"]));
  const changedFiles = reviewByLabel["Changed files"] || "No file changes detected";
  const taskContents = reviewByLabel["Task contents"] || "No changed file preview available";
  const metaItems = summaryItems.filter((item) => !["Task", "Changed files", "Task contents"].includes(item.label));
  target.innerHTML = `
    <div class="task-review-head">
      <div>
        <span>${escapeHtml(plainTaskStatusLabel(task))}</span>
        <h3>${escapeHtml(task.title || task.id)}</h3>
        <p>${escapeHtml(plainTaskStatusLine(task))}</p>
      </div>
      <strong>${escapeHtml(task.id)}</strong>
    </div>
    <div class="task-review-layout">
      <div class="task-review-brief">
        ${metaItems.map((item) => `
          <div class="task-review-row">
            <span>${escapeHtml(item.label)}</span>
            <strong>${escapeHtml(item.value || "None")}</strong>
          </div>
        `).join("")}
        <div class="task-review-row stack">
          <span>Changed files</span>
          <pre>${escapeHtml(changedFiles)}</pre>
        </div>
      </div>
      ${promoteAction ? `
        <div class="review-approval-card">
          <div>
            <span>Human decision</span>
            <strong>Approve & promote</strong>
            <code>${escapeHtml(promoteCommand)}</code>
          </div>
          <label>
            <span class="label">Optional context</span>
            <textarea data-promotion-context rows="4" placeholder="Add reviewer context for this promotion...">${escapeHtml(contextValue)}</textarea>
          </label>
          <button type="button" data-review-promote ${isPromoting ? "disabled" : ""}>${escapeHtml(isPromoting ? "Promoting..." : "Approve & promote")}</button>
        </div>
      ` : `
        <div class="review-approval-card muted">
          <div>
            <span>Next step</span>
            <strong>${escapeHtml(plainNextStep(task.next_action ? task.next_action.label : task.lane))}</strong>
            <code>${escapeHtml(task.next_action ? task.next_action.command : "No approval action available")}</code>
          </div>
        </div>
      `}
    </div>
    <details class="task-review-preview" open>
      <summary>Changed content preview</summary>
      <pre>${escapeHtml(taskContents)}</pre>
    </details>
    ${actionResult && actionResult.status !== "running" ? renderActionResult(actionResult) : ""}
  `;
  const contextInput = target.querySelector("[data-promotion-context]");
  if (contextInput && promoteAction) {
    contextInput.addEventListener("input", (event) => {
      promotionContextInputs[promoteAction.command] = event.target.value;
    });
  }
  const promoteButton = target.querySelector("[data-review-promote]");
  if (promoteButton && promoteAction && !isPromoting) {
    promoteButton.addEventListener("click", () => executeAction(promoteAction, { approvedPromotion: true }));
  }
}

function renderProgressTask(gate) {
  const task = taskById(gate.task_id) || {};
  const row = document.createElement("article");
  row.className = `progress-task-row ${progressTaskTone(gate, task)}`;
  row.setAttribute("role", "listitem");
  row.setAttribute("aria-label", `${gate.task_id}: ${plainNextStep(gate.next_gate)}`);
  const command = gate.command || (task.next_action && task.next_action.command) || "None";
  row.innerHTML = `
    <div class="progress-task-main">
      <span>${escapeHtml(gate.task_id)}</span>
      <strong>${escapeHtml(task.title || "Untitled task")}</strong>
      <p>${escapeHtml(task.display_status || task.status || "unknown")} / ${escapeHtml(task.worker || "no worker")} / ${escapeHtml(task.lane || "unlaned")}</p>
    </div>
    <div class="progress-step-grid" aria-label="Readiness checklist for ${escapeHtml(gate.task_id)}">
      ${progressStepDefinitions().map((step) => {
        const state = progressStepState(gate, step.key);
        return `
          <div class="progress-step ${state}">
            <i aria-hidden="true"></i>
            <strong>${escapeHtml(step.label)}</strong>
            <small>${escapeHtml(progressStepLabel(state))}</small>
          </div>
        `;
      }).join("")}
    </div>
    <div class="progress-next-panel">
      <span>Next safe action</span>
      <p>${escapeHtml(plainNextStep(gate.next_gate))}</p>
      <code>${escapeHtml(command)}</code>
      <p>${escapeHtml(task.latest || "No recent task event recorded.")}</p>
    </div>
  `;
  row.addEventListener("click", () => {
    if (!task.id) return;
    selectedTaskId = task.id;
    selectedGoalSelection = null;
    selectedMapNode = null;
    render();
  });
  return row;
}

function progressStepDefinitions() {
  return [
    { key: "intake", label: "Intake" },
    { key: "worker_evidence", label: "Worker output" },
    { key: "verification", label: "Verification" },
    { key: "promotion_readiness", label: "Review preview" },
    { key: "human_decision", label: "Human decision" },
  ];
}

function progressStepState(gate, step) {
  if (gate[step]) return "done";
  if (gate.next_gate === "closed") return "skipped";
  const currentByNextGate = {
    run_worker: "worker_evidence",
    verify: "verification",
    promotion_preview: "promotion_readiness",
    human_decision: "human_decision",
  };
  return currentByNextGate[gate.next_gate] === step ? "current" : "pending";
}

function progressStepLabel(state) {
  const labels = {
    done: "Done",
    current: "Next",
    pending: "Waiting",
    skipped: "Skipped",
  };
  return labels[state] || "Waiting";
}

function progressTaskTone(gate, task) {
  if (gate.next_gate === "closed") return "ready";
  if (task.lane === "blocked" || ["failed", "verification_failed", "blocked"].includes(task.status)) return "blocked";
  if (gate.next_gate === "run_worker") return "waiting";
  if (gate.next_gate === "human_decision") return "ready";
  return "active";
}

function renderProjects() {
  const overview = snapshot.multi_project;
  byId("project-count").textContent = overview ? overview.total_projects : 0;
  const summary = byId("project-summary");
  const list = byId("project-list");
  summary.innerHTML = "";
  list.innerHTML = "";
  if (!overview) {
    list.innerHTML = `<div class="empty">Registry unavailable</div>`;
    return;
  }
  [
    ["Projects", overview.total_projects],
    ["Active", overview.active_projects],
    ["Missing", overview.missing_projects],
    ["Verify", overview.needs_verification],
  ].forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "project-stat";
    item.innerHTML = `<span>${label}</span><strong>${value}</strong>`;
    summary.appendChild(item);
  });
  if (!overview.projects.length) {
    list.innerHTML = `<div class="empty">No projects registered</div>`;
    return;
  }
  overview.projects.slice(0, 8).forEach((project) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `project-card ${project.project_id === selectedProjectId ? "selected" : ""} ${project.path_status === "missing" ? "missing" : ""}`;
    card.disabled = project.path_status === "missing";
    card.innerHTML = `
      <h3>${escapeHtml(project.name)} <span class="label">${escapeHtml(project.project_id)}</span></h3>
      <div class="task-meta">
        <span>${escapeHtml(project.status)}</span>
        <span>${escapeHtml(project.path_status)}</span>
        <span>${escapeHtml(project.branch || "unknown")}</span>
      </div>
      <div class="project-row"><span>tasks</span><strong>${project.total_tasks}</strong></div>
      <div class="project-row"><span>active</span><strong>${project.active_tasks}</strong></div>
      <div class="project-row"><span>verify</span><strong>${project.needs_verification}</strong></div>
      <div class="project-row"><span>review</span><strong>${project.ready_to_promote}</strong></div>
      <code>${escapeHtml(project.next_action || "None")}</code>
    `;
    card.addEventListener("click", async () => {
      if (project.path_status === "missing") return;
      selectedProjectId = project.project_id;
      selectedProjectName = project.name;
      selectedProjectPathStatus = project.path_status;
      selectedTaskId = null;
      await loadSnapshot(project.project_id);
    });
    list.appendChild(card);
  });
}

function renderInbox() {
  byId("inbox-count").textContent = snapshot.inbox ? snapshot.inbox.length : 0;
  const list = byId("inbox-list");
  list.innerHTML = "";
  if (!sectionExpanded("inbox")) return;
  if (!snapshot.inbox || !snapshot.inbox.length) {
    list.innerHTML = `<div class="empty">None</div>`;
    return;
  }
  snapshot.inbox.slice(0, 12).forEach((item) => {
    const div = document.createElement("div");
    div.className = `inbox-item ${item.priority <= 15 ? "urgent" : ""}`;
    div.innerHTML = `
      <strong>${escapeHtml(item.title)}</strong>
      <div class="task-meta">
        <span>${escapeHtml(plainInboxKind(item.kind))}</span>
        <span>${escapeHtml(item.scope)}</span>
        <span>${escapeHtml(item.path || "no path")}</span>
      </div>
      <p>${escapeHtml(item.message)}</p>
      <code>${escapeHtml(item.command || "None")}</code>
    `;
    list.appendChild(div);
  });
}

function plainProgressStep(step) {
  const labels = {
    intake: "Task created",
    worker_evidence: "Worker output recorded",
    verification: "Verification passed",
    promotion_readiness: "Review preview ready",
    human_decision: "Human decision recorded",
  };
  return labels[step] || String(step || "unknown").replaceAll("_", " ");
}

function plainInboxKind(kind) {
  const labels = {
    question: "Question",
    blocked_task: "Blocked task",
    task_attention: "Task attention",
    human_decision: "Human decision",
  };
  return labels[kind] || String(kind || "Item").replaceAll("_", " ");
}

function renderQuestions() {
  byId("question-count").textContent = (snapshot.questions || []).length;
  const list = byId("question-list");
  list.innerHTML = "";
  if (!sectionExpanded("promotion")) return;
  if (!snapshot.questions.length) {
    list.innerHTML = `<div class="empty">None</div>`;
    return;
  }
  snapshot.questions.forEach((item) => {
    list.appendChild(simpleItem(item.task_id, item.question, item.command));
  });
}

function renderPromotion() {
  byId("promotion-count").textContent = (snapshot.promotion_desk || []).length;
  const list = byId("promotion-list");
  list.innerHTML = "";
  if (!sectionExpanded("promotion")) return;
  if (!snapshot.promotion_desk.length) {
    list.innerHTML = `<div class="empty">None</div>`;
    return;
  }
  snapshot.promotion_desk.forEach((item) => {
    list.appendChild(simpleItem(item.task_id, item.title, item.command));
  });
}

function renderEvidence() {
  const selectedIds = selectedGoalTaskIds();
  const evidence = visibleEvidence();
  byId("evidence-count").textContent = evidence.length;
  const list = byId("evidence-list");
  list.innerHTML = "";
  if (!sectionExpanded("evidence")) return;
  if (!evidence.length) {
    list.innerHTML = `<div class="empty">${selectedIds.length ? "No linked evidence" : "None"}</div>`;
    return;
  }
  evidence.slice(0, 16).forEach((item) => {
    const div = document.createElement("div");
    div.className = "evidence-item";
    div.innerHTML = `<strong>${item.task_id}</strong><span>${escapeHtml(item.log_path || item.result_path || item.verification_log_path || "evidence")}</span>`;
    list.appendChild(div);
  });
}

function renderAttention() {
  const inboxCount = snapshot.inbox ? snapshot.inbox.length : 0;
  const questionCount = snapshot.questions.length;
  const promotionCount = snapshot.promotion_desk.length;
  const evidenceCount = visibleEvidence().length;
  const cards = [
    {
      key: "inbox",
      label: "Inbox",
      value: inboxCount,
      detail: inboxCount ? "human decisions waiting" : "clear",
      tone: inboxCount ? "urgent" : "",
    },
    {
      key: "promotion",
      label: "Questions",
      value: questionCount,
      detail: questionCount ? "blocked worker prompts" : "no open questions",
      tone: questionCount ? "urgent" : "",
    },
    {
      key: "promotion",
      label: "Review",
      value: promotionCount,
      detail: promotionCount ? "ready for preview" : "nothing ready",
      tone: promotionCount ? "ready" : "",
    },
    {
      key: "evidence",
      label: "Evidence",
      value: evidenceCount,
      detail: evidenceCount ? "recent task artifacts" : "no evidence yet",
      tone: evidenceCount ? "verify" : "",
    },
  ];
  byId("attention-count").textContent = cards.reduce((total, card) => total + card.value, 0);
  const list = byId("attention-list");
  list.innerHTML = "";
  cards.forEach((card) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `attention-card ${card.tone}`;
    button.setAttribute("aria-label", `${card.label}: ${card.value}. ${card.detail}`);
    button.innerHTML = `
      <span>${escapeHtml(card.label)}</span>
      <strong>${card.value}</strong>
      <p>${escapeHtml(card.detail)}</p>
    `;
    button.addEventListener("click", () => {
      if (Object.prototype.hasOwnProperty.call(sectionState, card.key)) {
        sectionState[card.key] = "expanded";
      }
      setCurrentPage(card.key, { updateHash: true });
    });
    list.appendChild(button);
  });
}

function sectionExpanded(name) {
  return sectionState[name] !== "collapsed";
}

function toggleSection(name) {
  if (!Object.prototype.hasOwnProperty.call(sectionState, name)) return;
  sectionState[name] = sectionExpanded(name) ? "collapsed" : "expanded";
  render();
  if (sectionExpanded(name)) {
    const target = document.querySelector(`#${name} .section-body button, #${name} .section-body a, #${name} .section-body [tabindex], #${name} .section-body code`);
    target?.focus?.();
  }
}

function applySectionState() {
  Object.entries(sectionState).forEach(([name, state]) => {
    const section = byId(name);
    if (!section) return;
    section.classList.toggle("expanded", state === "expanded");
    section.classList.toggle("collapsed", state === "collapsed");
    const trigger = section.querySelector("[data-toggle-section]");
    if (trigger) {
      trigger.setAttribute("aria-expanded", state === "expanded" ? "true" : "false");
    }
  });
}

function normalizePage(page) {
  const value = String(page || "").replace(/^#/, "");
  return Object.prototype.hasOwnProperty.call(pageSections, value) ? value : "orchestrator";
}

function pageFromHash() {
  return normalizePage(window.location.hash || "orchestrator");
}

function setCurrentPage(page, { updateHash = false, scrollTop = true } = {}) {
  const nextPage = normalizePage(page);
  currentPage = nextPage;
  const pageScope = { lanes: "workers", gates: "gates", promotion: "promotion", inbox: "inbox" };
  selectedMapNode = pageScope[nextPage] || null;
  if (nextPage === "lanes") agentsExpanded = true;
  (pageSections[nextPage] || []).forEach((section) => {
    if (Object.prototype.hasOwnProperty.call(sectionState, section)) sectionState[section] = "expanded";
  });
  if (updateHash && window.location.hash !== `#${nextPage}`) {
    window.history.pushState(null, "", `#${nextPage}`);
  }
  if (snapshot) render();
  if (scrollTop) {
    requestAnimationFrame(() => {
      byId("main-panel")?.scrollIntoView({ block: "start" });
      window.scrollTo({ top: 0, behavior: "auto" });
    });
  }
}

function applyPageVisibility() {
  const activeSections = new Set(pageSections[currentPage] || pageSections.orchestrator);
  document.querySelectorAll("[data-section], #context").forEach((section) => {
    const visible = activeSections.has(section.id);
    section.classList.toggle("page-hidden", !visible);
    section.setAttribute("aria-hidden", visible ? "false" : "true");
  });
  const pageName = pageNames[currentPage] || "Overview";
  byId("main-panel").setAttribute("aria-label", `${pageName} page`);
  document.body.dataset.page = currentPage;
}

function currentSection() {
  return currentPage;
}

function scrollActiveNavIntoView(link) {
  const nav = link.closest("nav");
  if (!nav) return;
  const navRect = nav.getBoundingClientRect();
  const linkRect = link.getBoundingClientRect();
  if (linkRect.left >= navRect.left && linkRect.right <= navRect.right) return;
  link.scrollIntoView({ block: "nearest", inline: "center" });
}

function updateActiveNav(section) {
  document.querySelectorAll("nav a").forEach((link) => {
    const active = link.getAttribute("href") === `#${section}`;
    link.classList.toggle("active", active);
    if (active) {
      link.setAttribute("aria-current", "page");
      scrollActiveNavIntoView(link);
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

function installScrollLinkedNav() {
  if (!("IntersectionObserver" in window)) return;
  const observer = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
    if (visible && visible.target.dataset.section) updateActiveNav(visible.target.dataset.section);
  }, { rootMargin: "-35% 0px -45% 0px", threshold: [0.05, 0.2, 0.6] });
  document.querySelectorAll("[data-section]").forEach((section) => observer.observe(section));
}

function simpleItem(title, body, command) {
  const div = document.createElement("div");
  div.className = "list-item";
  div.innerHTML = `<strong>${escapeHtml(title)}</strong><span>${escapeHtml(body)}</span><code>${escapeHtml(command || "None")}</code>`;
  return div;
}

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function isTypingTarget(target) {
  if (!target) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable;
}

const _rb = byId("refresh-button"); _rb?.addEventListener("click", () => loadSnapshot());
const _ccb = byId("clear-context-button"); _ccb?.addEventListener("click", () => clearContext());
const _ast = byId("agent-stack-toggle"); _ast?.addEventListener("click", () => {
  agentsExpanded = !agentsExpanded;
  renderLanes();
});
const _gf = byId("global-filter"); _gf?.addEventListener("input", (event) => {
  globalFilter = event.target.value;
  const currentTask = selectedTaskId ? taskById(selectedTaskId) : null;
  if (currentTask && !taskMatchesFilter(currentTask, globalFilter)) {
    selectedTaskId = firstVisibleTaskId();
  }
  render();
});
document.querySelectorAll("[data-toggle-section]").forEach((trigger) => {
  trigger.addEventListener("click", () => toggleSection(trigger.dataset.toggleSection));
  trigger.addEventListener("keydown", (event) => {
    if (event.key === " ") {
      event.preventDefault();
      toggleSection(trigger.dataset.toggleSection);
    }
  });
});
document.querySelectorAll("nav a").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    const section = link.getAttribute("href").slice(1);
    if (Object.prototype.hasOwnProperty.call(sectionState, section)) {
      sectionState[section] = "expanded";
    }
    setCurrentPage(section, { updateHash: true });
  });
});
window.addEventListener("hashchange", () => setCurrentPage(pageFromHash(), { scrollTop: true }));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && globalFilter && isTypingTarget(event.target)) {
    event.preventDefault();
    globalFilter = "";
    byId("global-filter").value = "";
    selectedTaskId = firstVisibleTaskId();
    render();
    return;
  }
  if (event.key === "Escape" && (selectedMapNode || selectedGoalSelection)) {
    clearContext();
    return;
  }
  if (isTypingTarget(event.target)) return;
  if (event.key === "g" && !event.metaKey && !event.ctrlKey && !event.altKey) {
    byId("orchestrator-command")?.focus?.();
    setCurrentPage("orchestrator", { updateHash: true });
    return;
  }
  if (event.key === "f" && !event.metaKey && !event.ctrlKey && !event.altKey) {
    event.preventDefault();
    byId("global-filter")?.focus?.();
    setCurrentPage("orchestrator", { updateHash: true, scrollTop: false });
    return;
  }
  if (event.key === "m" && !event.metaKey && !event.ctrlKey && !event.altKey) {
    setCurrentPage("map", { updateHash: true });
    return;
  }
  if (event.key === "l" && !event.metaKey && !event.ctrlKey && !event.altKey) {
    setCurrentPage("lanes", { updateHash: true });
  }
});
const _ap = byId("all-projects-button"); _ap?.addEventListener("click", async () => {
  selectedProjectId = null;
  selectedProjectName = null;
  selectedProjectPathStatus = null;
  selectedTaskId = null;
  selectedMapNode = null;
  selectedGoalSelection = null;
  await loadSnapshot(null);
});
currentPage = pageFromHash();
loadSnapshot().then(() => setCurrentPage(currentPage, { updateHash: window.location.hash !== `#${currentPage}`, scrollTop: false })).catch(() => {});
"""
