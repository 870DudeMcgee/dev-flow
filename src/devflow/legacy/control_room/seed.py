from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


BOOTSTRAP_GOAL = "bootstrap-devflow-filesystem"

REQUIRED_SUCCESS_CRITERIA = [
    "project-context-exists",
    "context-classification-exists",
    "layered-context-exists",
    "bootstrap-goal-exists",
    "registries-exist",
    "locks-explained",
    "reports-marked-derived",
    "docs-reference-structure",
]

DIRECTORIES = [
    ".devflow/project",
    f".devflow/goals/{BOOTSTRAP_GOAL}/context",
    f".devflow/goals/{BOOTSTRAP_GOAL}/tasks",
    ".devflow/context/active",
    ".devflow/context/reference",
    ".devflow/context/archived",
    ".devflow/context/deprecated",
    ".devflow/context/rejected",
    ".devflow/layers/product",
    ".devflow/layers/architecture",
    ".devflow/layers/implementation",
    ".devflow/layers/verification",
    ".devflow/layers/operations",
    ".devflow/workers/profiles",
    ".devflow/models",
    ".devflow/locks",
    ".devflow/reports/daily",
    ".devflow/reports/task-summaries",
    ".devflow/reports/model-scorecards",
    ".devflow/tasks",
    ".devflow/providers",
    ".devflow/agents",
]

JSONL_FILES = [
    ".devflow/project/decisions.jsonl",
    ".devflow/project/open-questions.jsonl",
    f".devflow/goals/{BOOTSTRAP_GOAL}/events.jsonl",
    f".devflow/goals/{BOOTSTRAP_GOAL}/questions.jsonl",
    f".devflow/goals/{BOOTSTRAP_GOAL}/decisions.jsonl",
    ".devflow/layers/architecture/decisions.jsonl",
    ".devflow/models/scoreboard.jsonl",
]

JSON_FILES = [
    f".devflow/goals/{BOOTSTRAP_GOAL}/success.json",
]

IMPLEMENTATION_KNOWN_GAPS_CONTEXT_MARKER = (
    "<!-- devflow:context-contract implementation-known-gaps@1 -->"
)
IMPLEMENTATION_CURRENT_SLICE_CONTEXT_MARKER = (
    "<!-- devflow:context-contract implementation-current-slice@1 -->"
)

