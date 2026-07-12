# Mini Local-Model Tuning — Fresh Session Handoff

## What this is

This document is a complete operational handoff for continuing local LLM
tuning on a Mac Mini M1 (16 GB unified memory). It supersedes the original
handoff packet because a baseline has now been established, a lifecycle
wrapper and benchmark harness exist, and the next phase is candidate
auditioning and role assignment.

A prior session (20+ hours of tuning experience on a Mac Studio M4 Max/64GB)
produced the operational principles below. Those principles have been adapted
to and proven on the Mini.

---

## Machine: Mac Mini M1, 16 GB

- Macmini9,1, Apple M1, 8 cores (4P + 4E)
- macOS 26.5.1
- 52 GB free storage (at time of measurement)
- **Memory note:** Measurements in this packet were taken while multiple
  agents were actively building and processing on the same machine. The
  machine will likely have several GB more free memory when truly idle. Treat
  all memory numbers as a busy-system stress baseline, not an idle-use
  ceiling.

---

## Installed runtimes (verified)

| Runtime | Version | Notes |
|---|---|---|
| llama.cpp / llama-server | build 9810 | `/opt/homebrew/bin/llama-server` |
| Ollama | 0.30.10 (app) / 0.24.0 (brew formula) | Version skew risk; app version is authoritative |
| Hermes Agent | 0.18.2 | Python 3.11.15 |

---

## What has already been built

### Lifecycle wrapper: `~/.hermes/scripts/model-router`

Operations: `start`, `stop`, `restart`, `status`, `health`, `logs` — all on
port 8088.

Enforces:
- Exact model path and alias (configurable via `MINI_QWEN_MODEL_PATH` and
  `MINI_MODEL_ALIAS` env vars; defaults to
  `~/models/qwythos-9b-v2-q4_k_m.gguf` / `qwythos-9b-v2-mini`)
- `127.0.0.1` only binding
- One parallel slot
- Metal GPU offload (99 layers)
- Flash Attention `auto`
- Configurable context (`MINI_MODEL_CONTEXT`, default 8192)
- 512 MiB prompt-cache cap (`MINI_MODEL_CACHE_RAM_MIB`, default 512)
- **Model swapping**: if a different model is already running on the port,
  detects it via `/v1/models` alias check, stops it, and starts the requested
  model. This is driven by DevFlow's `ensure_lane()` which passes the model
  path and alias from the registry entry.
- No automatic startup; no provider fallback

### Lane lifecycle: `src/devflow/loop/execution.py::ensure_lane`

When a role resolves to a local llama.cpp model, `ensure_lane` passes the
model's `model_path` and `model_id` from the registry entry to model-router
via env vars. This enables automatic model swapping when different roles need
different models on the same port.

### Benchmark harness: `scripts/mini_model_benchmark.py`

Run with:
```bash
env -u PYTHONPATH .venv/bin/python scripts/mini_model_benchmark.py --idle-seconds 300
```

The `env -u PYTHONPATH` prefix is **mandatory** — the DevFlow project venv
is Python 3.14 but Hermes leaks a Python 3.11 PYTHONPATH that breaks
pydantic_core import.

Tests (3 repetitions each):
1. `/health` and `/v1/models`
2. Tiny exact completion
3. 1-2K token repository summarization
4. JSON-only structured output
5. Actual DevFlow `LocalModelClient` (`/v1/chat/completions`)
6. 5-minute idle then repeat completion

Evidence is written incrementally to
`.devflow/evidence/local-model-benchmarks/<timestamp>/raw-results.json`.

---

## Proven baseline: Qwen3.5 9B UD-Q4_K_XL

| Setting | Value |
|---|---|
| Model file | `~/.cache/huggingface/hub/models--unsloth--Qwen3.5-9B-MTP-GGUF/snapshots/9716a636ee4bddc3fed678220b7a33dd2a4160ae/Qwen3.5-9B-UD-Q4_K_XL.gguf` |
| Size | 6,135,034,208 bytes (5.71 GiB) |
| Parameters | 9.2B |
| Endpoint | `http://127.0.0.1:8088` |
| Context | 8,192 |
| Parallel | 1 |
| Prompt-cache cap | 512 MiB |
| Flash Attention | auto |
| Vision projector | **Not loaded** |

