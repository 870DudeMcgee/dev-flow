# Agent Registry And Adapter Runtime

Status: active architecture with current registry/adapter guardrails for the local-first Dev-Flow runtime.

Dev-Flow is a local-first control room for replaceable coding workers. Shell remains the stable direct-edit runtime, while manual proof-agent handoffs and registered local worker profiles are permissioned evidence surfaces. Future worker types need one stable layer for registration, invocation, permissions, routing, and evidence. This document defines that target architecture without making agents the source of truth.

Core rule: Dev-Flow owns state, verification, evidence, and promotion. Agents are replaceable runtimes. Workers propose. Dev-Flow records. Verification verifies. Humans promote.

Current runtime note: stable executable adapters remain intentionally narrow. Shell/manual adapters are stable runtime adapters, and local model routes are explicit evidence surfaces. Non-local adapters such as `openai_compatible`, `openai_chat`, `anthropic_messages`, and `gemini` are not executable through normal `task run` worker lookup unless they are the approved local Ornith/Qwen lanes.

Model profiles and execution surfaces are separate. A profile should name the model or route and record capabilities: reliable context, vision, thinking, code focus, speed, input modalities, tool access, and tuned archetypes such as `ui_visual_review` or `browser_ui_review`. A surface defines authority: advisory evidence, patch proposal evidence, local WorkerEvidence, shell execution, verification, apply, or promotion. Do not turn any normal model profile into a single-job identity like `patch-proposer`, `reviewer`, `planner`, `summarizer`, or `implementer` unless it is explicitly a separate wrapper profile for that surface.

Milestone 16 implemented the model-agnostic registry boundary: runtime eligibility/refusal projection, role-scoped context-pack evidence, derived task-local agent evidence summaries, selected-agent evidence, and explicit local worker profiles. Milestone 17 adds evidence-only task-fit/context routing: stable fit, scout, route, and scorecard commands write derived artifacts and recommended next commands. These surfaces are not autonomous routing and do not create tasks, run workers, apply patches, verify, promote, commit, push, or publish.

Related routing design: [agent-selection-and-context-routing.md](agent-selection-and-context-routing.md) defines the implemented Milestone 17 task-fit profile, context estimator, scout roles, routing-decision evidence, and routing-quality scorecards. Autonomous best-available worker assignment, non-local task-run execution, and policy-driven routing remain deferred until a future autonomy policy explicitly promotes them.

Current Codex/local-worker session behavior is defined by
`/Users/jewelbait/.codex/session-operating-contract.md`.

## 1. Problem

"Replaceable agents" are not real if every worker is wired directly into task execution. Dev-Flow needs a registry, adapter layer, permission model, and invocation lifecycle so local models, supervisor handoffs, manual review, and shell commands can all operate behind the same control-room contract.

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

A provider is how Dev-Flow talks to a backend. Provider configuration answers "what local service or human handoff mechanism is available?" Examples:

- `ornith-35b`
- `qwen-27b-q5-mtp`
- `openai-codex`
- `shell`
- `manual`

An agent is a named worker contract that binds a provider, model, role, adapter, capabilities, and permission mode. Agent names are operational identifiers, not personalities or single-job labels. Examples:

- `ornith-35b`
- `qwen-27b-q5-mtp`
- `hermes-codex-gpt55`
- `devflow-shell-worker`
- `devflow-manual-codex-worker`

A role is what an agent is allowed and expected to do. Roles provide durable policy language that can outlive a specific provider or model. Examples:

- `local_senior_worker`
- `local_implementation_worker`
- `test_runner`
- `codex_supervisor`
- `local_scout`
- `local_judge`
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
    ornith-35b.yaml
    qwen-27b-q5-mtp.yaml
    openai-codex.yaml
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
- `promotion_candidate`: prepare promotion evidence for human review without pushing or merging.
- `supervisor_read_only`: send bounded context to a remote or expensive model for analysis without direct repository mutation.
- `patch_proposal_only`: write patch-proposal evidence only; existing Dev-Flow review, dry-run, apply, verification, and promotion gates remain mandatory.
- `manual_packet_only`: generate a copy-paste packet for a human-mediated model or manual reviewer.

Rules:

- No agent can promote to main.
- Human approval is required before promotion, publishing, pushing, or merging.
- Remote or frontier models cannot directly mutate the repo.
- Local models can write only inside isolated task workspaces.
- Powerful models may see broader context, but that does not grant broader write access.
- Capability metadata guides selection; permission modes and command surfaces grant or refuse actions.
- Vision and browser use are separate dimensions: `vision=true` means the model can reason over images/screenshot evidence, while browser access must come from the runtime/tool surface that captured or exposes browser context.
- Secrets and API keys must never be stored in repo files.
- Provider configs reference environment variables only.
- `task.yaml`, `events.jsonl`, `verification.json`, and raw logs remain Dev-Flow-owned evidence surfaces.
- Adapters may suggest verification, but authoritative verification belongs to Dev-Flow.

## 5. Agent Registry Schema

The registry is declarative. Core task logic should resolve an agent by ID, validate its policy, and pass a bounded request to the adapter.