SEED_FILES = {
    ".devflow/project/project.yaml": """id: devflow
name: Dev-Flow
status: active_product_building_loop
purpose: "Local operating layer for turning rough ideas into verified product implementations."
canonical_state_note: "Machine-readable runtime and planning state lives under .devflow/project, .devflow/goals, .devflow/tasks, and related YAML/JSON/JSONL files."
current_active_goal: bootstrap-devflow-filesystem
authority_note: "Human instructions and active source-of-truth docs outrank derived reports. Reports and summaries are useful evidence, not canonical authority."
source_documents:
  - docs/DEVFLOW_SOURCE_OF_TRUTH.md
  - docs/README.md
  - docs/local-worker-policy.md
  - docs/verification-ledger.md
""",
    ".devflow/project/vision.md": """# Vision

DevFlow is a local operating layer for turning rough ideas into verified product implementations.
""",
    ".devflow/project/current-state.md": """# Current State

Status: active product-building loop with definition, specification, planning, bounded execution, verification, and human-controlled next decisions.
""",
    ".devflow/project/architecture.md": """# Architecture

Dev-Flow owns durable state, workspaces, locks, status, logs, reports, verification, and merge readiness. Workers are replaceable executors.
""",
    ".devflow/project/glossary.md": """# Glossary

- Operating layer: DevFlow's local product-building coordination layer.
- Worker: A replaceable executor such as the current shell worker or the manual proof-agent handoff.
- Canonical state: Machine-readable YAML, JSON, and JSONL files that define current truth.
""",
    f".devflow/goals/{BOOTSTRAP_GOAL}/goal.yaml": f"""id: {BOOTSTRAP_GOAL}
status: active
objective: "Establish the initial Dev-Flow filesystem/context structure and align documentation with the control-loop architecture."
constraints:
  - preserve existing repository content
  - avoid broad refactors
  - do not implement autonomous runners, autonomous routing, dashboards, or swarm behavior
  - keep canonical state machine-readable
  - keep Markdown concise and orienting
  - classify stale, deprecated, rejected, and archived context instead of deleting history
success_criteria:
  - id: project-context-exists
    description: ".devflow/project/ exists with project orientation files."
    verification:
      type: file_exists
      path: .devflow/project/project.yaml
  - id: context-classification-exists
    description: ".devflow/context/ separates active, reference, archived, deprecated, and rejected material."
    verification:
      type: file_exists
      path: .devflow/context/active/README.md
  - id: layered-context-exists
    description: ".devflow/layers/ contains product, architecture, implementation, verification, and operations layers."
    verification:
      type: file_exists
      path: .devflow/layers/architecture/contracts.md
  - id: bootstrap-goal-exists
    description: "The bootstrap filesystem goal exists with canonical goal files."
    verification:
      type: file_exists
      path: .devflow/goals/bootstrap-devflow-filesystem/goal.yaml
  - id: registries-exist
    description: "Model and worker registries exist, with the stable manual proof-agent registered separately from placeholder future registries."
    verification:
      type: file_exists
      path: .devflow/workers/registry.yaml
  - id: locks-explained
    description: ".devflow/locks/ explains lock purpose without creating live lock state."
    verification:
      type: file_exists
      path: .devflow/locks/README.md
  - id: reports-marked-derived
    description: "Reports are clearly marked as non-authoritative derived material."
    verification:
      type: file_exists
      path: .devflow/reports/README.md
  - id: docs-reference-structure
    description: "Repository docs reference the seeded .devflow structure."
    verification:
      type: file_contains
      path: docs/DEVFLOW_SOURCE_OF_TRUTH.md
      text: "DevFlow is the local operating layer"
iteration_policy:
  max_attempts_per_task: 3
  escalate_after_failures: 3
  require_verification: true
  require_human_completion_approval: true
""",
    f".devflow/goals/{BOOTSTRAP_GOAL}/status.md": """# Status

Status: active

The bootstrap filesystem/context structure exists and can be repaired by `devflow init`.
""",
    f".devflow/goals/{BOOTSTRAP_GOAL}/success.json": json.dumps(
        {
            "goal_id": BOOTSTRAP_GOAL,
            "status": "pending",
            "criteria": [
                {"id": criteria_id, "status": "pending"}
                for criteria_id in REQUIRED_SUCCESS_CRITERIA
            ],
        },
        indent=2,
    )
    + "\n",
    f".devflow/goals/{BOOTSTRAP_GOAL}/context/active.md": "# Active Context\n\nUse docs/DEVFLOW_SOURCE_OF_TRUTH.md as current authority.\n",
    f".devflow/goals/{BOOTSTRAP_GOAL}/context/relevant-files.md": "# Relevant Files\n\n- docs/DEVFLOW_SOURCE_OF_TRUTH.md\n- docs/README.md\n- docs/local-worker-policy.md\n- docs/verification-ledger.md\n",
    f".devflow/goals/{BOOTSTRAP_GOAL}/context/constraints.md": "# Constraints\n\nKeep changes focused on shell-worker control-room behavior, the manual proof-agent handoff, durable filesystem state, verification, and human-controlled promotion.\n",
    f".devflow/goals/{BOOTSTRAP_GOAL}/context/deferred-ideas.md": "# Deferred Ideas\n\nNon-local adapters, autonomous routing, dashboards, databases, and autonomous control loops remain deferred until their registry sequence step is active.\n",
    f".devflow/goals/{BOOTSTRAP_GOAL}/context/rejected-ideas.md": "# Rejected Ideas\n\nDo not revive legacy software-factory ceremonies as process authority.\n",
    f".devflow/goals/{BOOTSTRAP_GOAL}/tasks/README.md": "# Goal Tasks\n\nTask references for this goal live here when needed.\n",
    ".devflow/context/active/README.md": "# Active Context\n\nCurrent guidance promoted for use by workers.\n",
    ".devflow/context/reference/README.md": "# Reference Context\n\nUseful background that is not current canonical state.\n",
    ".devflow/context/archived/README.md": "# Archived Context\n\nHistorical material preserved for audit, not active instruction.\n",
    ".devflow/context/deprecated/README.md": "# Deprecated Context\n\nSuperseded guidance that should not drive new work.\n",
    ".devflow/context/rejected/README.md": "# Rejected Context\n\nIdeas explicitly rejected so they are not rediscovered as current plans.\n",
    ".devflow/layers/product/vision.md": "# Product Vision\n\nA local operating layer for turning rough ideas into verified product implementations.\n",
    ".devflow/layers/product/user-problems.md": "# User Problems\n\nParallel AI coding work needs visibility, isolation, recoverability, and reviewable results.\n",
    ".devflow/layers/product/success-metrics.md": "# Success Metrics\n\nShell-worker tasks can be created, run, verified, listed, shown, and reviewed without mutating the main checkout.\n",
    ".devflow/layers/architecture/system-map.md": "# System Map\n\nFilesystem state is the source of truth. CLI commands operate on tasks, workspaces, logs, verification, and reports.\n",
    ".devflow/layers/architecture/boundaries.md": "# Boundaries\n\nDev-Flow is not a model wrapper, coding agent, dashboard-first product, or legacy workflow ceremony.\n",
    ".devflow/layers/architecture/state-model.md": "# State Model\n\nCanonical state lives in YAML, JSON, and JSONL files. Derived reports are non-authoritative.\n",
    ".devflow/layers/architecture/contracts.md": """# Contracts

Active contracts:

- [../../../docs/DEVFLOW_SOURCE_OF_TRUTH.md](../../../docs/DEVFLOW_SOURCE_OF_TRUTH.md) defines the active product-building loop and ownership boundaries.
- [../../../docs/README.md](../../../docs/README.md) lists active docs and quarantine policy.
- [../../../docs/local-worker-policy.md](../../../docs/local-worker-policy.md) defines the compact local worker boundary when local model work is explicitly needed.

Quarantined historical docs are recovery material only and must not be loaded as active context by default.
""",
    ".devflow/layers/implementation/current-slice.md": f"# Current Slice\n\n{IMPLEMENTATION_CURRENT_SLICE_CONTEXT_MARKER}\n\nKeep the shell-worker MVP stable while building the local operating-layer control surface over existing control-room evidence. Browser actions may execute only supervisor-classified read-only Dev-Flow commands; non-local adapters, routing engines, databases, and autonomous dashboard mutation surfaces remain out of scope.\n",
    ".devflow/layers/implementation/file-map.md": "# File Map\n\n- src/devflow/control_room/: control-room runtime services.\n- tests/: focused behavior tests.\n- archive material: quarantined outside the active repository tree.\n",
    ".devflow/layers/implementation/known-gaps.md": f"# Known Gaps\n\n{IMPLEMENTATION_KNOWN_GAPS_CONTEXT_MARKER}\n\nMerge readiness is still human-controlled. Non-local adapters, routing, and scheduling remain out of scope until the manual proof-agent and shell alignment stay stable.\n\nLegacy surfaces still exist outside the frozen MVP path and must not be treated as active product authority.\n",
    ".devflow/layers/implementation/active-constraints.md": "# Active Constraints\n\n- Do not add databases, non-local adapters, routing engines, or autonomous routing.\n",
    ".devflow/layers/verification/verification-strategy.md": "# Verification Strategy\n\nPrefer focused pytest coverage and shell-worker acceptance checks.\n",
    ".devflow/layers/verification/commands.md": "# Verification Commands\n\nWhen running verification inside task worktrees (where .venv is not present locally), reference the virtualenv from the repository root, e.g.:\n- /absolute/path/to/repo/.venv/bin/python -m pytest tests/test_control_room_shell.py -q\n",
    ".devflow/layers/verification/known-failures.md": "# Known Failures\n\nRecord current known failures here when they are validated.\n",
    ".devflow/layers/operations/workflow.md": "# Workflow\n\nUse small, verifiable changes against the active product-building loop.\n",
    ".devflow/layers/operations/agent-coordination.md": "# Agent Coordination\n\nWorkers should operate from bounded task context and isolated workspaces.\n",
    ".devflow/layers/operations/recovery.md": "# Recovery\n\nFailures should leave clear logs, status, and next actions.\n",
    ".devflow/layers/operations/promotion.md": "# Promotion\n\nHumans control promotion to the main checkout.\n",
    ".devflow/workers/registry.yaml": """version: 1
authority: "Placeholder registry for future worker definitions. The stable proof agent is built into the Agent Registry loader. No worker availability is claimed in this future registry."
permission_modes:
  - read_only
  - review_only
  - test_only
  - workspace_write
  - verify_only
workers: []
schema_intent:
  worker_id: "Stable worker identifier."
  kind: "Execution adapter kind, such as shell, manual, ollama, openai_compatible, or another registry-approved adapter."
  profile: "Permission and resource profile under .devflow/workers/profiles/."
  enabled: "Whether Dev-Flow may consider the worker available."
""",
    ".devflow/workers/profiles/README.md": "# Worker Profiles\n\nFuture worker permission profiles live here.\n",
    ".devflow/models/registry.yaml": """version: 1
authority: "Placeholder registry for model metadata. Future provider/model records must follow docs/DEVFLOW_SOURCE_OF_TRUTH.md. No model availability or quality claim is recorded here yet."
models: []
schema_intent:
  model_id: "Stable model identifier."
  provider: "Provider or runtime, such as shell, manual, ollama, lmstudio, llama.cpp, OpenAI, Anthropic, xAI, Gemini, or another future adapter."
  intended_use: "Planner, implementer, reviewer, debugger, or other bounded role."
  enabled: "Whether Dev-Flow may consider the model available."
  notes: "Human-readable constraints or setup notes."
""",
    ".devflow/locks/README.md": "# Locks\n\nLive lock files will coordinate write ownership. No live locks are seeded by default.\n",
    ".devflow/reports/README.md": """# Reports

Reports are derived summaries generated from canonical state and evidence.

Reports are useful for review and orientation, but they are never authoritative. If a report disagrees with YAML, JSON, JSONL, events, logs, or verification artifacts, the canonical files win.
""",
    ".devflow/reports/daily/README.md": "# Daily Reports\n\nDerived daily summaries live here.\n",
    ".devflow/reports/task-summaries/README.md": "# Task Summaries\n\nDerived task summaries live here.\n",
    ".devflow/reports/model-scorecards/README.md": "# Model Scorecards\n\nDerived model scorecards live here.\n",
    ".devflow/tasks/README.md": "# Tasks\n\nRuntime task directories live here.\n",
    ".devflow/providers/ollama.yaml": """version: 1
id: ollama
provider: ollama
adapter: ollama_chat
base_url: http://127.0.0.1:11434
default_timeout_seconds: 600
enabled: true
""",
    ".devflow/providers/openai.yaml": """id: openai
provider: openai
adapter: openai_chat
base_url: https://api.openai.com/v1
api_key_env: OPENAI_API_KEY
default_timeout_seconds: 300
enabled: true
""",
    ".devflow/providers/anthropic.yaml": """id: anthropic
provider: anthropic
adapter: anthropic_messages
base_url: https://api.anthropic.com/v1
api_key_env: ANTHROPIC_API_KEY
default_timeout_seconds: 300
enabled: true
""",
    ".devflow/providers/gemini.yaml": """id: gemini
provider: gemini
adapter: gemini
base_url: https://generativelanguage.googleapis.com
api_key_env: GEMINI_API_KEY
default_timeout_seconds: 300
enabled: true
""",
    ".devflow/providers/openrouter.yaml": """id: openrouter
provider: openrouter
adapter: openai_compatible
base_url: https://openrouter.ai/api/v1
api_key_env: OPENROUTER_API_KEY
default_timeout_seconds: 300
enabled: true
""",
    ".devflow/providers/xai.yaml": """id: xai
provider: xai
adapter: openai_compatible
base_url: https://api.x.ai/v1
api_key_env: XAI_API_KEY
default_timeout_seconds: 300
enabled: true
""",
    ".devflow/providers/grok.yaml": """id: grok
provider: grok
adapter: openai_compatible
base_url: https://api.x.ai/v1
api_key_env: GROK_API_KEY
default_timeout_seconds: 300
enabled: true
""",
    ".devflow/providers/openai-codex.yaml": """id: openai-codex
provider: openai-codex
adapter: hermes_profile
base_url: https://chatgpt.com/backend-api/codex
default_timeout_seconds: 900
enabled: true
""",
    ".devflow/providers/qwen-27b-q5-mtp.yaml": """id: qwen-27b-q5-mtp
provider: qwen-27b-q5-mtp
adapter: openai_compatible
base_url: http://127.0.0.1:8083/v1
enabled: true
""",
    ".devflow/providers/ornith-35b.yaml": """id: ornith-35b
provider: ornith-35b
adapter: openai_compatible
base_url: http://127.0.0.1:8084/v1
enabled: true
""",
    ".devflow/providers/openai_compatible.yaml": """id: openai_compatible
provider: openai_compatible
adapter: openai_compatible
base_url: http://127.0.0.1:8000/v1
api_key_env: OPENAI_COMPATIBLE_API_KEY
default_timeout_seconds: 300
enabled: true
""",
    ".devflow/agents/roles.yaml": """version: 1
roles:
  implementation_worker:
    description: "Consume a bounded Dev-Flow task packet, edit only the assigned isolated workspace, produce structured results."
    enabled: true
  local_senior_worker:
    description: "Local senior worker for implementation tasks."
    enabled: true
  test_runner:
    description: "Runs verification tests."
    enabled: true
  codex_code_reviewer:
    description: "Frontier tier code reviewer."
    enabled: true
  tester:
    description: "Executes test scripts."
    enabled: true
  senior:
    description: "Senior implementation agent."
    enabled: true
  codex_supervisor:
    description: "Codex supervisor for explicit handoff and accountability."
    enabled: true
""",
    ".devflow/agents/registry.yaml": """version: 1
default_agent: devflow-manual-codex-worker
agents:
  devflow-manual-codex-worker:
    provider: manual
    model: human-launched-codex
    adapter: manual
    role: implementation_worker
    tier: manual
    default_mode: workspace_write
    execution_mode: human_launched_agent
    workspace: isolated_task_workspace
    can_see:
      - task_packet
      - assigned_workspace
      - recent_events
      - verification_plan
      - verification_summary
    can_touch:
      - "<workspace>/**"
      - "<task>/agents/devflow-manual-codex-worker/result.md"
      - "<task>/agents/devflow-manual-codex-worker/questions.jsonl"
      - "<task>/agents/devflow-manual-codex-worker/worker_failed.json"
    cannot_touch:
      - "<main_checkout>/**"
      - "<task>/task.yaml"
      - "<task>/events.jsonl"
      - "<task>/verification.json"
      - "<task>/merge-readiness.json"
      - ".git/**"
    allowed_reads:
      - "<task>/packet.json"
      - "<task>/events.jsonl"
      - "<task>/questions.jsonl"
      - "<task>/agents/devflow-manual-codex-worker/handoff.md"
      - "<workspace>/**"
    allowed_writes:
      - "<workspace>/**"
      - "<task>/agents/devflow-manual-codex-worker/result.md"
      - "<task>/agents/devflow-manual-codex-worker/questions.jsonl"
      - "<task>/agents/devflow-manual-codex-worker/worker_failed.json"
    forbidden_writes:
      - "<main_checkout>/**"
      - "<task>/task.yaml"
      - "<task>/events.jsonl"
      - "<task>/verification.json"
      - "<task>/merge-readiness.json"
      - "<task>/packet.json"
      - ".git/**"
    required_outputs:
      - "On completion, write <task>/agents/devflow-manual-codex-worker/result.md with status, summary, changed files, and suggested verification."
      - "When blocked, append one blocked_question JSON object to <task>/agents/devflow-manual-codex-worker/questions.jsonl."
      - "When failed, write <task>/agents/devflow-manual-codex-worker/worker_failed.json with summary, error_type, evidence, and next_safe_action."
    completion_rules:
      - "Edit only files under <workspace>."
      - "Never edit the main checkout, .git, <task>/task.yaml, <task>/events.jsonl, <task>/verification.json, or promotion artifacts."
      - "Stop after writing exactly one terminal evidence artifact."
      - "Dev-Flow verification is required after result.md; worker completion is not promotion readiness."
    can_run_shell: false
    can_use_network: false
    can_promote: false
    enabled: true

  ornith-builder:
    provider: ornith-35b
    model: ornith-35b
    adapter: openai_compatible
    role: implementation_worker
    tier: strong_local
    default_mode: workspace_write
    execution_mode: automated
    workspace: isolated_task_workspace
    can_see:
      - task_packet
      - assigned_workspace
      - recent_events
      - verification_plan
      - verification_summary
    can_touch:
      - "<workspace>/**"
      - "<task>/agents/ornith-builder/proposal.patch"
      - "<task>/agents/ornith-builder/raw_output.md"
      - "<task>/agents/ornith-builder/result.md"
      - "<task>/agents/ornith-builder/run.json"
      - "<task>/agents/ornith-builder/logs/**"
      - "<task>/agents/ornith-builder/questions.jsonl"
      - "<task>/agents/ornith-builder/worker_failed.json"
    cannot_touch:
      - "<main_checkout>/**"
      - "<task>/task.yaml"
      - "<task>/events.jsonl"
      - "<task>/verification.json"
      - "<task>/merge-readiness.json"
      - ".git/**"
    allowed_reads:
      - "<task>/packet.json"
      - "<task>/events.jsonl"
      - "<task>/questions.jsonl"
      - "<workspace>/**"
    allowed_writes:
      - "<workspace>/**"
      - "<task>/agents/ornith-builder/proposal.patch"
      - "<task>/agents/ornith-builder/raw_output.md"
      - "<task>/agents/ornith-builder/result.md"
      - "<task>/agents/ornith-builder/run.json"
      - "<task>/agents/ornith-builder/logs/**"
      - "<task>/agents/ornith-builder/questions.jsonl"
      - "<task>/agents/ornith-builder/worker_failed.json"
    forbidden_writes:
      - "<main_checkout>/**"
      - "<task>/task.yaml"
      - "<task>/events.jsonl"
      - "<task>/verification.json"
      - "<task>/merge-readiness.json"
      - "<task>/packet.json"
      - ".git/**"
    required_outputs:
      - "On completion, write <task>/agents/ornith-builder/proposal.patch and <task>/agents/ornith-builder/result.md with status, summary, changed files, and suggested verification."
      - "Always preserve raw model output in <task>/agents/ornith-builder/raw_output.md and run metadata in <task>/agents/ornith-builder/run.json."
      - "When blocked, append one blocked_question JSON object to <task>/agents/ornith-builder/questions.jsonl."
      - "When failed, write <task>/agents/ornith-builder/worker_failed.json with summary, error_type, evidence, and next_safe_action."
    completion_rules:
      - "Propose changes only as a unified diff in proposal.patch; do not directly edit the main checkout."
      - "Never edit the main checkout, .git, <task>/task.yaml, <task>/events.jsonl, <task>/verification.json, or promotion artifacts."
      - "Dev-Flow must apply proposal.patch to the isolated workspace and run verification after this worker completes."
      - "Worker completion is not promotion readiness."
    can_run_shell: false
    can_use_network: false
    can_promote: false
    enabled: false

""",
}

