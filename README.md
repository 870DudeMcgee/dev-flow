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

Read in this authority order:

1. **[DevFlow Software Factory — Vision, Architecture & Blueprint](docs/DevFlow_Software_Factory_Vision_Architecture_Blueprint.docx)**
   — the immutable, highest product/architecture/direction authority for DevFlow
   and its Obsidian integration. Read it first for any product-direction,
   architecture, workflow-runtime, worker-contract, human-authority, or
   DevFlow–Obsidian question. It describes the north-star direction, not
   necessarily what is implemented in the current checkout.
2. [Agent guide](AGENTS.md) — operational rules and current constraints
   (subordinate to the blueprint on product direction).
3. [Current-implementation reference](docs/DEVFLOW_SOURCE_OF_TRUTH.md) — what is
   actually implemented today (routing, gaps); subordinate to the blueprint.
4. [Active documentation index](docs/README.md)

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

DevFlow is model-agnostic and machine-agnostic. Profiles are preferred
role-to-model assignments for an environment; they are not fixed architectures.
The operator may use machine-local models, OpenRouter `:free` models,
Hermes-subscription models, or any qualified mixture through a profile or
per-run override.

The current profile catalog is defined only by
[`src/devflow/loop/profiles.yaml`](src/devflow/loop/profiles.yaml). The current
model registry is defined by
[`src/devflow/loop/models.yaml`](src/devflow/loop/models.yaml), or by the
host-specific files named in `DEVFLOW_PROFILES_YAML` and
`DEVFLOW_MODELS_YAML`. See
[Model Routing & Operating Modes](docs/DEVFLOW_SOURCE_OF_TRUTH.md#model-routing--operating-modes)
and
[Machine Agnosticism And Capability Discovery](docs/DEVFLOW_SOURCE_OF_TRUTH.md#machine-agnosticism-and-capability-discovery)
for the authoritative contract and current implementation gaps.

Important current facts:

- `legacy-current` and `studio-local-heavy` describe M4 Studio **mixed** routes;
  neither is a fully offline profile because each uses GLM-5.2 for some roles.
- `mini-baseline` describes the M1 Mini's smaller single-flight local fleet plus
  subscription reasoning; the Mini does not inherit the Studio's local models.
- `mini-free-cloud`, `cloud-free-fast`, and `hy3-swap` are zero-incremental-cost
  cloud modes and require an OpenRouter credential in the DevFlow process.
- The checked-in registry is currently Mini-oriented: Studio model entries are
  present but marked unavailable. An M4 route needs the matching host registry
  or availability configuration; selecting an M4 profile alone is insufficient.
- Runtime endpoint discovery (`/health`, `/v1/models`) identifies the resident
  model, while local auditions establish role fitness. These are separate from
  host-resource discovery and profile recommendation.

Select a profile explicitly for model-backed execution:

```bash
export DEVFLOW_PROFILE=mini-free-cloud
export OPENROUTER_API_KEY="..."  # required only for direct OpenRouter routes
```

Profiles contain no credentials. Included-subscription GLM/GPT routes use
Hermes OAuth; direct OpenRouter routes use `OPENROUTER_API_KEY`. Actual routed
model identity must be recorded in run evidence. Free aliases and provider
availability are runtime facts and must be rechecked rather than treated as
permanent architecture.

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
