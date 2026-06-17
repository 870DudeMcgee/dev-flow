# Model Capability Taxonomy And Routing Engine

Status: planning proposal — next step after milestone-closure checkpoint. This document defines the capability taxonomy, profile schema, routing decision tree, and implementation plan for matching tasks to the best model from a heterogeneous fleet.

This extends [agent-registry-and-adapter-runtime.md](agent-registry-and-adapter-runtime.md) and [agent-selection-and-context-routing.md](agent-selection-and-context-routing.md). The existing evidence-only routing (`devflow task fit`, `devflow task route`, `devflow task scorecard`) remains the stable entry point. This doc defines the *routing intelligence* layer that makes those commands choose the right model for the job.

## 1. Problem

Dev-Flow manages a heterogeneous fleet with wildly different model capabilities:

| Dimension | Range in fleet |
|---|---|
| Context window | 32k (Qwen Coder 1.5B) → 1,000,000+ (DeepSeek V4 Pro) |
| Vision | none → full multimodal (Gemma 4, Qwen 3.6) |
| Thinking/reasoning | none → always-on (Gemma 4) |
| Code specialization | general-purpose → heavily code-tuned (Qwen Coder family) |
| Speed | instant (1.5B) → very slow (36B full context) |
| Cost | local-free → OpenRouter paid/expensive |
| Architecture | dense → MoE (affects per-token speed vs context ceiling) |
| Reliability | experimental → production-proven |
| FIM/insert support | none → supported (Qwen Coder family) |
| Tool calling | none → reliable |

The current routing (`router.py` + `local_agent_discovery.py`) does not use most of these dimensions. It picks by tier and name matching only:

```
current:  tier == "strong_local"  →  pick by string match on role name
needed:   task requires vision + thinking + 64k context  →  pick cheapest capable model
```

This means:
- **Overpay**: expensive frontier models get dispatched for tasks a 7B coder could handle
- **Underutilize**: local models with 262k context, vision, and thinking sit idle while cheaper-but-weaker models get picked
- **Mismatch**: code-specialist models (Qwen Coder) are not preferred over general-purpose models for pure coding tasks
- **No vision routing**: Gemma 4's screenshot-reviews never happen because no task asks for them
- **Cost blindness**: DeepSeek V4 Flash free tier is never considered before the paid Pro tier

## 2. Capability Profile Schema

Every model — local or remote — gets a structured capability profile. This replaces the current ad-hoc `ModelCapabilityProfile` with a complete multi-dimensional schema.

### 2.1 Static Dimensions (from manifest, provider metadata, or explicit registration)

```yaml
# .devflow/agents/profiles/<profile-id>.yaml — or inline in registry.yaml
model_capability_profile:
  # Identity
  model_id: qwopus:latest
  provider: ollama
  architecture: qwen35moe           # qwen35moe | qwen2 | gemma4 | deepseek_v4 | …
  architecture_class: moe             # dense | moe | unknown
  parameter_count_billions: 36.0
  active_parameters_billions: ~       # null for dense; ~3.0 for Qwen36 MoE

  # Context
  advertised_context_tokens: 262144
  reliable_context_tokens: 245000     # verified real-world, not advertised
  context_utilization_quality: high   # high | medium | low — how well it uses full context
  
  # Modalities
  vision: true
  vision_quality: good                # none | basic | good | excellent
  audio: false
  tools: true
  tool_quality: good                  # none | basic | good | excellent
  
  # Reasoning
  thinking: true                      # native chain-of-thought
  thinker_type: always_on             # none | optional | always_on
  reasoning_quality: high             # low | medium | high | excellent

  # Code specialization
  code_focus: general_purpose         # general_purpose | code_specialist | frontier_general | frontier_coder
  fim_support: false                  # fill-in-middle / insert capability

  # Speed
  real_speed_class: slow              # instant | fast | medium | slow | very_slow
  measured_time_to_first_token_ms: 2000
  measured_tokens_per_second: 25

  # Cost
  cost_class: local_free              # local_free | openrouter_free | openrouter_paid | openrouter_expensive
  cost_per_million_input_tokens: 0.0
  cost_per_million_output_tokens: 0.0

  # Reliability
  trust_level: high                   # experimental | name_only | manifest_verified | production_proven
  scorecard_accuracy: 0.0             # populated from post-run quality feedback, 0.0 = unknown

  # Allowed roles — same as current registry
  allowed_roles:
    - implementation_worker
    - reviewer
    - summarizer
    - planner
    - scout

  # Tuned aliases (for models with purpose-built parameter presets)
  tuned_aliases:
    - alias: local-planner-128k
      purpose: planning with 128k context
      overrides:
        num_ctx: 131072
    - alias: local-devflow
      purpose: balanced devflow implementation
      overrides:
        num_ctx: 65536
```