CONTEXT_CONGRUENCE_RULES = [
    {
        "path": ".devflow/layers/implementation/known-gaps.md",
        "marker": IMPLEMENTATION_KNOWN_GAPS_CONTEXT_MARKER,
        "forbidden": [
            "No schema validation exists yet",
            "No command creates or repairs this structure deterministically",
        ],
    },
    {
        "path": ".devflow/layers/implementation/current-slice.md",
        "marker": IMPLEMENTATION_CURRENT_SLICE_CONTEXT_MARKER,
        "forbidden": [
            "Current implementation slice: seed the `.devflow/` filesystem/context structure",
            "No runtime automation is part of this slice.",
        ],
    },
]


def initialize_seed(root: Path, project_seed: Any | None = None) -> None:
    for directory in DIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)

    seed_files = dict(SEED_FILES)
    if project_seed is not None:
        if hasattr(project_seed, "model_dump"):
            payload = project_seed.model_dump(mode="json", exclude_none=False)
        elif isinstance(project_seed, dict):
            payload = project_seed
        else:
            raise TypeError("project_seed must be a mapping or Pydantic model")
        seed_files[".devflow/project/project.yaml"] = yaml.safe_dump(payload, sort_keys=False)

    for path, content in seed_files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(content, encoding="utf-8")

    for path in JSONL_FILES:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=True)


