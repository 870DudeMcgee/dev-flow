# Dev-Flow

Dev-Flow is a local-first control room for parallel AI coding workers.

It is not the coding intelligence itself. It is the operational layer around coding intelligence: task state, isolated workspaces, locks and ownership, status, logs, verification evidence, and human-controlled promotion.

Workers are replaceable. The current runtime supports shell workers only; the next architecture direction is a registry and adapter runtime that keeps future local, remote, and manual workers behind one permissioned contract.

## Current Product Contract

The active runtime contract is [docs/mvp-contract.md](docs/mvp-contract.md). The near-term product direction is [docs/control-room-mvp.md](docs/control-room-mvp.md), grounded by [PRODUCT_NORTH_STAR.md](PRODUCT_NORTH_STAR.md).

Stable commands:

```bash
devflow --help
devflow init
devflow doctor
devflow dashboard
devflow task --help
devflow task create "example task"
devflow task run <task-id> --worker shell -- /bin/sh -c "echo hello > result.txt"
devflow task run <task-id> --shell "echo hello > result.txt"
devflow task verify <task-id> --shell "test -f result.txt"
devflow task list
devflow task show <task-id>
devflow task packet <task-id>
devflow task log <task-id>
devflow task promote-preview <task-id>
devflow task promote <task-id>
```

The current control-room MVP intentionally excludes enabled non-shell adapters, browser or web dashboards, database state, git worktree orchestration, autonomous routing, automatic copy-back, commits, pushes, pull requests, and legacy software-factory workflow machinery. The future registry and adapter-runtime direction is design-only in [docs/architecture/agent-registry-and-adapter-runtime.md](docs/architecture/agent-registry-and-adapter-runtime.md).

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

Current development should keep strengthening the control-room loop: shell-worker task lifecycle, workspace isolation, status visibility, verification evidence, human-controlled promotion, and merge readiness.

## License

Dev-Flow is released under the [MIT License](LICENSE).

This repository also contains DevMode skill and harness material influenced by [Superpowers](https://github.com/obra/superpowers). Attribution details are in [ATTRIBUTION.md](ATTRIBUTION.md).
