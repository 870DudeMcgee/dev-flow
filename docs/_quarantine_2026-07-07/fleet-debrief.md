# Local Fleet Debrief — Comprehensive Intention Brief

This document explains the intent, design, and operating procedures for the local model fleet used in DevFlow work. It is supporting evidence only. The active authority for current session behavior, model residency, lifecycle commands, and closeout is `/Users/jewelbait/.codex/session-operating-contract.md`.

## 1. Purpose and Philosophy

### Why a local fleet exists

The operator runs a Mac Studio with substantial RAM and compute. Running local LLMs eliminates API costs, keeps code private, gives deterministic latency, and allows parallel work without rate limits. The fleet is the operator's owned compute — not a rented service.

### The supervisor-fleet split

The frontier model (you, the agent reading this) is the **supervisor**. It stays lean:
- Plans the work
- Routes tasks to the right tool or model
- Reads compact JSON verdicts, not raw logs
- Verifies evidence
- Makes decisions the local models can't make (product judgment, architecture trade-offs, intent interpretation)
- Handles communication with the human operator

The local fleet does the **bulk work**:
- Code generation
- Code review and judging
- AST scanning and codebase mapping
- Context compression (summarizing large files so the supervisor doesn't read them)
- Test and lint execution (through wrapper scripts)
- Failure diagnosis and classification

The supervisor never reads large files directly, never runs raw pytest/ruff, and never generates verbatim code that a parser could move deterministically. Those are fleet jobs.

### Tool-first principle

Some work is mechanical enough that an LLM is the wrong tool. Moving functions between modules, computing imports, updating facade re-exports, running tests, and classifying common failures are all deterministic operations. We built `extract_module.py` to handle these — it does in one command what a builder-judge loop would do in 8 tool calls and 15K tokens.

**The rule:** if a deterministic tool can do it, use the tool. Use models only when they add value: ambiguous seam analysis, product judgment, new behavior generation, complex failure diagnosis, architecture decisions.

## 2. Fleet Configuration

### Ornith 35B — Primary Builder/Scout (port 8084)

**What it is:**
- Model: Ornith 1.0-35B by DeepReinforce AI
- Architecture: 35B total parameters, ~3B active per token (MoE)
- Base: post-trained on Qwen 3.5
- Released: June 25, 2026
- License: MIT
- Quantization: Q4_K_M
- Context window: 131K (configurable up to 262K)
- Parallel slots: 3 (`-np 3` flag in llama-server)
- Reasoning mode: YES (generates `` blocks before final answer)
- Tool calling: YES (OpenAI-compatible)

**Benchmark performance:**
- SWE-Bench Verified: 75.6
- SWE-Bench Pro: 50.4
- SWE-Bench Multilingual: 69.3
- Terminal-Bench 2.1 (Terminus-2): 64.2
- NL2Repo: 34.6
- ClawEval Avg: 69.8

**Why it was chosen as the primary builder:**
It outperforms every comparable-size open model on agentic coding benchmarks. The self-scaffolding RL training means it learned to construct its own task plans, launch tools, inspect intermediate results, and rewrite failing steps — not just generate code. It has reasoning mode for complex problems. The 3B active parameter count means fast inference despite 35B total. And it runs 3 parallel slots, so you can dispatch 3 concurrent jobs without swapping.

**What it's used for:**
- Code generation (primary builder in builder-judge loops)
- Codebase surveys and seam analysis (`codebase_survey.py`)
- Context compression (`compress_tool_output.py`)
- Method body extraction (`extract_methods.py`)
- AST scanning and file inspection (scout work)
- Refactoring and debugging
- Any LLM-dependent work where reasoning helps

**How to call it:**
Ornith is the default resident heavy lane when active local-worker work is expected. Use the explicit model-router boundary: `~/.hermes/scripts/model-router start local-ornith-35b`. Fleet scripts (compress, survey, extract) target port 8084. For builder-judge loops, `builder-judge-loop.sh` targets port 8084 for build/scout phases. For subagent delegation, use `delegate_task` only after the lane is known resident or explicitly started; children inherit the configured delegation lane.

**Reasoning mode notes:**
Ornith generates a `` block before its final answer. Fleet scripts that need clean output use a `## ANSWER:` marker prompt — the model is instructed to write its final answer after the marker, and the script extracts text after the marker from either `content` or `reasoning_content`. For verbatim code extraction, prefer `extract_methods.py` which produces more reliable output. The reasoning content can burn all `max_tokens` — always set `max_tokens=2048+` for this model.

### Qwen 27B Q5 MTP — Judge (port 8083)

**What it is:**
- Model: Qwen 27B Q5 MTP
- Architecture: 27B dense (not MoE)
- Quantization: Q5_K_M
- Context window: 131K
- MTP (Multi-Token Prediction) draft mode for faster inference
- Reasoning mode: YES (thinking mode for deep review)
- Parallel slots: 1 (MTP uses the draft head, can't parallelize)

**Why it's the judge:**
It's a **dense** model — not MoE. Every token activates all 27B parameters, giving higher per-token quality than an MoE model that only activates 3B. It's from a **different model family** than Ornith (Qwen vs DeepReinforce's post-trained Qwen variant) — different training means different blind spots, so it catches errors Ornith would miss. It supports **thinking mode** — it can reason through complex code review step-by-step before rendering judgment. It's slower than Ornith, but judging is not parallelized — precision matters more than speed.

**What it's used for:**
- Code review and validation (judge in builder-judge loops)
- Final approval gate before promotion
- Complex semantic review where extended thinking helps
- Architecture and design judgment (different perspective from the builder)

**How to call it:**
Qwen is a temporary judge/review lane, not the default resident worker. Use the explicit model-router boundary: `~/.hermes/scripts/model-router start local-llama-mtp`. After the judge/review phase, explicitly swap back to `local-ornith-35b` when more local-worker work is expected, or stop `heavy` when no local model work remains. Don't try to run Qwen and Ornith simultaneously — they're both heavy-group models.

### The swap rule

**One heavy model process runs at a time.** The model-router enforces this — starting one heavy model stops any other heavy model first. This is a resource constraint: both models need substantial RAM, and running both would cause swapping and degraded performance.

This does NOT mean one job at a time. Ornith 35B runs with `-np 3` (3 parallel slots), meaning a single Ornith process can handle 3 concurrent requests. You can dispatch 3 builder/scout jobs to Ornith simultaneously without any swap. Only swap to Qwen 27B when you need the judge — and only one swap at a time.

### Fleet status is informational

`~/.hermes/scripts/model-router status` shows which models are currently running. A model showing "down" means the process isn't resident — it does NOT mean the lane is unavailable. The router can start it on demand. Do not:
- Block work because a model shows "down"
- Declare a "lane outage" because a process isn't running
- Stop and ask the user to start a model manually

Just request the lane with the provider-key command (`model-router start local-ornith-35b` or `model-router start local-llama-mtp`) and let the router handle stop-before-start. Keep `local_runners.auto_start: false` for the Desktop/supervisor workflow; do not hide heavy model start/stop inside a normal Hermes chat-completion request. Only treat a lane as blocked if the router cannot start the model or a healthcheck fails after start.

## 3. Scout Work

Scouting is the **orientation and inspection** phase of the workflow. It happens before any code changes, before any builder-judge loop, before any patch. The scout's job is to produce structured evidence about the codebase so the supervisor can make routing decisions without reading raw files.

### What scouting means

Scouting answers questions like:
- Where is function X defined?
- What calls function Y?
- How does subsystem Z work?
- What are the imports, class structure, and method signatures in this file?
- What are the monkeypatch targets in test files?
- What functions should be grouped together for module extraction?
- What are the refactoring seams in this god module?

### Scout tools (all deterministic, no LLM needed)

| Tool | What it does | When to use |
|---|---|---|
| `mcp_context_map_orient` | Returns source-backed orientation for a task, file, or symbol. Combines task-level orientation with symbol tracing — includes imports, imported-by, related tests, related docs. | First step for any task — understand where target files fit |
| `mcp_agent_proxy_codebase_search` | Multi-step code intelligence queries (symbol search, call tracing, code snippets) against a persistent knowledge graph. | When DevFlow is indexed and you need call-site/callee relationships |
| `scout_wiring_context.py` | Deterministic AST scan of a source file: movable imports, shared imports, monkeypatch targets, method line ranges, MRO, server line count. | Class method extraction (Mode A) — before builder-judge loop |
| `codebase_survey.py` | AST + LLM survey of files/dirs for refactoring seams. Reports function groups, import dependencies, and proposed module splits. | When deciding how to split a god module; uses Ornith 35B for seam analysis |
| `extract_methods.py` | Extracts exact method bodies from source via LLM. Returns verbatim source code for specific functions. | When builder-judge needs the exact source of functions being moved or reviewed |

### Scout workflow

1. **Context map orient** on the target file or symbol — this gives you imports, callers, related tests, related docs. No file reading needed.
2. **If extracting class methods** (Mode A): run `scout_wiring_context.py` to get AST-level details (imports, monkeypatch targets, line ranges, MRO).
3. **If extracting module functions** (Mode B): run `codebase_survey.py` to get seam analysis and proposed groupings.
4. **If exact source is needed** for a builder prompt: run `extract_methods.py` to get verbatim function bodies.
5. **Read the JSON verdicts** — never read the raw source files into frontier context if they're > 50 lines.

### Scout output is structured evidence

All scout tools return JSON. The supervisor reads the JSON, not the source files. The JSON contains:
- File paths and line numbers
- Import relationships (movable vs shared)
- Monkeypatch targets (so you know what to preserve)
- Method/function line ranges (so the extractor knows what to move)
- Proposed groupings (so the supervisor can approve or adjust the manifest)

### When scouting needs Ornith 35B

`codebase_survey.py` and `extract_methods.py` send prompts to Ornith 35B (:8084). This is scout work, not builder work — the model is being used for comprehension, not generation. The survey prompt asks for structural analysis (function groups, import dependencies, proposed splits). The extract prompt asks for verbatim source code of specific functions.

These are the LLM-dependent scout tools. The deterministic scout tools (`scout_wiring_context.py`, `mcp_context_map_orient`, `mcp_agent_proxy_codebase_search`) need no model at all.

## 4. Tool Routing

### Two extraction modes

**Mode A: Class Method → Mixin Extraction** (Slices 3-11)
For extracting class methods from a god class into mixin modules. Uses the 6-step workflow: gate → scout → builder-judge → wire → test → receipt.

Tools: `scout_wiring_context.py`, `builder-judge-loop.sh`, `wire_mixin.py`, `local_test_runner.py`, `fleet_efficiency_report.py`

**Mode B: Module Function → Focused Module Extraction** (Slice 12+)
For extracting top-level functions from a god module into focused modules with a facade re-export pattern. Uses one deterministic tool: `extract_module.py`. No builder-judge loop needed.

Tool: `extract_module.py` (handles AST parsing, import computation, constant detection, helper reference rewriting, monkeypatch preservation, facade patching, ruff auto-fix, and test/lint verification — all in one command)

**When to use which:** If functions are being moved verbatim from one module to another with a compatibility facade, use Mode B (deterministic). If class methods are being extracted into mixins with MRO wiring, use Mode A (builder-judge). If new code is being written or behavior is changing, use the builder-judge loop directly.

### Full tool reference

| Tool | Purpose | LLM? | Mode |
|---|---|---|---|
| `extract_module.py` | Deterministic module-level function extraction with facade re-exports | No | B |
| `scout_wiring_context.py` | AST scan: imports, monkeypatch targets, method ranges, MRO | No | A |
| `wire_mixin.py` | Automated mixin wiring from scout JSON | No | A |
| `local_test_runner.py` | Test/lint summary wrapper — never use raw pytest/ruff | No | Both |
| `efficiency_gate.py` | Preflight gate + budget check | No | A |
| `fleet_efficiency_report.py` | Token metrics with subagent + delta mode | No | A |
| `codebase_survey.py` | File/directory survey for refactoring seams | Yes (Ornith 35B) | Both |
| `compress_tool_output.py` | Context compression via LLM | Yes (Ornith 35B) | Both |
| `extract_methods.py` | Extract exact method bodies from source | Yes (Ornith 35B) | Both |
| `builder-judge-loop.sh` | Builder generates, judge reviews, iterate | Yes (Ornith 35B + Qwen 27B swap) | A |

All scripts live in `~/.hermes/skills/software-development/local-fleet-efficiency/scripts/`.

## 5. The Workflow (always follow this)

### Step 1: Follow the session contract

Current session behavior is defined by
`/Users/jewelbait/.codex/session-operating-contract.md`.

### Step 2: Scout before edits

Scout first. The scout owns mapping, source search, file reads, compression, and freshness checks. The frontier reads compact scout evidence, not broad raw source context.

The scout should use `mcp_context_map_orient` on the target file, symbol, or task question. This returns imports, callers, related tests, and related docs — all source-backed, no file reading. If DevFlow is indexed in the codebase knowledge graph, the scout may also use `mcp_agent_proxy_codebase_search` for call-site/callee tracing.

Never skip scout orientation. Even for "simple" tasks, scout evidence tells you what else touches the files you're about to change without bloating frontier context.

### Step 3: Compress

Never read files > 50 lines directly in frontier context. Use:
- `compress_tool_output.py` — LLM summarizes the file (defaults to Ornith 35B)
- `extract_methods.py` — LLM extracts exact method bodies
- `codebase_survey.py` — LLM surveys for seams and groupings

The supervisor reads JSON verdicts from these tools, not raw source.

### Step 4: Check fleet

`~/.hermes/scripts/model-router status` — informational only. Shows what's running. Don't block on "down" status. If a script needs a model, the model-router starts it.

### Step 4: Route

Pick the right tool from the table in section 4. The routing decision is:
- Moving existing code verbatim? → `extract_module.py` (deterministic, no LLM)
- Extracting class methods into mixins? → Mode A 6-step workflow
- Writing new code? → `builder-judge-loop.sh` (Ornith 35B builds, Qwen 27B judges)
- Need to understand the codebase? → `codebase_survey.py` or scout tools
- Need to verify? → `local_test_runner.py` (always, never raw pytest/ruff)

### Step 5: Verify

Always use `local_test_runner.py`:
```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/local_test_runner.py \
  --pytest "tests/test_file.py" \
  --ruff "src/path/to/file.py" \
  --project-root . --python .venv/bin/python --task-id <task> \
  --write-json .devflow/evidence/test-results-<task>.json
```

Never run raw `pytest` or `ruff` directly. The wrapper returns compact JSON with pass/fail counts, top failures, and verdict. If tests fail, read the JSON — don't read raw pytest output.

## 6. Documentation Discipline

Follow `/Users/jewelbait/.codex/session-operating-contract.md` for
documentation discipline. Do not create new handoff, plan, spec, or checklist
files by default. Update existing authority surfaces first, and create a new
handoff only when the human explicitly asks for one.

## 7. Failure Modes to Avoid

### Treating "down" status as a lane outage

An agent saw Qwen 27B showing "down" in model-router status and stopped work, reporting a "lane outage." "Down" means the process isn't resident — the router starts it when needed. Don't block on fleet status. Request the lane and let the router handle it.

### Skipping orientation because the task seems simple

An agent skipped orientation, mapping, compression, fleet check, and verification because a task looked small. It wrote code that worked but ignored the evidence workflow. Tiny tasks still start with orientation; handoffs do not need to restate the rule.

### Using rm with globs that match source files

An agent ran `rm -f src/devflow/.../local_ai_*.py` to clean up extracted modules. The glob matched `local_ai_fleet.py` and `local_ai_command.py` too, deleting the source file. Always list explicit filenames in rm commands. Never use a glob pattern that could match the file you're working on.

### Modifying source files during model installation

An agent installed a new model and modified `local_ai_fleet.py`, `local_model_server.py`, `local_model_readiness.py`, and `hermes_profile_resolver.py` to wire it in. Model installation should only touch Hermes config (`~/.hermes/config.yaml`), lifecycle scripts, Hermes profiles, Codex configs, and DevFlow registry/manifest files (`.devflow/providers/`, `.devflow/agents/`, `data/local_model_expected_profiles.yaml`). Source code files are not config.

## 8. Key Files

| File | Purpose |
|---|---|
| `AGENTS.md` | First-read instruction surface — fleet table, workflow, handoff format standard |
| `docs/fleet-routing-brief.md` | Full routing rules and constraints for agent sessions |
| `docs/fleet-debrief.md` | This document — comprehensive intention brief |
| `~/.hermes/skills/software-development/local-fleet-efficiency/SKILL.md` | Full skill: two extraction modes, all scripts, pitfalls, packet templates |
| `~/.hermes/scripts/model-router` | Fleet lifecycle manager — status, start, stop |
| `~/.hermes/config.yaml` | Hermes config with provider definitions and local_runners |

## 9. Summary

Ornith 35B builds and scouts. Qwen 27B judges. The router swaps. Fleet status is informational. Orient first, scout before edits, compress, route, verify. Use `local_test_runner.py`. Use `extract_module.py` for verbatim function extraction. Use the builder-judge loop for new code. Follow AGENTS.md. Don't let handoffs override the workflow. Research models before suggesting fleet changes. Don't modify source files during model installation.
