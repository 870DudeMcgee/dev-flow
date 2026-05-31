# Dev-Flow

Dev-Flow is a local-first control room for parallel AI coding workers.

It is not the coding intelligence itself. It is the operational layer around coding intelligence: task state, isolated workspaces, locks and ownership, status, logs, verification evidence, and human-controlled promotion.

Workers are replaceable. The current runtime supports shell workers only, along with an experimental transition layer (registries, manual worker, deterministic task-fit/context packing, and conservative capability routing).

## Current Product Contract

The active runtime contract is [docs/mvp-contract.md](docs/mvp-contract.md). The near-term product direction is [docs/control-room-mvp.md](docs/control-room-mvp.md), grounded by [PRODUCT_NORTH_STAR.md](PRODUCT_NORTH_STAR.md).

### Stable Commands
- **Initialization & Diagnostics**: `devflow init`, `devflow doctor`
- **Dashboard**: `devflow dashboard`
- **Task Lifecycle**: `devflow task create`, `devflow task run --worker shell`, `devflow task verify`, `devflow task list`, `devflow task show`, `devflow task log`
- **Promotion & Merging**: `devflow task promote-preview`, `devflow task promote`

### Experimental Transition Commands
- **Agent Registry**: `devflow agent list`, `devflow agent show`, `devflow agent packet`
- **Task Estimation**: `devflow task fit`, `devflow task pack`
- **Scouting & Routing**: `devflow task scout`, `devflow task route`, `devflow task scorecard`

These transition commands are allowed only as read-only/manual planning aids until promoted into the stable contract.

The current control-room MVP intentionally excludes enabled remote provider adapters, browser or web dashboards, database state, git worktree orchestration, and autonomous scheduling/routing. The future registries and adapter-runtime designs are documented in [docs/architecture/agent-registry-and-adapter-runtime.md](docs/architecture/agent-registry-and-adapter-runtime.md) and [docs/architecture/agent-selection-and-context-routing.md](docs/architecture/agent-selection-and-context-routing.md).

## Runtime Shape

Dev-Flow stores durable task state as local filesystem artifacts:

```text
.devflow/
  tasks/<task-id>/
    task.yaml
    events.jsonl
    verification.json
    logs/
      worker.log
      verify.log
  workspaces/<task-id>/
```

`task.yaml` is canonical current state. `events.jsonl` is append-only evidence. `verification.json` stores the latest verification result. Worker and verification logs are raw command evidence. Shell worker output stays in `.devflow/workspaces/<task-id>/` until a human explicitly previews and promotes verified changes.

## Durable Context Structure

The broader `.devflow/` tree is also the durable context layer for the control room. It contains project orientation, active goals, classified context, layered product and architecture notes, worker/model registries, lock documentation, derived reports, and preserved archive material.

Start with:

- [.devflow/project/project.yaml](.devflow/project/project.yaml): machine-readable project orientation.
- [.devflow/goals/bootstrap-devflow-filesystem/goal.yaml](.devflow/goals/bootstrap-devflow-filesystem/goal.yaml): active bootstrap filesystem goal.
- [.devflow/context/active/README.md](.devflow/context/active/README.md): context classification entry point.
- [.devflow/layers/architecture/contracts.md](.devflow/layers/architecture/contracts.md): layer-local contract pointers.
- [docs/devflow-control-loop-contracts.md](docs/devflow-control-loop-contracts.md): reference architecture for the target structure.

## Quick Start

Install locally from the repository root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
```

Initialize the control-room structure:

```bash
.venv/bin/python -m devflow.cli init
.venv/bin/python -m devflow.cli doctor
```

Create, run, verify, inspect, and preview one shell task:

```bash
TASK_ID=$(.venv/bin/python -m devflow.cli task create "write hello result" | sed -n 's/^Created \(task-[^:]*\):.*/\1/p')
.venv/bin/python -m devflow.cli task run "$TASK_ID" --worker shell -- /bin/sh -c "echo hello > result.txt"
.venv/bin/python -m devflow.cli task verify "$TASK_ID" --shell "test -f result.txt"
.venv/bin/python -m devflow.cli task show "$TASK_ID"
.venv/bin/python -m devflow.cli dashboard
.venv/bin/python -m devflow.cli task promote-preview "$TASK_ID"
```

Promotion is explicit and human-controlled:

```bash
.venv/bin/python -m devflow.cli task promote "$TASK_ID"
```

Use promotion only after reviewing the preview and verification evidence.

## DevMode Relationship

DevMode is the portable discipline layer for agent behavior: mode gating, search-before-read context discipline, focused changes, and verification before completion.

Dev-Flow is the product in this repository: the local-first control room that owns task state, worker isolation, logs, verification evidence, and promotion readiness.

The canonical DevMode contract is [docs/devmode-contract.md](docs/devmode-contract.md). The boundary is documented in [docs/devmode-devflow-boundary.md](docs/devmode-devflow-boundary.md). DevMode guides humans and agents working in this repo; it is not the Dev-Flow runtime.

DevMode harness compatibility is tracked in [docs/harness-compatibility.md](docs/harness-compatibility.md) for Claude Code, Gemini CLI, Cursor, Codex, OpenCode, and VS Code / GitHub Copilot.

## Active References

- [PRODUCT_NORTH_STAR.md](PRODUCT_NORTH_STAR.md): long-term product identity and self-checks.
- [docs/mvp-contract.md](docs/mvp-contract.md): stable current command, filesystem, and safety contract.
- [docs/control-room-mvp.md](docs/control-room-mvp.md): near-term MVP authority.
- [docs/architecture/agent-registry-and-adapter-runtime.md](docs/architecture/agent-registry-and-adapter-runtime.md): next architecture direction for provider, agent, role, permission, adapter, and routing contracts.
- [docs/architecture/agent-selection-and-context-routing.md](docs/architecture/agent-selection-and-context-routing.md): future task-fit, context-estimation, model-capability, context-pack, scout, and routing-quality design.
- [docs/roadmap.md](docs/roadmap.md): current sequencing and deferred work.
- [docs/agent-handoff.md](docs/agent-handoff.md): orientation for future agents.
- [docs/devflow-operating-model.md](docs/devflow-operating-model.md): role split between human, main chat agent, Dev-Flow kernel, worker agents, and DevMode.
- [docs/read-only-control-room-agent.md](docs/read-only-control-room-agent.md): main chat agent responsibilities and boundaries.
- [docs/devmode-devflow-boundary.md](docs/devmode-devflow-boundary.md): product/runtime boundary between DevMode and Dev-Flow.

## Development Boundary

Active control-room code belongs under:

```text
src/devflow/control_room/
```

Legacy software-factory files are quarantined under:

```text
src/devflow/_legacy/
```

Do not add new product features under top-level compatibility shims or `_legacy/`.

## Verification

Focused control-room verification:

```bash
.venv/bin/python -m pytest tests/test_architecture_boundaries.py tests/test_devflow_init_structure.py tests/test_control_room_shell.py tests/test_promote_preview.py tests/test_task_packet.py -q
```

Current development should keep strengthening the control-room loop: shell-worker task lifecycle, the `devflow-manual-codex-worker` proof-agent handoff, workspace isolation, status visibility, verification evidence, human-controlled promotion, and merge readiness.

## License

Dev-Flow is released under the [MIT License](LICENSE).

This repository also contains DevMode skill and harness material influenced by [Superpowers](https://github.com/obra/superpowers). Attribution details are in [ATTRIBUTION.md](ATTRIBUTION.md).