### 2.2 Dynamic Dimensions (populated from real runs via scorecard)

```yaml
# Updated after each task — lives in task-local scorecard or registry overlay
model_runtime_profile:
  model_id: qwopus:latest
  
  # Recent performance
  last_10_tasks:
    successes: 8
    failures: 1
    escalations_needed: 1
    verification_first_pass: 7
  
  # Measured effective context
  actual_useful_context_tokens: 200000  # learned from real usage, not advertised
  context_degradation_threshold: 180000 # where quality observably drops
  
  # Speed under load
  avg_latency_seconds: 45
  p95_latency_seconds: 90
  
  # Cost tracking
  total_cost_incurred: 0.0
  
  # Role-specific quality scores
  role_scores:
    implementation_worker: 0.85
    reviewer: 0.72
    planner: 0.91
    summarizer: 0.88
```

### 2.3 Task Archetype Schema (routing input)

Every task gets classified into one archetype during `devflow task fit`. The archetype encodes *what the task needs* — the routing engine then matches against the capability profiles.

```yaml
task_archetype:
  # Classification
  archetype_id: feature_implementation
  archetype_family: code_work         # code_work | research | review | planning | documentation
  
  # Required dimensions
  min_context_tokens: 8000
  max_context_tokens: 32000           # hard ceiling — above this, reject candidate
  requires_vision: false
  requires_thinking: recommended       # none | optional | recommended | required
  requires_tools: false
  preferred_code_focus: code_specialist # any | general_purpose | code_specialist | frontier
  preferred_architecture: any          # any | dense | moe
  
  # Risk
  edit_risk: medium                    # none | low | medium | high | critical
  architectural_risk: low
  
  # Cost sensitivity
  max_cost_class: local_free           # local_free | openrouter_free | openrouter_paid | unlimited
  
  # Speed sensitivity
  preferred_speed: fast                # any | fast | medium | slow
```

Full archetype catalog (extends the vocabulary from agent-selection-and-context-routing.md):

