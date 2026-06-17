# Codex Project Notes

Codex should follow `AGENTS.md` as the primary instruction source.

This repository no longer uses the old Devflow Software Factory workflow as active authority. Do not require legacy task files, claim/release rituals, worktree ceremonies, local-model delegation, memory, DAGs, traces, evals, or unified-diff patch gates before ordinary work.

## Current Direction

Dev-Flow is a local-first control room for parallel AI coding workers.

Current runtime:
- shell-worker task lifecycle
- filesystem task state
- isolated workspaces
- logs, reports, questions, and verification evidence
- human-controlled promotion

Next architecture direction:
- `docs/architecture/agent-registry-and-adapter-runtime.md`
- provider vs agent vs role separation
- permissioned adapter runtime
- manual/local adapters before routing or provider expansion

## Starting the Dev-Flow UI Server

The Dev-Flow operating layer UI is a local HTTP server (Python stdlib `http.server`). Start it with:

```bash
# Activate venv first, then:
devflow operating-layer serve
```

This serves the UI at `http://127.0.0.1:8765/` by default.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8765` | Port (use `0` for ephemeral) |
| `--open` | `false` | Open in default browser |

### What it serves

- `/` — Dev-Flow control room UI (HTML/CSS/JS bundled in Python)
- `/api/snapshot` — Read-only JSON snapshot of project state
- `/api/snapshot?project=<id>` — Multi-project drilldown
- `/api/actions/run` — Supervisor-safe command execution (read-only + approved mutations)
- `/api/agents` — Configured agent list
- `/api/brainstorm/sessions` — Advisory brainstorm transcripts
- `/api/brainstorm/message` — Advisory chat with configured DeepSeek V4 Flash profile
- `/api/brainstorm/escalate` — Write spec/plan artifacts from brainstorm
- `/healthz` — Health check

### Prerequisites

```bash
source .venv/bin/activate
```

### Install as login service (macOS)

```bash
devflow operating-layer install-service
```

This installs a per-user LaunchAgent that starts the server at login from the current project root.

### Troubleshooting

- **Port conflict**: Pass `--port 0` for an ephemeral port. The ready message prints the actual address.
- **No provider key**: Brainstorm endpoints fail closed when the configured OpenRouter key is unavailable.
- **Can't reach from another machine**: Server binds to `127.0.0.1` by default. Pass `--host 0.0.0.0` and configure firewall rules if remote access is needed.

## References

- `AGENTS.md`
- `PRODUCT_NORTH_STAR.md`
- `docs/control-room-mvp.md`
- `docs/mvp-contract.md`
- `docs/architecture/agent-registry-and-adapter-runtime.md`
- `docs/architecture/local-operating-layer-ui.md`
