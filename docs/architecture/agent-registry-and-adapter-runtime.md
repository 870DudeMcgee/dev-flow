# Agent Registry And Adapter Runtime

Status: planning architecture. This document does not implement runtime behavior or expand the current shell-worker MVP.

Dev-Flow is a local-first control room for replaceable coding workers. The shell worker is the only current runtime contract, but future worker types need one stable layer for registration, invocation, permissions, routing, and evidence. This document defines that target architecture without making agents the source of truth.

Core rule: Dev-Flow owns state, verification, evidence, and promotion. Agents are replaceable runtimes. Workers propose. Dev-Flow records. Verification verifies. Humans promote.

Related routing design: [agent-selection-and-context-routing.md](agent-selection-and-context-routing.md) defines the future task-fit profile, context estimator, model capability profile, context pack builder, scout roles, and routing-quality feedback loop. It is planning architecture only until the registry/manual/shell-alignment sequence is active.

## 1. Problem

"Replaceable agents" are not real if every worker is wired directly into task execution. Dev-Flow needs a registry, adapter layer, permission model, and invocation lifecycle so local models, frontier APIs, manual review, and shell commands can all operate behind the same control-room contract.

Without this layer, provider details leak into core task logic, agent names become informal personalities, permission rules become implicit, and evidence becomes scattered across logs, chat transcripts, and provider-specific outputs. The result would drift away from the North Star: visible, isolated, recoverable work with sacred filesystem state.

The registry and runtime must make each agent a permissioned execution contract bound to:

- provider
- model
- model capability profile
- role
- adapter
- workspace
- allowed context
- allowed writes
- evidence trail
- routing rules

## 2. Provider Vs Agent Vs Role

A provider is how Dev-Flow talks to a backend. Provider configuration answers "what API, local service, or human handoff mechanism is available?" Examples:

- `openai`
- `anthropic`
- `xai`
- `google`
- `ollama`
- `lmstudio`
- `llama_cpp`
- `shell`
- `manual`

An agent is a named worker contract that binds a provider, model, role, adapter, and permission mode. Agent names are operational identifiers, not personalities. Examples:

- `qwen36-senior`
- `qwen-coder-fast`
- `test-agent`
- `openai-frontier-architect`
- `claude-reviewer`
- `gemini-large-context`
- `grok-current-research`
- `manual-frontier`

A role is what an agent is allowed and expected to do. Roles provide durable policy language that can outlive a specific provider or model. Examples:

- `local_senior_worker`
- `local_implementation_worker`
- `test_runner`
- `frontier_architecture_reviewer`
- `frontier_code_reviewer`
- `large_context_synthesizer`
- `current_research_reviewer`
- `manual_escalation_worker`

## 3. Folder Structure

Agent configuration should be durable and separate from per-task evidence. Registry files live under `.devflow/agents/` and `.devflow/providers/`. Task-specific packets, logs, outputs, and result summaries live under each task.

```text
.devflow/
  agents/
    registry.yaml
    roles.yaml
    policies.yaml
    routing.yaml
    <agent-id>/
      agent.yaml
      system_prompt.md
      allowed_roles.md
      local_notes.md
      performance.md
  providers/
    openai.yaml
    anthropic.yaml
    xai.yaml
    google.yaml
    ollama.yaml
    lmstudio.yaml
    llama_cpp.yaml
    shell.yaml
    manual.yaml
  tasks/
    <task-id>/
      task.yaml
      context.md
      constraints.md
      events.jsonl
      questions.jsonl
      verification.json
      agents/
        <agent-id>/
          packet.md
          raw_output.md
          result.yaml
          logs/
  workspaces/
    <task-id>/
      <agent-id>/
        repo/
```

The current MVP uses `.devflow/workspaces/<task-id>/` for the shell worker. The nested agent workspace shape is a future extension for multi-agent tasks. Until that extension is explicitly promoted, shell execution should continue to use the current workspace layout.

## 4. Permission Model

Permission modes define the maximum authority an agent can receive for a run:

- `read_only`: inspect bounded context and produce analysis only.
- `workspace_write`: write only inside the assigned isolated task workspace.
- `verify_only`: run explicit verification commands inside the assigned workspace.
- `docs_only`: write approved documentation artifacts only, usually inside the task workspace or approved docs path.
- `frontier_read_only`: send bounded context to a remote or expensive model for analysis without direct repository mutation.
- `manual_packet_only`: generate a copy-paste packet for a human-mediated model or manual reviewer.

Rules:

- No agent can promote to main.
- Remote or frontier models cannot directly mutate the repo.
- Local models can write only inside isolated task workspaces.
- Powerful models may see broader context, but that does not grant broader write access.
- Secrets and API keys must never be stored in repo files.
- Provider configs reference environment variables only.
- `task.yaml`, `events.jsonl`, `verification.json`, and raw logs remain Dev-Flow-owned evidence surfaces.
- Adapters may suggest verification, but authoritative verification belongs to Dev-Flow.

## 5. Agent Registry Schema

The registry is declarative. Core task logic should resolve an agent by ID, validate its policy, and pass a bounded request to the adapter.

```yaml
agents:
  qwen36-senior:
    provider: ollama
    model: qwen3:36b
    adapter: ollama_chat
    role: local_senior_worker
    tier: local
    default_mode: workspace_write
    workspace: isolated_task_workspace
    can_see:
      - task_packet
      - assigned_workspace
      - recent_events
      - verification_summary
    can_touch:
      - "<workspace>/**"
    cannot_touch:
      - "<main_checkout>/**"
      - "<task>/task.yaml"
      - "<task>/events.jsonl"
      - "<task>/verification.json"
      - ".git/**"
      - "src/devflow/_legacy/**"
    can_run_shell: false
    can_use_network: false
    can_promote: false

  test-agent:
    provider: shell
    model: local-shell
    adapter: shell
    role: test_runner
    tier: local
    default_mode: verify_only
    workspace: isolated_task_workspace
    can_see:
      - task_packet
      - assigned_workspace
      - verification_plan
    can_touch:
      - "<workspace>/**"
      - "<task>/logs/verify.log"
    cannot_touch:
      - "<main_checkout>/**"
      - ".git/**"
    can_run_shell: true
    can_use_network: false
    can_promote: false

  openai-frontier-architect:
    provider: openai
    model: gpt-5
    adapter: openai_responses
    role: frontier_architecture_reviewer
    tier: frontier
    default_mode: frontier_read_only
    workspace: none
    can_see:
      - architecture_packet
      - bounded_source_excerpts
      - failing_test_summary
    can_touch:
      - "<task>/agents/openai-frontier-architect/result.yaml"
      - "<task>/agents/openai-frontier-architect/raw_output.md"
    cannot_touch:
      - "<main_checkout>/**"
      - "<workspace>/**"
      - ".env*"
      - ".git/**"
    can_run_shell: false
    can_use_network: true
    can_promote: false
```

## 6. Provider Schema

Provider configs describe connection details without storing secrets. Secrets are environment variable names, not values.

```yaml
# .devflow/providers/openai.yaml
provider: openai
adapter: openai_responses
base_url: https://api.openai.com/v1
api_key_env: OPENAI_API_KEY
default_timeout_seconds: 120
```

```yaml
# .devflow/providers/anthropic.yaml
provider: anthropic
adapter: anthropic_messages
base_url: https://api.anthropic.com
api_key_env: ANTHROPIC_API_KEY
default_timeout_seconds: 120
```

```yaml
# .devflow/providers/xai.yaml
provider: xai
adapter: openai_compatible
base_url: https://api.x.ai/v1
api_key_env: XAI_API_KEY
default_timeout_seconds: 120
```

```yaml
# .devflow/providers/google.yaml
provider: google
adapter: gemini
api_key_env: GEMINI_API_KEY
default_timeout_seconds: 120
```

```yaml
# .devflow/providers/ollama.yaml
provider: ollama
adapter: ollama_chat
base_url: http://127.0.0.1:11434
api_key_env: null
default_timeout_seconds: 300
```

```yaml
# .devflow/providers/lmstudio.yaml
provider: lmstudio
adapter: openai_compatible
base_url: http://127.0.0.1:1234/v1
api_key_env: null
default_timeout_seconds: 300
```

```yaml
# .devflow/providers/llama_cpp.yaml
provider: llama_cpp
adapter: openai_compatible
base_url: http://127.0.0.1:8080/v1
api_key_env: null
default_timeout_seconds: 300
```

```yaml
# .devflow/providers/manual.yaml
provider: manual
adapter: manual_packet
delivery: copy_paste
api_key_env: null
default_timeout_seconds: null
```

## 7. Adapter Runtime

The adapter runtime should be boring Python. Core Dev-Flow code builds a request, validates permissions, calls an adapter, records evidence, and updates canonical state through existing Dev-Flow state transition rules.

```python
class AgentAdapter(Protocol):
    def run(self, request: AgentRequest) -> AgentResponse:
        ...
```

`AgentRequest` should include:

- `task_id`
- `agent_id`
- `role`
- `mode`
- `packet_path`
- `workspace_path`
- `model`
- `temperature`
- `max_output_tokens`
- `timeout_seconds`

`AgentResponse` should include:

- `status`
- `raw_output`
- `parsed_summary`
- `questions`
- `proposed_files`
- `usage`
- `provider_metadata`

Runtime lifecycle:

1. Resolve `agent_id` from the registry.
2. Resolve provider config and adapter type.
3. Validate requested mode against role and policy.
4. Build a bounded task packet from canonical Dev-Flow artifacts.
5. Prepare or validate the isolated workspace.
6. Invoke `AgentAdapter.run(request)` with sanitized environment and timeout policy.
7. Write raw output, result summary, questions, and logs under task-local agent evidence paths.
8. Append Dev-Flow-owned lifecycle events.
9. Update canonical task state only through Dev-Flow-owned state transitions.
10. Leave verification and promotion to separate Dev-Flow commands.

## 8. Task Fit And Context Routing Boundary

Dev-Flow should route by task fit and capability, not by agent name first. The future routing layer must classify the task, estimate required context and risk, build role-specific context packs, and choose the cheapest capable agent for each role. Agent IDs are selected only after Dev-Flow has a task-fit profile and eligible model capability profiles.

Minimum future artifacts:

- `task-fit.yaml`: task type, repo scope, context requirement, reasoning requirement, edit risk, architectural risk, verification complexity, context layer, and recommended tiers.
- `context-estimate.yaml`: relevant files, relevant lines, estimated tokens, tests needed, docs needed, task history tokens, and total context estimate.
- `context-pack.yaml`: role, context layer, included sources, excluded sources, estimated tokens, and truncation notes.
- `routing-decision.yaml`: selected planner, worker, reviewer, verifier, reasons, rejected agents, and policy version.
- `model-scorecard.jsonl`: post-run evidence about useful context, success rate, verification failures, rework, escalation, cost, and latency.

The planner may receive broad L4/L5 context. The worker should usually receive a bounded L1/L2 pack. The reviewer receives the diff, task contract, acceptance criteria, and targeted architecture notes. The verifier receives commands, logs, expected outputs, and verification history.

## 9. Routing Rules

Routing chooses which agent contract to invoke. It should be policy-driven and conservative, not a hidden autonomous scheduler.

Initial suggested routing:

- `qwen36-senior`: default local senior worker for implementation tasks that need reasoning but can remain local.
- `qwen-coder-fast`: mechanical or simple implementation where speed matters more than deep planning.
- `test-agent`: verification, focused test execution, and test failure reproduction.
- `claude-reviewer`: code review after repeated failures or when an external review pass is warranted.
- `openai-frontier-architect`: architecture uncertainty, cross-subsystem risk, model-routing changes, or high-impact design review.
- `gemini-large-context`: broad-context synthesis or document consolidation where large input windows matter.
- `grok-current-research`: current external API, model, ecosystem, or research questions.
- `manual-frontier`: copy-paste escalation packet when API use is not desired or credentials are unavailable.

Routing inputs can include task type, allowed files, failure count, verification status, deterministic context size, required context layer, requested role, model capability profile, and cost policy. Routing output should be recorded as evidence: selected agent, rejected agents, reason, mode, packet path, and policy version.

## 10. MVP Sequence

Build this layer incrementally. Do not jump directly to a general-purpose agent framework.

1. Architecture document only.
2. Agent registry loading.
3. `agent list`, `agent show`, and `agent packet` commands.
4. Manual adapter.
5. Shell adapter alignment.
6. Deterministic task-fit and context-size estimation.
7. Role-based context pack builder.
8. Ollama adapter for Qwen.
9. OpenAI-compatible adapter for LM Studio and Grok-style APIs.
10. Native OpenAI, Anthropic, and Gemini adapters.
11. Local scout reports as optional evidence.
12. Routing engine.
13. Metrics: local success rate, frontier escalations, verification failures, rework, useful context limits, and cost avoided.

Each step should preserve the shell-worker control-room contract and add evidence before automation. A future implementation step is acceptable only when it makes task execution more visible, isolated, recoverable, or reviewable.

## 11. Non-Goals

- Do not build a general-purpose agent framework.
- Do not let agents own canonical task state.
- Do not hardcode Qwen, OpenAI, Claude, Gemini, or Grok into core logic.
- Do not build routing before one local and one manual adapter work.
- Do not add dashboards before evidence exists.
- Do not store provider secrets in repo files.
- Do not make model power equivalent to write authority.
- Do not let workers self-certify verification or merge readiness.