def validate_seed_contract(root: Path) -> list[str]:
    errors: list[str] = []

    for directory in DIRECTORIES:
        path = root / directory
        if not path.is_dir():
            errors.append(f"{directory}: missing directory")

    for path in SEED_FILES:
        target = root / path
        if not target.is_file():
            errors.append(f"{path}: missing file")

    for path in JSONL_FILES:
        target = root / path
        if not target.is_file():
            errors.append(f"{path}: missing file")
            continue
        _validate_jsonl(path, target, errors)

    for path in JSON_FILES:
        target = root / path
        if not target.is_file():
            errors.append(f"{path}: missing file")
            continue
        _validate_json(path, target, errors)

    _validate_project_yaml(root / ".devflow/project/project.yaml", errors)
    _validate_goal_yaml(root / f".devflow/goals/{BOOTSTRAP_GOAL}/goal.yaml", errors)
    _validate_empty_registry(root / ".devflow/workers/registry.yaml", "workers", errors)
    _validate_empty_registry(root / ".devflow/models/registry.yaml", "models", errors)
    _validate_reports_readme(root / ".devflow/reports/README.md", errors)
    _validate_context_congruence(root, errors)
    return errors


def _validate_json(display_path: str, path: Path, errors: list[str]) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{display_path}: invalid JSON: {exc.msg}")
        return
    if display_path.endswith("/success.json"):
        if payload.get("goal_id") != BOOTSTRAP_GOAL:
            errors.append(f"{display_path}: goal_id must be {BOOTSTRAP_GOAL}")
        if not isinstance(payload.get("criteria"), list) or not payload["criteria"]:
            errors.append(f"{display_path}: criteria must be a non-empty list")


