# Context Agent Service

Status: future architecture idea. This document does not enable autonomous
routing, provider-backed worker execution, hidden memory, automatic patching,
verification, promotion, merge, or push.

Dev-Flow can become more token-efficient by separating "knowing the project"
from "doing the work." Instead of asking a powerful orchestrator to repeatedly
answer every repo-context question for every worker, Dev-Flow can introduce a
local Context Agent: a source-grounded service that keeps project context warm
and answers narrow context questions for planners, workers, reviewers, and
verifiers.

This idea extends the context-layer and local-worker direction in
[agent-selection-and-context-routing.md](agent-selection-and-context-routing.md),
[local-model-worker-pool.md](local-model-worker-pool.md), and
[../local-model-runtime.md](../local-model-runtime.md).

## 1. Real-World Scenario

Imagine a multi-hour Dev-Flow task: "Fix gateway command routing and update the
dashboard status panel."

A capable orchestrator may need a broad view:

- `AGENTS.md`
- product north star
- control-room MVP docs
- command registry rules
- worker boundary rules
- local model runtime docs
- current git diff
- task history
- verification ledger
- relevant source files and tests

That context can easily become tens of thousands of tokens before the model
does useful work. During the task, several workers ask small context questions:

```text
Implementation worker:
"I am editing command routing. What invariant do I need to preserve?"

Docs worker:
"What did we decide about Hermes owning worker state?"

Reviewer:
"Which tests or evidence should I expect for a local-model worker change?"

Verifier:
"What is the minimum acceptable verification for documentation-only changes?"
```

Today, a powerful orchestrator might answer each question from its own giant
prompt. That is wasteful: the same project rules, architecture, and decision
history are repeatedly loaded into expensive model context.

With a Context Agent, workers ask narrow questions against a warmed project
context:

```text
Worker -> Context Agent:
"For command routing, what source-of-truth rule matters?"

Context Agent -> Worker:
"Use hermes_cli/commands.py-style central command registry patterns as the
analogy, but in Dev-Flow preserve docs/devmode-contract.md as process
authority. Do not create hidden alias dispatch. Relevant Dev-Flow docs:
AGENTS.md, docs/devmode-contract.md, docs/architecture/agent-selection-and-context-routing.md."
```

The worker receives a compact answer with source references instead of carrying
the whole repo memory in its own prompt.

## 2. Core Idea

The Context Agent is a local, read-only model service optimized for project
context retrieval and source-grounded summarization.

It is not the final decision-maker. It does not apply patches. It does not
verify readiness. It does not promote. It answers questions like:

- "Which docs govern this subsystem?"
- "What constraints apply before editing this file?"
- "What did we decide about local model runtime boundaries?"
- "Which tests usually cover this behavior?"
- "What stale context should I avoid?"
- "What context layer does this task appear to need?"

The agent is useful because it can keep a large, repeated context pack warm:

- active product docs
- architecture docs
- code map and subsystem indexes
- task packet summaries
- recent decisions and handoffs
- verification ledger summaries
- current diff summary
- selected source snippets

Workers then receive only the answer they need.

## 3. Why This Is Lighter Than A Giant Orchestrator

A powerful orchestrator has to hold many responsibilities at once:

```text
goal + plan + repo context + architecture + memory + tool schemas
+ current diff + task state + worker coordination + final judgment
```

A Context Agent has a narrower contract:

```text
Given source-backed project context, answer one context question compactly.
Return citations, caveats, and confidence.
```

The expected savings come from three places:

1. Less repeated prompt stuffing. Workers can receive hundreds of tokens of
   targeted context instead of tens of thousands of broad project context.
2. Cheaper model tier. The Context Agent can often be smaller and local because
   it retrieves, summarizes, and cites; it does not need to own hard planning.
3. Cache reuse. A long-context local runtime can keep common project context
   hot, making repeated context questions faster and cheaper.

The orchestrator becomes an executive function:

```text
Orchestrator:
"Worker A, implement the command change. Ask the Context Agent for subsystem
rules. Worker B, update docs. Ask the Context Agent for prior decisions."
```

Instead of:

```text
Orchestrator:
"I will personally reread every architecture document and answer every worker
subquestion."
```

## 4. Why oMLX Or Similar Long-Context Caching Matters

Coding agents repeatedly revisit the same context:

- system instructions
- repo rules
- architecture documents
- task state
- file summaries
- test strategy
- prior decisions

The slow part is often not only generation tokens per second. It is the time
spent processing the huge prompt before the model starts producing useful
output.

A runtime with hot RAM plus cold SSD KV cache can reduce that repeated prefill
cost. The Context Agent can keep the common project context warm in RAM and
spill older reusable KV blocks to SSD. When workers ask follow-up questions, the
runtime may restore previously processed context instead of recomputing the
entire prompt.

Practical effect:

```text
Normal local runner:
"What tests cover this?" -> reread giant repo/session context -> answer starts

Cached context runner:
"What tests cover this?" -> restore reused context blocks -> answer starts sooner
```

This does not make the model smarter. It makes the project memory cheaper to
reuse.

## 5. Source-Grounded Contract

The Context Agent must be treated as a source router and summarizer, not as
truth.

Every answer should include:

