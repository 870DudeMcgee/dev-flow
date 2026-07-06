# Codex Efficient Workflow

Status: active first-read workflow for Dev-Flow Codex sessions.

Use this workflow for all Dev-Flow codebase work beyond a tiny one-file answer.
The goal is faster, cheaper, more reliable work: Codex stays the supervisor,
while codebase mapping, large-output compression, local model work, and compact
verification run through purpose-built tools.

This is not permission to launch local workers automatically. Worker starts are
still opt-in. Mapping, compression, fleet telemetry, and compact wrappers are
the default.

## Mental Model

- Map first: find where to look before opening files.
- Compress before reading: never load large files or long command output raw.
- Route before running models: check which model is active and safe.
- Use local lanes for bulk work: keep Codex focused on decisions and review.
- Verify live: local output is evidence, not final proof.

## First Five Minutes

Run these before non-trivial repo work:

```bash
git status --short --branch
~/.hermes/scripts/model-router status
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli local-ai snapshot --json
```

Then choose the map route:

```text
Preferred: Agent Proxy codebase_search("<specific question>")
Fallback: mcp__context_map.build_index(repo="/Users/jewelbait/Desktop/Local AI Dev Team", include_obsidian=false)
Architecture evidence: env PYTHONPATH=src:. .venv/bin/python -m devflow.cli architecture audit --json
Targeted literals/config: rg
```

Current caveat: Agent Proxy may not have Dev-Flow indexed. If it reports a
different project only, say so and use Context Map, Graphify, and targeted `rg`.

## Side Effects

- `mcp__context_map.build_index` writes `.context-map/*.json`.
- `devflow architecture audit --json` refreshes ignored `graphify-out/`.
- `.devflow/` and `graphify-out/` are generated evidence and should normally
  stay uncommitted.
- If the worktree is already dirty, preserve unrelated changes and say what you
  touched.

## Compression Route

Use compression for any file or command output over roughly 50 lines, and for
large generated artifacts. Do not paste huge raw output into Codex.

Default compressor:

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/compress_tool_output.py \
  --input-file <path> \
  --question "<specific extraction question>" \
  --max-output-chars 2000 \
  --write-json .devflow/evidence/compressed-<name>.json
```

Exact method extraction:

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/extract_methods.py \
  --source-file <path> \
  --methods "method_one,method_two" \
  --write-json .devflow/evidence/extracted-methods.json
```

Seam survey for module splits:

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/codebase_survey.py \
  --target-file <path> \
  --write-json .devflow/evidence/codebase-survey.json
```

Qwen3-Coder-Next on port `8084` is the builder lane for context compression,
codebase surveys, and code-producing work. It is non-thinking mode only; do not
expect `<think>` blocks or `reasoning_content` from this route. Ornith 35B on
port `8086` is the scout lane for AST scans, file surveys, and deterministic
codebase inspection.

Ornith 9B is retired from the compression/extraction fallback path. If Ornith
35B is unavailable, use deterministic extraction tools directly where possible
or proceed with frontier-context reading after compressing by other safe means.

## Fleet Routing

Always inspect fleet state before local model work:

```bash
~/.hermes/scripts/model-router status
env PYTHONPATH=src:. .venv/bin/python -m devflow.cli local-ai recommend --json
```

Rules:

- Only one big local model may run at a time.
- Qwen3-Coder-Next on `8084`: builder/coder for code generation,
  refactoring, debugging, codebase surveys, and context compression. It is
  non-thinking mode only.
- Qwen 27B MTP on `8083`: judge for review, validation, final approval, and
  strict-output checks. It runs with thinking mode on.
- Ornith 35B on `8086`: scout for AST scans, file surveys, and deterministic
  codebase inspection. Do not use it as a builder.
- In Codex, visible subagent output is worker evidence:
  `qwen3_coder_next_coder` for builder work, `qwen36_27b_mtp_coder` for
  judge/review work.
- In Hermes/MCP packets, use the routed fleet scripts or profile wrappers
  described in `docs/fleet-routing-brief.md`; prove the route with a real
  completion before trusting the output.
- `/v1/models`, open ports, and configured providers are not readiness proof.
  Use real completions.
- Local model output is evidence. Codex still owns final source review and test
  verification.

Fleet status is informational, not gating. If another big model is resident,
use `~/.hermes/scripts/model-router start <name>` and let the router handle the
swap.

## Mixin Slice Workflow

Use this for extracting methods from `operating_layer_server.py` into handler
mixins.

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/efficiency_gate.py check \
  --task-id <slice-id> --planned-tool-calls 8 --files-to-inspect 5 \
  --will-edit --edit-areas 2 --will-run-tests --needs-builder-judge \
  --user-requested-local-fleet --delegation-planned scout,builder,judge,test-runner \
  --strict --write-json .devflow/evidence/efficiency-gate-<slice-id>.json

python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/scout_wiring_context.py \
  --source-file src/devflow/control_room/operating_layer_server.py \
  --methods "method_one,method_two" --test-dir tests --task-id <slice-id> \
  --write-json .devflow/evidence/scout-<slice-id>.json

bash ~/.hermes/skills/software-development/multi-model-fleet/scripts/builder-judge-loop.sh \
  --skip-baseline \
  "<task description>" \
  "<new mixin file>" \
  "/Users/jewelbait/Desktop/Local AI Dev Team" \
  "src/devflow/control_room/operating_layer_server.py" \
  "method_one,method_two"

python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/wire_mixin.py \
  --scout-json .devflow/evidence/scout-<slice-id>.json \
  --mixin-file <new mixin file> \
  --mixin-class <MixinClass> \
  --server-file src/devflow/control_room/operating_layer_server.py \
  --project-root . \
  --ruff .venv/bin/ruff \
  --write-json .devflow/evidence/wiring-<slice-id>.json
```