def _validate_jsonl(display_path: str, path: Path, errors: list[str]) -> None:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{display_path}:{line_number}: invalid JSONL: {exc.msg}")


def _validate_project_yaml(path: Path, errors: list[str]) -> None:
    display_path = ".devflow/project/project.yaml"
    if not path.exists():
        return
    data = _read_simple_yaml_map(path)
    project_id = data.get("project_id") or data.get("id")
    if project_id != "devflow":
        _validate_managed_project_yaml(display_path, data, errors)
        return
    for key in ("id", "name", "status", "purpose", "current_active_goal", "source_documents"):
        if key not in data:
            errors.append(f"{display_path}: missing {key}")
    if data.get("id") != "devflow":
        errors.append(f"{display_path}: id must be devflow")
    if data.get("current_active_goal") != BOOTSTRAP_GOAL:
        errors.append(f"{display_path}: current_active_goal must be {BOOTSTRAP_GOAL}")
    if not isinstance(data.get("source_documents"), list) or not data["source_documents"]:
        errors.append(f"{display_path}: source_documents must be a non-empty list")


def _validate_managed_project_yaml(display_path: str, data: dict[str, object], errors: list[str]) -> None:
    for key in ("schema_version", "project_id", "name", "status", "root_path", "source_control", "remote_publication"):
        if key not in data:
            errors.append(f"{display_path}: missing {key}")
    if data.get("schema_version") != 1:
        errors.append(f"{display_path}: schema_version must be 1")
    source_control = data.get("source_control")
    if not isinstance(source_control, dict):
        errors.append(f"{display_path}: source_control must be a mapping")
    else:
        if source_control.get("mode") not in {"none", "local_git", "remote_git", "github_managed"}:
            errors.append(f"{display_path}: source_control.mode is invalid")
    remote_publication = data.get("remote_publication")
    if not isinstance(remote_publication, dict):
        errors.append(f"{display_path}: remote_publication must be a mapping")
    elif remote_publication.get("push_allowed") is not False and remote_publication.get("push_allowed") is not True:
        errors.append(f"{display_path}: remote_publication.push_allowed must be boolean")