```yaml
archetype_catalog:
  trivial_edit:
    archetype_family: code_work
    min_context: 2000
    max_context: 8000
    requires_vision: false
    requires_thinking: none
    preferred_code_focus: code_specialist
    edit_risk: low
    max_cost: local_free
    preferred_speed: fast
    example: "Fix typo in docstring"
    good_for: qwen2.5-coder:1.5b, local-coder-tiny

  simple_implementation:
    archetype_family: code_work
    min_context: 8000
    max_context: 32000
    requires_vision: false
    requires_thinking: optional
    preferred_code_focus: code_specialist
    edit_risk: low
    max_cost: local_free
    preferred_speed: fast
    example: "Add input validation to one function"
    good_for: qwen2.5-coder:7b, local-coder-fast, qwen2.5-coder:14b

  complex_implementation:
    archetype_family: code_work
    min_context: 16000
    max_context: 64000
    requires_vision: false
    requires_thinking: recommended
    preferred_code_focus: code_specialist
    edit_risk: medium
    max_cost: local_free
    preferred_speed: medium
    example: "Implement file upload component with drag-and-drop"
    good_for: qwen2.5-coder:32b, local-coder-heavy, qwopus, local-devflow

  multi_file_refactor:
    archetype_family: code_work
    min_context: 32000
    max_context: 128000
    requires_vision: false
    requires_thinking: recommended
    preferred_code_focus: code_specialist
    edit_risk: high
    max_cost: openrouter_free
    preferred_speed: medium
    example: "Extract auth subsystem into independent package"
    good_for: qwen2.5-coder:32b, qwopus (local), deepseek-v4-flash (if exceeds local ctx)

  architecture_design:
    archetype_family: planning
    min_context: 32000
    max_context: 256000
    requires_vision: false
    requires_thinking: required
    preferred_code_focus: any
    edit_risk: low
    architectural_risk: high
    max_cost: openrouter_free
    preferred_speed: slow
    example: "Design the model routing subsystem"
    good_for: deepseek-v4-flash (free, 1M ctx), local-planner-128k, qwopus (local)

  deep_debugging:
    archetype_family: code_work
    min_context: 16000
    max_context: 128000
    requires_vision: false
    requires_thinking: required
    preferred_code_focus: frontier_coder
    edit_risk: low
    max_cost: openrouter_paid
    preferred_speed: slow
    example: "Investigate why websocket disconnects after 60s idle"
    good_for: deepseek-v4-pro, claude (paid), qwopus (local fallback)

  context_synthesis:
    archetype_family: research
    min_context: 64000
    max_context: 1000000
    requires_vision: false
    requires_thinking: recommended
    preferred_code_focus: any
    edit_risk: none
    max_cost: openrouter_free
    preferred_speed: slow
    example: "Synthesize all docs/architecture/* into a unified design overview"
    good_for: deepseek-v4-flash (1M ctx, free), local-planner-128k (local)

  ui_visual_review:
    archetype_family: review
    min_context: 4000
    max_context: 32000
    requires_vision: true
    requires_thinking: recommended
    preferred_code_focus: any
    edit_risk: none
    max_cost: local_free
    preferred_speed: medium
    example: "Review the new settings panel screenshot for UX issues"
    good_for: gemma4-31b-review, qwopus, qwen3.6 (all have vision)

  code_review:
    archetype_family: review
    min_context: 8000
    max_context: 64000
    requires_vision: false
    requires_thinking: recommended
    preferred_code_focus: code_specialist
    edit_risk: none
    max_cost: local_free
    preferred_speed: medium
    example: "Review the implementation PR for correctness and edge cases"
    good_for: gemma4-31b (thinking, strict), qwen2.5-coder:32b (code specialist),
             deepseek-v4-flash (escalation)

  research_current:
    archetype_family: research
    min_context: 2000
    max_context: 16000
    requires_vision: false
    requires_thinking: optional
    preferred_code_focus: any
    edit_risk: none
    max_cost: openrouter_free
    preferred_speed: fast
    example: "What's the latest Qwen model and its capabilities?"
    good_for: deepseek-v4-flash:free, grok/xai (current cutoff)

  documentation:
    archetype_family: documentation
    min_context: 4000
    max_context: 32000
    requires_vision: false
    requires_thinking: optional
    preferred_code_focus: any
    edit_risk: none
    max_cost: local_free
    preferred_speed: fast
    example: "Write API docstrings for the new endpoint"
    good_for: gemma4 (any), qwopus, local-coder-fast
```

## 3. Routing Decision Tree

The routing engine evaluates candidates in a deterministic priority order. The orchestrator (the Hermes agent running DeepSeek V4) initiates this by calling `devflow task route` after the task is created and classified.

```
┌─────────────────────────────────────────────┐
│ 1. CLASSIFY TASK ARCHETYPE                   │
│    (from task-fit.yaml + orchestrator input)  │
│    → archetype_id + required dimensions      │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 2. BUILD CANDIDATE POOL                      │
│    All registry agents where:                │
│    • model is installed (or provider key set) │
│    • agent is enabled                        │
│    • agent supports the required role        │
│    • agent's max_context ≥ task min_context   │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 3. APPLY MUST-HAVE FILTERS                   │
│    Remove any agent that CANNOT satisfy:     │
│    • vision required → agent.vision == true │
│    • thinking required → agent.thinking == true
│    • code_specialist preferred → keep both   │
│      general and code-specialist, but prefer │
│      code-specialist in ranking              │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 4. CHECK CONTEXT FIT                         │
│    Remove any agent where:                   │
│    • estimated_tokens > agent.reliable_context
│    • rank remaining by: closer fit is better │
│      (too much context headroom = waste)     │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 5. APPLY COST CONSTRAINT                     │
│    If max_cost_class == local_free:          │
│      remove all non-local, non-free agents   │
│    If max_cost_class == openrouter_free:     │
│      keep local_free + openrouter_free       │
│    If max_cost_class == openrouter_paid:     │
│      keep everything except openrouter_expensive
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 6. RANK AND SELECT                           │
│    Score each remaining candidate:           │
│    • +30 if code_focus matches preference    │
│    • +20 if exact context fit (not overkill) │
│    • +15 if speed_class matches preference   │
│    • +10 if local_free vs paid               │
│    • +10 if tuned alias exists for this role │
│    • +5  if scorecard accuracy > 0.7         │
│    • -10 if thinking=required but need to    │
│           use thinking-optional model        │
│                                              │
│    Winner: highest score.                    │
│    Record: selected agent + runner-up + why  │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│ 7. PRODUCE ROUTING DECISION                  │
│    Write routing-decision.yaml with:         │
│    • selected agent per role                 │
│    • rejected candidates + reasons           │
│    • context pack size recommendation        │
│    • next command for execution              │
│    • cap: will_not_escalate flag if          │
│      the best available is weak              │
└─────────────────────────────────────────────┘
```

