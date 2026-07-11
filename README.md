# DevFlow

DevFlow is a **V2 product-building loop** for turning a rough idea into a
verified implementation:

```text
Idea -> Brainstorm -> Spec -> Plan -> Judge -> Build -> Judge -> Verify -> Next human decision
```

It is intentionally narrow:

- **DevFlow** owns active loop state, evidence, verification, and the next safe action.
- **Hermes** owns brainstorm interaction, tools, messaging, and bounded worker orchestration.
- **Obsidian** owns broad knowledge and long-lived context.
- **Git/filesystem** own the source records.

## Start Here

- [Source of truth](docs/DEVFLOW_SOURCE_OF_TRUTH.md)
- [Agent guide](AGENTS.md)
- [Active documentation index](docs/README.md)

Historical designs are not active context. Do not add old compatibility layers,
prior UI flows, or recovered code to the V2 runtime unless a human explicitly
requests archival recovery.

## Install

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
```

## V2 Commands

```bash
source .venv/bin/activate

# Unified brainstorm and auto-refreshing pipeline status surface.
devflow status serve                       # http://127.0.0.1:8770/

# Deterministic V2 stage-chain regression fixture (no model calls).
devflow loop spine-fixture --json
```

If the console script is unavailable:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli status serve
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

The browser is the unified brainstorm and live-evidence surface. It creates and
continues model-backed brainstorm sessions while reading pipeline-run state from
disk; Hermes remains the bounded worker/orchestration harness.

## Deployment Profiles

DevFlow routes roles through capability-checked model profiles. The default
`legacy-current` profile assumes the Mac Studio local fleet. On this Mac mini,
set the low-resource `mini-free-cloud` profile in the environment of any
model-backed execution process:

```bash
export DEVFLOW_PROFILE=mini-free-cloud
# Required by DevFlow's direct OpenRouter client; supply it securely, never in Git.
export OPENROUTER_API_KEY="..."
```

`mini-free-cloud` routes every V2 text role to the zero-cost OpenRouter HY3
worker, so it does not load a local model. The `cloud-free-fast` profile uses
three ordered OpenRouter `:free` fleets: HY3-led brainstorm/planning, a
Qwen-Coder-led builder lane, and a disjoint Gemma/Nemotron review lane. All
fallbacks remain cloud-only and zero-token-cost, actual routed models are
recorded in usage evidence, and the builder fleet never judges its own work.
Poolside Laguna M.1 is
registered under the exact free slug `poolside/laguna-m.1:free`. The
`mini-laguna-builder` audition profile remains the mixed local/cloud comparison
profile. OpenRouter advertises tool calling and reasoning but not API-enforced
response-format support, so Laguna's structured-output capability here refers
only to its verified DevFlow worker prompt contracts.
Hermes may manage an OpenRouter credential separately, but DevFlow's V2 remote
executor requires that key in its own process environment. `devflow status
serve` observes pipeline evidence and does not call the selected profile.

When local implementation work is desired instead, set
`DEVFLOW_PROFILE=mini-baseline`. It uses the Mac mini's single-flight llama.cpp
fleet for bounded builder/review work and capability-checked Hermes subscription
models for planning, verification, and final judgment. The legacy profile name
`mini-ollama` remains an alias for this assignment; it does not start or use
Ollama.

These profiles contain no credentials. For a different fleet, provide an
external registry/profile with `DEVFLOW_MODELS_YAML` and
`DEVFLOW_PROFILES_YAML`.

## Development Boundary

```text
src/devflow/loop/          # V2 loop contracts, persistence, scout, and model slots
src/devflow/control_room/  # V2 unified brainstorm/status surface
src/devflow/cli.py         # V2 command entrypoint
tests/                     # V2 regression coverage
docs/                      # sparse active authority
```

## Verification

Run the focused V2 checks after changes:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_v2_cli.py \
  tests/test_loop_models.py \
  tests/test_loop_adapter.py \
  tests/test_loop_orient.py \
  tests/test_planning_judge.py \
  tests/test_loop_builder_judge.py \
  tests/test_loop_verification.py \
  tests/test_loop_human_decision.py \
  tests/test_loop_e2e_harness.py \
  tests/test_control_room_git_status.py \
  tests/test_control_room_memory.py \
  -q
```

Before pushing or promoting anything, inspect the diff and require explicit
human approval.

## License

MIT. See [LICENSE](LICENSE).