def _validate_goal_yaml(path: Path, errors: list[str]) -> None:
    display_path = f".devflow/goals/{BOOTSTRAP_GOAL}/goal.yaml"
    if not path.exists():
        return
    data = _read_simple_yaml_map(path)
    for key in ("id", "status", "objective", "constraints", "success_criteria", "iteration_policy"):
        if key not in data:
            errors.append(f"{display_path}: missing {key}")
    if data.get("id") != BOOTSTRAP_GOAL:
        errors.append(f"{display_path}: id must be {BOOTSTRAP_GOAL}")
    if not isinstance(data.get("constraints"), list) or not data["constraints"]:
        errors.append(f"{display_path}: constraints must be a non-empty list")
    if not isinstance(data.get("success_criteria"), list) or not data["success_criteria"]:
        errors.append(f"{display_path}: success_criteria must be a non-empty list")
    else:
        criteria_ids = set()
        for item in data["success_criteria"]:
            if isinstance(item, dict):
                criteria_ids.add(item.get("id"))
            elif isinstance(item, str) and item.startswith("id:"):
                criteria_ids.add(_strip_yaml_quotes(item.split(":", 1)[1].strip()))
        missing_ids = [item for item in REQUIRED_SUCCESS_CRITERIA if item not in criteria_ids]
        if missing_ids:
            errors.append(
                f"{display_path}: missing success_criteria ids: {', '.join(missing_ids)}"
            )