### 3.1 Pseudocode

```python
def route_task_to_model(task_fit: TaskFitProfile, candidates: list[ModelCapabilityProfile]) -> RoutingDecision:
    archetype = ARCHETYPE_CATALOG[task_fit.archetype_id]
    
    # Step 1: Filter by must-have capabilities
    eligible = []
    for candidate in candidates:
        if archetype.requires_vision and not candidate.vision:
            reject(candidate, "no vision capability")
            continue
        if archetype.requires_thinking and not candidate.thinking:
            reject(candidate, "no thinking capability")
            continue
        if candidate.max_safe_context_tokens < archetype.min_context_tokens:
            reject(candidate, f"context too small: {candidate.max_safe_context_tokens} < {archetype.min_context_tokens}")
            continue
        if candidate.reliable_context_tokens < task_fit.estimated_tokens:
            reject(candidate, f"reliable context {candidate.reliable_context_tokens} < estimated {task_fit.estimated_tokens}")
            continue
        eligible.append(candidate)
    
    if not eligible:
        return RoutingDecision(status="no_eligible_candidate", escalate_to_human=True)
    
    # Step 2: Apply cost constraints
    if archetype.max_cost_class == "local_free":
        eligible = [c for c in eligible if c.cost_class == "local_free"]
    elif archetype.max_cost_class == "openrouter_free":
        eligible = [c for c in eligible if c.cost_class in ("local_free", "openrouter_free")]
    elif archetype.max_cost_class == "openrouter_paid":
        eligible = [c for c in eligible if c.cost_class != "openrouter_expensive"]
    
    if not eligible:
        return RoutingDecision(
            status="cost_blocked",
            escalate_to_human=True,
            message="No eligible candidates within cost constraint",
        )
    
    # Step 3: Score and rank
    scored = []
    for c in eligible:
        score = 0
        
        # Code specialization match
        if archetype.preferred_code_focus == c.code_focus:
            score += 30
        elif (archetype.preferred_code_focus == "code_specialist" 
              and c.code_focus == "general_purpose"):
            score += 10  # acceptable fallback
        
        # Context fit — prefer closest match without waste
        headroom = c.reliable_context_tokens - task_fit.estimated_tokens
        if 0 < headroom < c.reliable_context_tokens * 0.5:
            score += 20  # good fit
        elif headroom < 0:
            score -= 50  # shouldn't happen after filter
        # too much headroom means overkill — slight penalty
        elif headroom > c.reliable_context_tokens * 2:
            score -= 10
        
        # Speed match
        if archetype.preferred_speed == c.speed_class or archetype.preferred_speed == "any":
            score += 15
        elif archetype.preferred_speed == "fast" and c.speed_class == "medium":
            score -= 5
        
        # Prefer free over paid
        if c.cost_class == "local_free":
            score += 25
        elif c.cost_class == "openrouter_free":
            score += 15
        elif c.cost_class == "openrouter_paid":
            score += 5
        
        # Tuned alias bonus — prefer purpose-built over generic
        if task_fit.task_type in c.tuned_for_types:
            score += 10
        
        # Scorecard bonus
        if c.scorecard_accuracy > 0.7:
            score += 5
        
        # Thinking deficit penalty
        if archetype.requires_thinking == "required" and c.thinking == False:
            score -= 50  # effectively disqualifying
        elif archetype.requires_thinking == "recommended" and not c.thinking:
            score -= 10
        
        # Vision deficit penalty
        if archetype.requires_vision and not c.vision:
            score -= 50
        
        # Architecture preference
        if archetype.preferred_architecture == "dense" and c.architecture_class == "moe":
            score -= 5  # dense is more deterministic for coding
        elif archetype.preferred_architecture == "moe" and c.architecture_class == "dense":
            pass  # no penalty
        
        scored.append((score, c))
    
    scored.sort(key=lambda x: -x[0])
    best = scored[0][1]
    runner_up = scored[1][1] if len(scored) > 1 else None
    
    return RoutingDecision(
        status="selected",
        selected_agent=best,
        runner_up=runner_up,
        score=scored[0][0],
        rejected_candidates=scored[1:],
        will_escalate=scored[0][0] < 50,  # low-confidence selection
    )
```