- source file paths or artifact ids
- short cited snippets or summaries
- confidence level
- known missing context
- whether the answer is current authority or historical context
- suggested next lookup when confidence is low

Example response shape:

```yaml
answer: >
  Documentation-only changes normally require git diff --check and targeted
  stale-context searches, not full pytest.
sources:
  - path: AGENTS.md
    why: Verification Escalation Policy
  - path: docs/verification-ledger.md
    why: Current verification cost guidance
confidence: high
authority: current
missing_context: []
```

This prevents a fast local model from becoming a fast hallucination amplifier.

## 6. Runtime Boundary

The Context Agent should follow the same local-runtime boundary as other
Dev-Flow local models:

- Dev-Flow must not load model weights in-process.
- The model runs behind a local HTTP boundary.
- Inputs are bounded context packs and explicit questions.
- Outputs are evidence, not truth.
- Worker and orchestration state stay owned by Dev-Flow.
- No source edits, patch application, verification, promotion, merge, or push.

The service may be backed by:

- Ollama for baseline local operation.
- llama.cpp for GGUF/MTP experiments and native timing metrics.
- oMLX or another long-context cached runtime for repeated project-context
  sessions on Apple Silicon.

The runtime is replaceable. The contract matters more than the model brand.

## 7. Proposed Architecture

```text
Planner / Worker / Reviewer / Verifier
        |
        | narrow context question
        v
Context Agent API
        |
        | retrieves/builds bounded context pack
        v
Source Index + Task Artifacts + Current Docs + Current Diff
        |
        | warmed prompt / cached KV blocks
        v
Local Long-Context Model Runtime
        |
        | compact cited answer
        v
WorkerEvidence / context-answer artifact
```

Dev-Flow should persist context answers as evidence under the task:

```text
.devflow/tasks/<task-id>/context-answers/<answer-id>/
  question.md
  answer.yaml
  sources.json
  run.json
```

This gives later reviewers and route-quality analysis something durable to
inspect.

## 8. Example Questions

Good Context Agent questions:

- "What files define worker permission boundaries?"
- "What is the current rule for documentation-only verification?"
- "What docs are authoritative for local model runtime?"
- "What previous handoffs mention registry-backed local workers?"
- "Which files should a reviewer inspect for task packet changes?"
- "What context layer does this task likely need, and why?"

Bad Context Agent questions:

- "Should we ship this?"
- "Apply the patch."
- "Run verification and mark ready."
- "Decide product strategy."
- "Ignore the current docs and infer the intended architecture."

## 9. Implementation Phases

### Phase 1: Deterministic Context Answer Artifacts

Add a read-only command that accepts a task id and question, builds a bounded
context pack from current docs/artifacts, and writes a context-answer artifact.

No model cache assumptions yet. Use the existing local model HTTP boundary.

Example future command:

```bash
devflow context ask <task-id> \
  --question "What verification applies to this doc-only change?" \
  --profile local-context-agent
```

### Phase 2: Source Index And Context Pack Reuse

Add deterministic source indexes:

- current-authority docs
- subsystem docs
- stale/historical docs
- task artifact summaries
- common test ownership map

The Context Agent should receive indexes and selected snippets, not an
unbounded recursive repo dump.

### Phase 3: Cached Local Runtime Evaluation

Evaluate a long-context cached runtime such as oMLX for the Context Agent role.
Measure:

- time to first token
- prompt/prefill time
- repeated-question latency
- answer source accuracy
- token volume avoided in worker prompts
- failure rate versus deterministic lookup alone

The benchmark should compare:

1. Worker receives full broad context.
2. Worker asks Context Agent and receives compact answer.
3. Context Agent with baseline local runtime.
4. Context Agent with long-context cache runtime.

### Phase 4: Routing Integration

Allow planners and workers to request context-answer artifacts before execution.
The routing layer can recommend asking the Context Agent when:

- estimated context layer is L3 or higher
- repeated architecture decisions are likely
- task touches worker/runtime boundaries
- stale context risk is high
- worker model useful context is smaller than estimated task context

This should remain explicit and evidence-producing. Do not introduce invisible
memory injection.

## 10. Risks

- Hallucinated authority: mitigated by citations and confidence.
- Stale context poisoning: mitigated by source classification and stale-context
  searches.
- Hidden coupling: mitigated by keeping the runtime behind a replaceable HTTP
  boundary.
- Cache overconfidence: KV cache can reduce latency, but it does not prove
  correctness.
- Worker dependency loops: workers should ask bounded questions, not outsource
  judgment.
- Token savings illusion: measure actual worker prompt reduction and task
  outcomes before treating this as a win.

## 11. Success Criteria

The idea is worth implementing only if evidence shows:

- worker prompts get materially smaller
- repeated context questions answer faster
- answers include correct current-authority sources
- workers make fewer stale-context mistakes
- orchestrator prompts carry less repo background
- verification and promotion authority remain unchanged

If it merely adds another model call without reducing prompt size, latency, or
context errors, it is not worth the complexity.

## 12. Short Version

The Context Agent is a local, cached, source-grounded project-memory service.
It lets workers ask, "What context do I need?" without forcing a powerful
orchestrator or every worker to reread the entire project on every turn.

The model does not become the authority. Dev-Flow remains the authority over
state, evidence, verification, and promotion. The Context Agent keeps the map
warm.