```yaml
agents:
  local-gateway-judge-packet:
    provider: local_qwen_27b_mtp
    model: qwen-27b-q5-mtp
    adapter: openai_compatible
    role: local_implementation_worker
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

  codex-supervisor:
    provider: openai
    model: gpt-5
    adapter: openai_responses
    role: codex_supervisor
    tier: frontier
    default_mode: supervisor_read_only
    workspace: none
    can_see:
      - architecture_packet
      - bounded_source_excerpts
      - failing_test_summary
    can_touch:
      - "<task>/agents/codex-supervisor/result.yaml"
      - "<task>/agents/codex-supervisor/raw_output.md"
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
version: 1
provider: ollama
adapter: ollama_chat
base_url: http://127.0.0.1:11434
api_key_env: null
default_timeout_seconds: 600
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

Current local lifecycle:

1. Resolve `agent_id` from the registry and provider metadata.
2. Project runtime maturity, execution surface, next command, and refusal reason through `agent_runtime`.
3. Build role-scoped context-pack evidence when `devflow agent context-pack` is invoked.
4. Summarize existing shell/manual evidence when `devflow agent evidence` or operating-layer projections need it.
5. Show local provider/profile status with `agent catalog`.
6. Run explicit shell/manual/local-evidence commands only when the command itself is invoked; no selector runs a worker by itself.
7. Leave verification and promotion to separate Dev-Flow commands.

Future adapter lifecycle:

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

Dev-Flow should route by task fit and capability, not by agent name first. The current local selector is intentionally narrower: it ranks installed registry agents for an explicit role and records selected-agent evidence, but it does not infer task fit or run workers. The broader routing layer must classify the task, estimate required context and risk, build role-specific context packs, and choose the cheapest capable agent for each role. Agent IDs are selected only after Dev-Flow has a task-fit profile and eligible model capability profiles.

Milestone 17 implements the first evidence-only task-fit/context-routing slice: task-fit, scout, routing-decision, and routing-quality artifacts are stable derived evidence, while autonomous worker assignment and non-local task-run execution remain excluded.

Minimum routing artifacts:

- `task-fit.yaml`: task type, repo scope, context requirement, reasoning requirement, edit risk, architectural risk, verification complexity, context layer, and recommended tiers.
- `context-estimate.yaml`: relevant files, relevant lines, estimated tokens, tests needed, docs needed, task history tokens, and total context estimate.
- `context-pack.yaml`: role, context layer, included sources, excluded sources, estimated tokens, and truncation notes.
- `routing-decision.yaml`: selected or unresolved planner, worker, reviewer, verifier roles, reasons, rejected agents, recommended next commands, and policy version.
- `model-scorecard.jsonl`: post-run evidence about useful context, success rate, verification failures, rework, escalation, cost, and latency.

The planner may receive broad L4/L5 context. The worker should usually receive a bounded L1/L2 pack. The reviewer receives the diff, task contract, acceptance criteria, and targeted architecture notes. The verifier receives commands, logs, expected outputs, and verification history.

## 9. Routing Rules

Routing chooses which agent contract to invoke. It should be policy-driven and conservative, not a hidden autonomous scheduler.

Initial suggested routing:

- When current local-worker use is explicitly opted in, use the active Ornith
  scout/build/compression lane and Qwen judge/review lane from
  [docs/local-worker-policy.md](../local-worker-policy.md).
- `test-agent`: verification, focused test execution, and test failure reproduction.
- `claude-reviewer`: code review after repeated failures or when an external review pass is warranted.
- `codex-supervisor`: architecture uncertainty, cross-subsystem risk, model-routing changes, or high-impact design review.
- `gemini-large-context`: broad-context synthesis or document consolidation where large input windows matter.
- `grok-current-research`: current external API, model, ecosystem, or research questions.
- `manual-supervisor`: copy-paste escalation packet when API use is not desired or credentials are unavailable.

Routing inputs can include task type, allowed files, failure count, verification status, deterministic context size, required context layer, requested role, model capability profile, and cost policy. Routing output should be recorded as evidence: selected agent, rejected agents, reason, mode, packet path, and policy version.

## 10. MVP Sequence

Build this layer incrementally. Do not jump directly to a general-purpose agent framework.

Implemented through Milestone 17:

1. Architecture document.
2. Agent registry loading.
3. `agent list`, `agent show`, and `agent packet` commands.
4. Manual adapter.
5. Shell adapter alignment.
6. Runtime eligibility/refusal projection for shell and manual profiles.
7. Role-based context-pack evidence through `agent context-pack`.
8. Derived task-local evidence summary through `agent evidence`.
9. Evidence-only task-fit and context estimation through `devflow task fit`.
10. Evidence-only local scout signal capture through `devflow task scout`.
13. Evidence-only candidate eligibility, rejection, unresolved-role, and next-command routing decisions through `devflow task route`.
14. Evidence-only post-run routing-quality scorecards through `devflow task scorecard`.
15. Registry-visible Hermes/local profiles with capability metadata and explicit local evidence surfaces.
16. `devflow agent catalog [--provider <id>] --json` for read-only registry visibility.

Deferred until future specs promote them:

1. Full arbitrary-task context-size estimation beyond the Milestone 17 deterministic evidence slice.
2. Autonomous best-available model routing by task and role.
3. General OpenAI-compatible adapter task-run execution beyond the approved local Ornith/Qwen lanes.
4. Native OpenAI, Anthropic, and Gemini task-run execution adapters.
5. Routing engines that assign workers, invoke workers, or verify/promote based on routing evidence.
6. Metrics that drive autonomous routing policy, cost optimization, or provider selection beyond the Milestone 17 scorecard artifacts.

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