### 3.2 Tuned Alias Priority

A critical routing rule: **tuned aliases are preferred over base model names** when the alias purpose matches the task type. For example, `local-planner-128k` (Qwen 3.6 with num_ctx=131072) should be preferred over bare `qwopus:latest` (same model, default params) for any planning task. Rationale: the alias represents human tuning effort — someone intentionally set that context window for that purpose.

```yaml
alias_routing_rules:
  local-planner-128k:
    preferred_archetypes: [architecture_design, context_synthesis, complex_implementation]
    weight_bonus: +15
  local-planner-64k:
    preferred_archetypes: [complex_implementation, multi_file_refactor]
    weight_bonus: +10
  local-devflow:
    preferred_archetypes: [complex_implementation, simple_implementation]
    weight_bonus: +10
  local-coder-heavy:
    preferred_archetypes: [complex_implementation, multi_file_refactor, deep_debugging]
    weight_bonus: +15
  local-coder-medium:
    preferred_archetypes: [simple_implementation, code_review]
    weight_bonus: +15
  local-coder-fast:
    preferred_archetypes: [trivial_edit, simple_implementation]
    weight_bonus: +15
  local-coder-tiny:
    preferred_archetypes: [trivial_edit, classification]
    weight_bonus: +10
  local-reviewer-deep:
    preferred_archetypes: [code_review, ui_visual_review]
    weight_bonus: +15
  local-reviewer-short:
    preferred_archetypes: [code_review]
    weight_bonus: +10  # 32k ctx — focused but limited
  local-worker-fast:
    preferred_archetypes: [trivial_edit, documentation]
    weight_bonus: +15
  local-worker-balanced:
    preferred_archetypes: [simple_implementation, documentation]
    weight_bonus: +10
```

## 4. Concrete Fleet Routing Recommendations

### 4.1 Local Model Routing Table

What to use for what, based on actual verified manifests:

| Task Archetype | Best Local Pick | Why | Fallback |
|---|---|---|---|
| trivial_edit | `qwen2.5-coder:1.5b` or `local-coder-tiny` | Instant, free, code-specialized, 32k ctx is plenty | `local-worker-fast` (Gemma 4 4.6B) |
| simple_implementation | `qwen2.5-coder:7b` or `local-coder-fast` | Fast, free, code-specialist with `insert` for FIM | `local-coder-medium` (14B) |
| complex_implementation | `local-coder-heavy` (qwen2.5-coder:32b) | Most capable code specialist, 32k ctx, no thinking overhead | `local-devflow` (Qwen 3.6 at 64k ctx) |
| architecture_design (local) | `local-planner-128k` (Qwen 3.6 at 128k ctx) | 128k context window + thinking + vision, purpose-tuned alias | `local-planner-64k` or base `qwopus` |
| multi_file_refactor (local) | `local-coder-heavy` or `local-devflow` | 32-64k ctx, code-specialized, good balance | `qwopus` if more context needed |
| deep_debugging (local) | `qwopus:latest` (no num_ctx override = 262k ctx) | Full context + thinking + vision for maximum local reasoning | `qwen2.5-coder:32b` for pure code bugs |
| code_review (local) | `local-reviewer-deep` (Gemma 4 31B at 262k ctx) | Thinking + large context, best strict reviewer | `gemma4-31b-review` (32k ctx, faster) |
| ui_visual_review | `qwopus:latest` or `gemma4-31b:latest` | Both have vision + thinking + huge context | Any Gemma 4 variant |
| documentation | `local-worker-balanced` (Gemma 4 8B at 131k ctx) | Fast, cheap, good writing quality | `qwopus` |
| context_synthesis (local) | `qwopus:latest` (262k ctx) or `local-planner-128k` | Maximum local context window | `local-devflow` |