### Benchmark results (8K / 512 MiB cache)

All tests passed 3/3. No errors, disconnects, malformed output, or server
exits.

| Test | In/Out tokens | Avg elapsed | Prompt tok/s | Gen tok/s |
|---|---:|---:|---:|---:|
| Exact tiny completion | 40 / 6 | 1.29s | 39.73 | 9.70 |
| Repository summary (2.2K input) | 2165 / 565 | 90.85s | 97.88 | 8.21 |
| JSON-only structured | 85 / 22 | 3.39s | 70.38 | 8.96 |
| DevFlow `LocalModelClient` | 30 / 5 | 1.12s | — | — |
| Post-5-min-idle completion | 23 / 9 | 1.32s | — | 9.64 |

### Key operational findings

1. **`chat_template_kwargs.enable_thinking = false` is mandatory** for
   Qwen3.5 on bounded tasks. Without it, `/v1/responses` emits ~200 reasoning
   tokens to answer "reply with exactly X" (28s vs 1s). DevFlow's
   `LocalModelClient` already sets this correctly.

2. **llama.cpp's default `--cache-ram` is 8 GiB** — excessive on a 16 GB
   machine. The cap was reduced to 512 MiB with zero performance regression.
   Without the cap, prompt cache grew to ~1.76 GB during the first run.

3. **16K context is stable** but showed no quality benefit for current
   packet sizes (~2.2K tokens). Keep 8K as default; use 16K only for packets
   that demonstrably need it.

4. **`/v1/responses` works** on llama.cpp build 9810 but requires the same
   `enable_thinking: false` override to be practical.

---

## Existing model inventory

### Active fleet: `~/models/` (llama.cpp only, Ollama decommissioned)

| Model file | Params | Quant | Size | Role |
|---|---:|---|---:|---|
| `qwythos-9b-v2-q4_k_m.gguf` | 8.95B | Q4_K_M | 5.3 GiB | Unqualified audition candidate |
| `ornith-9b-q4_k_m.gguf` | 8.95B | Q4_K_M | 5.2 GB | Build judge/review |
| `qwen2.5-coder-7b-q4_k_m.gguf` | 7.6B | Q4_K_M | 4.4 GB | Builder |

All three share endpoint `127.0.0.1:8088` via single-flight locking. The
model-router swaps models on demand when `ensure_lane` passes the correct
path and alias.

### Pruned (deleted this session)

Qwen3.5-9B UD-Q4_K_XL + mmproj, Qwen2.5-coder 1.5B/14B, Qwen3 14B, Gemma4
12B. Total freed: ~31 GB. Ollama daemon killed, all blobs/manifests deleted.

---

## Benchmark results summary

All five candidates passed all 7 tests 3/3. See
`.devflow/evidence/local-model-benchmarks/candidate-comparison-matrix.csv`
for the full comparison data.

| Model | Gen t/s (tiny) | Gen t/s (repo) | Prompt t/s (repo) | Repo time | Size | Result |
|---|---:|---:|---:|---:|---:|---|
| Qwen2.5 Coder 7B | **14.26** | **12.42** | 46.22 | **26s** | 4.4 GB | **Builder** |
| Qwythos-9B v1 (historical; retired) | 10.35 | 10.22 | 108.46 | 85s | 5.5 GB | Unsafe judge results; no longer installed |
| Ornith-9B | 11.09 | 10.16 | **109.90** | 80s | 5.2 GB | **Build judge** |
| Qwen3.5-9B (baseline) | 9.70 | 8.21 | 97.88 | 91s | 6.1 GB | Pruned (dominated) |
| Gemma4-12B | 8.53 | 7.71 | 28.01 | 64s | 6.5 GB | Pruned (dominated) |

---

## DevFlow routing state

### What is fixed (this session)

1. **`mini-baseline` profile created** in `profiles.yaml` — maps:
   - builder → `qwen2.5-coder-7b-mini` (local, port 8088)
   - build_judge → `ornith-9b-mini` (local, port 8088)
   - planner → `gpt-5.6-terra` (subscription)
   - planning_judge, verifier → `gpt-5.6-luna` (subscription)
   - final_judge, brainstorm → `glm-5.2` (subscription)