Use `wire_mixin.py`; do not manually remove methods, move imports, or edit MRO
unless the script cannot handle the slice and you have a clear reason.

## Non-Mixin Module Split Workflow

Use this for files such as `local_ai_fleet.py`, where the target is module-level
functions rather than class methods.

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/codebase_survey.py \
  --target-file src/devflow/control_room/local_ai_fleet.py \
  --write-json .devflow/evidence/local-ai-fleet-survey.json

python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/compress_tool_output.py \
  --input-file src/devflow/control_room/local_ai_fleet.py \
  --question "Identify cohesive module split groups, imports, callers, and test risks" \
  --max-output-chars 4000 \
  --write-json .devflow/evidence/compress-local-ai-fleet.json
```

Then make small facade-preserving moves. Keep compatibility imports working,
run focused tests after each move, and avoid reopening unrelated UI assets.

`wire_mixin.py` and `scout_wiring_context.py` are for class-method mixin
extraction. Do not use them for module-level splits unless they are explicitly
extended for that shape.

## Compact Verification

Use the wrapper instead of dumping raw pytest or ruff logs:

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/local_test_runner.py \
  --project-root "/Users/jewelbait/Desktop/Local AI Dev Team" \
  --python .venv/bin/python \
  --task-id <task-id> \
  --pytest "<pytest targets>" \
  --ruff "<ruff targets>" \
  --write-json .devflow/evidence/test-results-<task-id>.json
```

Use `fleet_efficiency_report.py` only when you have a real session id and real
local response directory:

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/fleet_efficiency_report.py \
  --session-id <real-session-id> \
  --task-id <task-id> \
  --local-response-dir /tmp/builder-judge \
  --write-json .devflow/evidence/token-efficiency-<task-id>.json
```

Do not use a made-up session id as proof. If session metrics are unavailable,
say that and report the local response evidence separately.

## Documentation And Handoffs

For future slices, write a compact handoff alongside long handoffs. The compact
handoff must be self-contained and executable with only `AGENTS.md` and this
runbook.

Use:

```text
~/.hermes/skills/software-development/local-fleet-efficiency/references/compact-handoff-format.md
```

Keep the compact handoff to roughly 20-30 lines:

- state
- target
- exact methods or function groups
- import and caller risks
- commands
- constraints
- next action

## Failure Handling

- If Agent Proxy is not indexed for Dev-Flow, say so and use Context Map plus
  Graphify.
- If Graphify is stale, refresh only when architecture evidence matters.
- If a big model conflict exists, do not start another big model silently.
- If compression output is empty, inspect `reasoning_content` extraction and
  marker handling before changing model config.
- If local lanes fail, record the failure and proceed with a named bypass only
  when the task is still safe.
- If generated evidence rewrites `.context-map/`, `.devflow/`, or
  `graphify-out/`, keep it separate from source changes unless the task
  explicitly asks to commit those artifacts.

## Fresh-Agent Checklist

Before finalizing, a fresh agent should be able to answer:

- Which map source did I use, and was it fresh?
- Did I compress large source/tool output before reading it?
- Which local model lanes were active?
- Did I avoid starting a second big model?
- Did any local worker actually run, or did I only use telemetry/compression?
- What evidence did local tools produce?
- What did I verify myself against live source/tests?