### 4.2 Remote (OpenRouter) Escalation Path

Only when local models cannot meet requirements:

| Scenario | Route To | Why | Cost |
|---|---|---|---|
| Exceeds local context (>262k tokens) | DeepSeek V4 Flash (free tier) | 1M context, free | $0 |
| Architecture/planning needs 1M ctx | DeepSeek V4 Flash (paid, ~$0.15/M input) | Cheaper than Pro for planning | Low |
| Hard debugging, local failed | DeepSeek V4 Pro | Best reasoning, 1M ctx | Medium |
| Code review locals disagree | DeepSeek V4 Flash code review | Cheap, good at spotting issues | Low → Free |
| Current research / info cutoffs | Grok/xAI or DeepSeek Flash | Up-to-date knowledge | Low |
| Highest quality code generation | DeepSeek V4 Pro or Qwen3.7 Plus (OpenRouter) | Frontier level | Medium/High |

### 4.3 The Most Common Decision Paths (Quick Reference)

```yaml
day_one_decisions:
  # Most coding tasks → Qwen Coder family, not Qwen 3.6
  "Fix this function":           qwen2.5-coder:7b
  "Implement the feature":       qwen2.5-coder:14b (medium) or qwen2.5-coder:32b (complex)
  "Refactor the subsystem":      local-coder-heavy (32b coder) or local-devflow (Qwen 3.6 64k)
  
  # Planning → planner aliases, not default model
  "Design the architecture":     local-planner-128k (128k ctx) or deepseek-v4-flash (free, 1M ctx)
  
  # Review → Gemma 4 reviewer aliases
  "Review this code":            local-reviewer-deep (Gemma 31B) or local-reviewer-short (fast Gemma 31B 32k)
  "Review this screenshot":      qwopus (vision+thinking) or gemma4-31b (vision+thinking)
  
  # Big context → leverage local 262k before remote
  "Synthesize all the docs":     qwopus (262k local, free) or local-planner-128k (128k local)
  "Need to understand 500k tokens of codebase":  deepseek-v4-flash:free (1M ctx, free)
```

## 5. Context Window Utilization Strategy

With local models running well at 256k context in Hermes, the context tiers shift dramatically:

| Model | Native Ctx | Reliable Ctx | Best Alias Ctx | Use For |
|---|---|---|---|---|
| Qwen 3.6 / Qwopus | 262,144 | ~245,000 (verified) | 128k (local-planner-128k), 64k (local-devflow) | Full codebase awareness, architecture |
| Gemma 4 31B | 262,144 | ~250,000 | 32k (local-reviewer-short) for fast review | Deep review with full context |
| Gemma 4 26B MoE | 262,144 | ~200,000 (MoE degrades earlier) | 262k (gemma4-review) | Review with big context |
| Gemma 4 12B | 262,144 | ~180,000 | Native | Medium-depth analysis |
| Gemma 4 8B | 131,072 | ~100,000 | 131k (local-worker-balanced) | Fast workers, docs |
| Gemma 4 4.6B | 131,072 | ~80,000 | 131k (local-worker-fast) | Simple fast tasks |
| Qwen Coder 32B | 32,768 | 32,768 | 32k (local-coder-heavy) | Code-specific — smaller but more precise |

**Key insight: the current code caps useful_context_tokens at 32k and max_safe_context at 64k for ALL local models.** This is the single most impactful fix — the tier-based ceilings in `router.py:_useful_context_tokens()` are:

```python
# Current — artificially low
"strong_local": 48000,    # → should be 200000+ for Qwen 3.6 and Gemma 31B
"premium_local": 65536,   # → should be 250000+
"local": 32768,           # → should be model-dependent

# Proposed — model-specific, from manifest
qwopus: 245000 (reliable)
gemma4-31b: 250000
gemma4-26b: 200000
gemma4-12b: 180000
qwen2.5-coder:32b: 32000  # honest — code specialist needs less
```

The alias system is the practical way to get different context windows from the same base model:

```
Base model: qwopus:latest (262k native, vision, thinking)

local-devflow:        num_ctx=65536   → "I need a Qwen 3.6 with moderate context 
                                         for balanced implementation"
local-planner-128k:   num_ctx=131072  → "I need a Qwen 3.6 with big context 
                                         for planning"  
qwopus:latest (bare): num_ctx=262144  → "I need max context for full codebase 
                                         synthesis"
```