2. **Three Mini models registered** in `models.yaml` with `model_path`
   pointing to `~/models/*.gguf`. The `model_path` field is now a first-class
   field on `ModelEntry` and `ResolvedSlot`, threaded through the YAML loader
   to `ensure_lane()`.

3. **Studio models marked `available: false`** — they're no longer eligible
   for routing on the Mini but retained for cross-machine use.

4. **`ensure_lane()` fixed** — now uses `_is_local_endpoint()` instead of a
   string check for "localhost" (which missed `127.0.0.1`). It passes
   `MINI_QWEN_MODEL_PATH` and `MINI_MODEL_ALIAS` env vars to model-router,
   enabling automatic model swapping.

5. **model-router supports model swapping** — when a different model is
   already running on the port, it detects the mismatch via `/v1/models`,
   stops the old server, and starts the new one. No more "port in use" errors
   when switching roles.

6. **`mini-ollama` profile updated** — now routes builder to
   `qwen2.5-coder-7b-mini` instead of the deleted `qwen2.5-coder-14b`. Kept
   as backward-compat alias.

### What may still need attention

1. **Silent fallback in `routing.py`**: when a profile's preferred model is
   stale/unavailable, routing silently falls through to auto-cost-routing.
   This is designed behavior but worth knowing.

2. **Silent cloud fallback in `HermesSubscriptionClient`**: catches any
   exception and retries on `openai-codex/gpt-5.5` without logging.

3. **Registry `available: true`** means "configured", not "live and
   reachable." No health probe is performed before routing.

4. **Ollama auto-launch**: the daemon was killed and bootout attempted (SIP
   blocked full removal). If the app is re-opened manually or via "Open at
   Login", it will start again.

---

## Tuning workflow for each new candidate

### Step 1: Download (one model at a time)

```bash
# Verify storage first
df -h /

# Download to HF cache
huggingface-cli download <repo> <filename>.gguf
```

### Step 2: Configure model-router

Either modify the existing `~/.hermes/scripts/model-router` to accept the
new model path via env var, or create a candidate-specific wrapper. The
existing script supports `MINI_QWEN_MODEL_PATH` env override.

### Step 3: Start and verify

```bash
MINI_QWEN_MODEL_PATH=<new_model_path> \
  ~/.hermes/scripts/model-router start 8088

~/.hermes/scripts/model-router status 8088
curl -fsS http://127.0.0.1:8088/v1/models
```

### Step 4: Run benchmark harness

```bash
cd /Users/josh/Desktop/Dev-Flow
env -u PYTHONPATH .venv/bin/python scripts/mini_model_benchmark.py \
  --idle-seconds 300 \
  --model <alias>
```

### Step 5: Score by role

Use the same test matrix across all candidates. Score separately:
- Exact instruction following
- JSON format compliance
- Repository comprehension quality
- Unified-diff correctness (if builder role)
- Critique/review quality (if judge role)
- Speed (prompt tok/s, generation tok/s)
- Memory pressure and swap delta
- Idle survival

### Step 6: Record in comparison ledger

Add results to:
`.devflow/evidence/local-model-benchmarks/qwen3.5-9b-benchmark-matrix.csv`

Create a new matrix CSV per candidate for clean comparison.

---

## Keep / Change / Reject decisions so far

| Item | Decision |
|---|---|
| Qwen3.5 9B UD-Q4_K_XL | **KEEP** — proven baseline |
| llama.cpp build 9810 | **KEEP** |
| 8K context | **KEEP as default** |
| 16K context | **KEEP as optional on-demand mode** |
| One slot / single-flight | **KEEP** |
| 512 MiB prompt-cache cap | **KEEP** |
| Default 8 GiB prompt cache | **REJECT** |
| Thinking enabled for bounded tasks | **REJECT** |
| `/v1/responses` without template override | **REJECT** |
| Vision projector loaded | **REJECT for baseline** |
| Qwen2.5 Coder 7B | **TEST NEXT** |
| Qwythos-9B v2 Q4_K_M trunk-only | **QUALIFY NEXT; audition-only** |
| Ornith 9B | **HIGH-PRIORITY FUTURE** |
| Qwen2.5 Coder 14B | **DEFER** — experiment only |
| Qwen3 14B | **DEFER** |
| Gemma4 12B | **DEFER** |
| Qwythos-9B v1 | **REMOVED** — retired after unsafe false-positive judge results |

