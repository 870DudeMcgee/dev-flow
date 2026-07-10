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

# Read-only, auto-refreshing pipeline status board.
devflow status serve                       # http://127.0.0.1:8770/

# Deterministic V2 stage-chain regression fixture (no model calls).
devflow loop spine-fixture --json
```

If the console script is unavailable:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli status serve
PYTHONPATH=src .venv/bin/python -m devflow.cli loop spine-fixture --json
```

The status board is a supporting live-evidence view, not a second chat surface.
It reads pipeline-run state from disk while Hermes performs brainstorming and
orchestration.

## Development Boundary

```text
src/devflow/loop/          # V2 loop contracts, persistence, scout, and model slots
src/devflow/control_room/  # V2 read-only status board
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