## 6. Implementation Plan

### Phase 0 — Fix The Profile Data Model *(one session, no new commands)*

**Files changed:** `local_agent_discovery.py`, `router.py`

**Changes:**
1. Add new fields to `ModelCapabilityProfile`: `architecture_class`, `vision`, `thinking`, `code_focus`, `speed_class`, `cost_class`, `fim_support`, `tuned_aliases`, `reliable_context_tokens`
2. Update `classify_local_model()` to populate these from `ollama show` manifest data
3. Remove the hard-coded `_useful_context_tokens()` ceiling function in `router.py` — instead read `reliable_context_tokens` from the profile
4. Add `insert` capability detection (Qwen Coder family) from manifests
5. Add architecture classification (dense vs MoE) from the architecture field

**What this enables:** `devflow agent discover-local --json` immediately starts producing accurate, multi-dimensional profiles. `devflow task route` can start making smarter context-fit decisions.

**Note on reliability:** Getting `ollama show` to work for all models is critical. Currently `discover_local_ollama_models()` calls `ollama show` and falls through on error. For models where manifest is incomplete, derive conservative defaults from model name patterns and architecture hints.

### Phase 1 — Task Archetype Classification *(one session)*

**Files changed:** `estimator.py`, `router.py`, new file: `task_archetypes.py`

**Changes:**
1. Create `task_archetypes.py` with the full archetype catalog as a YAML-loaded or Python dict structure
2. Add archetype classification to `estimate_task_fit()` — derive `archetype_id` from the task description, title, allowed files, and context estimate
3. Store `archetype_id` + `required_dimensions` in `task-fit.yaml`
4. Update `route_task()` to read archetype dimensions and apply the scoring algorithm from section 3.1

**Approved: the estimator infers archetypes deterministically.** No orchestrator tagging needed. The `estimate_task_fit()` function in `estimator.py` grows a deterministic archetype classifier that pattern-matches on task title, description, allowed files, declared scope, and estimated context size. This keeps the routing cycle entirely local and free — no expensive LLM call just to decide which model to use. The archetype classifier is a pure function with no dependencies.

### Phase 2 — Tuned Alias Registry *(one session)*

**Files changed:** `agent_registry.yaml`, `local_agent_discovery.py`

**Changes:**
1. Add `tuned_aliases` metadata to agent registry entries — which archetypes they're preferred for
2. In `rank_local_agent_candidates()`: prefer aliases over base models when the task archetype matches the alias purpose
3. Add alias priority weighting in the candidate scoring function

### Phase 3 — Scorecard Feedback Loop *(one session)*

**Files changed:** `scorecard.py`, `agent_registry.py`, new file: `model_runtime_profiles.py`

**Changes:**
1. After each task completes, write runtime profile data: success/failure, verification pass rate, context headroom used, time taken
2. Feed this back into `reliable_context_tokens` estimates — if a model keeps failing above 150k, lower its reliable ceiling
3. Surface in `devflow agent scorecard` and `devflow agent catalog --json`

### Phase 4 — Orchestrator Integration *(the meta-layer)*

No code change — the orchestrator (Hermes agent with DeepSeek V4) already reads `devflow task route --json` output. The orchestrator uses it as follows:

```
When the orchestrator receives a new task request:

1. devflow task fit <task_id> --json
   → Gets task-fit profile with archetype, context estimate, risk

2. devflow task route <task_id> --json
   → Gets routing decision: selected agent, reason, next command

3. Orchestrator validates:
   - "Does this selection make sense given what I know about the task?"
   - "Is there a tuned alias that would be better?"
   - "Should we escalate to a frontier model?"

4. devflow task run <task_id> --worker <selected-agent>
   → Dispatches to the optimal model
```

The orchestrator is the **safety net** — it can override the deterministic router when the task description reveals requirements the estimator missed (e.g., "this task needs multimodal review" was implied but not explicit in the task definition).

## 7. Concrete Examples

### Example 1: Simple Feature Implementation