---

## Architecture: what worked on the Studio (adapt for Mini)

1. **One heavy model resident at a time.** Explicitly started, stopped, and
   swapped. Auto-start disabled.

2. **Clear roles beat one "do everything" model.**
   - Planner/research: converts rough intent into compact task packets.
   - Scout/build/compression: bounded file surveys, extraction, scoped edits.
   - Judge: validation and critique after there is an actual packet.
   - Frontier agent remains supervisor.

3. **Bounded packets and single-flight work.** Small, anchored jobs: exact
   files, exact question, expected output shape, verification command.

4. **Explicit launchers and local-only health checks.** Each model has its
   own lifecycle script.

5. **Verify the real request path.** Test the exact API the client uses.
   For DevFlow that is `/v1/chat/completions` via `LocalModelClient`.

6. **Preserve explicit provider selection.** Disable keyword-routing
   overrides and cloud fallback during testing.

---

## What did not work (lessons from Studio + Mini)

- "Router ready" did not prove the model could complete the workload.
- A model could accept a request yet emit reasoning/fake tool-call text
  rather than the required structured output.
- Large context is not automatically useful. 16K showed no quality benefit
  over 8K for current ~2.2K-token packets.
- Broad codebase questions are low-quality and fragile. Deterministic
  search tools plus compact packets are more reliable.
- Do not run multiple heavyweight models simultaneously on 16 GB.
- Do not retry an unstable server repeatedly. Capture logs, stop, reduce
  load, retest.
- The default llama.cpp prompt-cache (8 GiB) is a silent memory hog on
  16 GB machines.

---

## Resolved risks (as of this session)

1. Qwythos-9B v1's earlier 7/7 micro-benchmark result is historical and did not
   survive role-specific ground-truth evaluation. It was retired after falsely
   passing all nine known-bad build-judge trials. Qwythos v2 is installed as a
   distinct audition-only candidate with no inherited role credit.
2. ~~Ornith 9B needs to be identified and sourced~~ — **Sourced from
   `deepreinforce-ai/Ornith-1.0-9B-GGUF`, tested, and assigned build_judge
   role.** All 7 tests passed 3/3.
3. ~~Ollama version skew~~ — **Ollama decommissioned.** Daemon killed, blobs
   deleted, all models consolidated to `~/models/`.
4. ~~Ollama login startup and auto-load conflict~~ — **Resolved.** Ollama is
   no longer running.
5. ~~DevFlow routing still points at unreachable Studio endpoints~~ — **Fixed.**
   `mini-baseline` profile created and wired.
6. Registry "available" means configured, not live — **Still true by design.**
   No health probe before routing.
7. ~~DevFlow can silently reroute after stale profile choices~~ — **Still by
   design** but routing now has correct Mini models available.
8. ~~Subscription execution silently falls back to another cloud provider~~ —
   **Fixed.** Fallback now uses `gpt-5.6-luna` (not deprecated `gpt-5.5`) and
   logs a visible warning to stderr before falling back.
9. ~~Memory measurements were taken under heavy concurrent load~~ — **Re-verified
   during benchmarks.** Stable with no swap growth.
10. ~~Storage is at 52 GB free — be conservative with downloads~~ — **Now 70 GB
    free** after pruning 6 models.

---

## Next actions

1. **Run the real DevFlow loop** through the `mini-baseline` profile against
   an actual task packet. `spine-fixture` is deterministic (no model calls);
   a real loop exercise is the next proof point.
2. **Content capture** — ContentFlow integration to capture decisions and
   progress from DevFlow sessions.
3. **Workspace selection** — DevFlow should operate in a user-selected
   workspace directory. The repo picker serves as a file system explorer for
   picking the working folder, with options for adding and renaming folders.