def _validate_empty_registry(path: Path, list_key: str, errors: list[str]) -> None:
    display_path = f".devflow/{'workers' if list_key == 'workers' else 'models'}/registry.yaml"
    if not path.exists():
        return
    data = _read_simple_yaml_map(path)
    if data.get("version") != 1:
        errors.append(f"{display_path}: version must be 1")
    if data.get(list_key) != []:
        errors.append(f"{display_path}: {list_key} must be an empty placeholder list")
    authority = str(data.get("authority", "")).lower()
    if list_key == "workers" and "no worker availability is claimed" not in authority:
        errors.append(f"{display_path}: authority must avoid worker availability claims")
    if list_key == "models" and "no model availability" not in authority:
        errors.append(f"{display_path}: authority must avoid model availability claims")
    if not isinstance(data.get("schema_intent"), dict) or not data["schema_intent"]:
        errors.append(f"{display_path}: schema_intent must be a non-empty map")


def _validate_reports_readme(path: Path, errors: list[str]) -> None:
    display_path = ".devflow/reports/README.md"
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8").lower()
    if "derived" not in content or "never authoritative" not in content:
        errors.append(f"{display_path}: reports must be marked derived and never authoritative")


def _validate_context_congruence(root: Path, errors: list[str]) -> None:
    for rule in CONTEXT_CONGRUENCE_RULES:
        display_path = str(rule["path"])
        path = root / display_path
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        marker = str(rule["marker"])
        if marker not in content:
            errors.append(f"{display_path}: missing context contract marker: {marker}")
        for forbidden in rule["forbidden"]:
            if forbidden in content:
                errors.append(f"{display_path}: stale context contradicts runtime: {forbidden}")


def _read_simple_yaml_map(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8").splitlines()
    data: dict[str, object] = {}
    current_key: str | None = None

    for raw_line in lines:
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith(" ") and ":" in raw_line:
            key, value = raw_line.split(":", 1)
            current_key = key.strip()
            data[current_key] = _parse_simple_yaml_value(value.strip())
            continue
        if current_key and raw_line.startswith("  - "):
            existing = data.setdefault(current_key, [])
            if not isinstance(existing, list):
                existing = []
                data[current_key] = existing
            existing.append(_strip_yaml_quotes(raw_line.strip()[2:].strip()))
            continue
        if current_key and raw_line.startswith("  ") and ":" in raw_line:
            existing_map = data.setdefault(current_key, {})
            if isinstance(existing_map, list):
                continue
            if not isinstance(existing_map, dict):
                existing_map = {}
                data[current_key] = existing_map
            key, value = raw_line.strip().split(":", 1)
            existing_map[key.strip()] = _parse_simple_yaml_value(value.strip())

    return data


def _parse_simple_yaml_value(value: str) -> object:
    if value == "":
        return {}
    if value == "[]":
        return []
    if value == "true":
        return True
    if value == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return _strip_yaml_quotes(value)


def _strip_yaml_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