```yaml
task:
  title: "Add dark mode toggle to settings panel"
  type: feature_implementation
  
# Estimator produces:
archetype_id: simple_implementation
estimated_context: 12000 tokens
requires_vision: false
requires_thinking: optional
max_cost: local_free

# Route evaluates candidates:
- qwen2.5-coder:7b → score: 95  ← SELECTED
  Why: code_specialist (+30), fits context perfectly (+20), fast (+15), local_free (+25), tuned alias (+15)
- qwen2.5-coder:14b → score: 85  # runner-up, heavier than needed
- qwopus:latest → score: 55       # overkill — too much context, slower
- gemma4-31b:latest → score: 50   # overkill + general purpose, not code specialist

# Result: dispatches to local-coder-fast (Qwen 2.5 Coder 7B alias)
```

### Example 2: Architecture Design

```yaml
task:
  title: "Design the model routing subsystem"
  type: architecture_change

# Estimator produces:
archetype_id: architecture_design
estimated_context: 85000 tokens
requires_vision: false
requires_thinking: required
max_cost: openrouter_free

# Route evaluates candidates:
- deepseek-v4-flash:free → score: 85  ← SELECTED
  Why: 1M context fits easily (+20), thinking=yes, free (+15), 
       architecture_design good_for
- local-planner-128k → score: 75       # runner-up
  Why: 128k fits 85k estimation, thinking=yes, free (+25), alias bonus (+10)
       but speed=slow (-5), no code focus mismatched
- qwopus:latest → score: 65            # 262k ctx works, but slower

# Result: dispatches to deepseek-v4-flash:free for the planning,
# or falls back to local-planner-128k if offline
```

### Example 3: Visual UI Review

```yaml
task:
  title: "Review new settings panel layout"
  type: ui_visual_review

# Estimator produces:
archetype_id: ui_visual_review
estimated_context: 8000 tokens
requires_vision: true
requires_thinking: recommended
max_cost: local_free

# Route evaluates — only vision-capable models:
- qwopus:latest → score: 75  ← SELECTED
  Why: vision (+must-have), thinking=yes, huge context (overkill but accepted),
       local_free (+25). Only vision+thinking local option.
- gemma4-31b → score: 70      # runner-up — also vision+thinking
- qwen2.5-coder:32b → REJECTED  # no vision

# Result: dispatches to qwopus:latest or gemma4-31b for visual review
```

### Example 4: Massive Context Synthesis

```yaml
task:
  title: "Synthesize all architecture docs into unified document"
  type: context_synthesis

# Estimator produces:
archetype_id: context_synthesis
estimated_context: 350000 tokens  # exceeds local max!
requires_vision: false
requires_thinking: recommended
max_cost: openrouter_free

# Route:
- deepseek-v4-flash:free → score: 90  ← SELECTED (only option that fits)
- All local models → REJECTED: reliable context < 350k estimate

# Result: deepseek-v4-flash:free is the ONLY model that can handle 350k tokens.
# This is the killer use case for OpenRouter — tasks that genuinely exceed
# local hardware context limits.
```

## 8. Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Archetype classification is wrong | Orchestrator overrides; task-fit.yaml is editable; classification is evidence-only |
| Profile data becomes stale | `devflow agent discover-local --json` re-reads manifests; scorecard feedback auto-adjusts |
| Cost creep from misrouting to paid models | `max_cost_class` constraint in archetype definition is a hard filter, not a soft score |
| Alias priority causes unexpected behavior | Routing decision is always recorded in `routing-decision.yaml` with reasons; human can inspect and override |
| Models degrade at high context | `reliable_context_tokens` is accountably lower than advertised; scorecard auto-lowers it |
| Too many dimensions make routing hard to debug | Each phase adds one dimension at a time; route output always includes reason chain |

## 9. Success Criteria

The taxonomy is working when:

1. **Trivial edits** route to 1.5B-7B coder models, not 36B general-purpose models
2. **Architecture planning** routes to DeepSeek V4 Flash (free) or local-planner-128k
3. **Visual review** routes to vision-capable models (Qwen 3.6 or Gemma 4)
4. **Large context synthesis** routes to DeepSeek V4 Flash (free) when > 262k tokens
5. **Code review** routes to Gemma 4 reviewer aliases or Qwen Coder, not general-purpose
6. **Cost** stays at $0 for 90%+ of tasks (local or free-tier only)
7. **Scorecard** shows an improving trend: first-pass verification rate goes up as better-matched models are selected
8. **The 40+ model tags** reduce to ~11 meaningful unique models in the user's mental model, with the routing system transparently choosing the right alias