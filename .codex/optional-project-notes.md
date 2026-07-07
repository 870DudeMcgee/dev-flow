# Codex Project Notes

Codex should follow `AGENTS.md` as the primary instruction source.

This repository no longer uses old milestone contracts, DevMode-era docs, or retired north-star docs as active authority. Do not require legacy task files, claim/release rituals, broad archaeology, local-model ceremony, memory, DAGs, traces, evals, or unified-diff patch gates before ordinary work.

## Current Direction

DevFlow is the local operating layer for turning rough ideas into verified product implementations.

Current active loop:

```text
Idea -> definition -> spec -> plan -> planning judge -> bounded tasks -> builder/judge execution -> verification -> next human decision
```

Ownership boundary:

- Obsidian owns broad capture, knowledge, and cross-project context.
- DevFlow owns the active product-building loop and the evidence needed to move one product task forward safely.
- Git/filesystem artifacts remain the source of truth for actual changes.
- Local workers are bounded implementation/review lanes, not the product identity.

## Starting the DevFlow UI Server

The DevFlow operating layer UI is a local HTTP server (Python stdlib `http.server`). Start it with:

```bash
# Activate venv first, then:
devflow operating-layer serve
```

This serves the UI at `http://127.0.0.1:8765/` by default.

If the in-app browser shows old marketing/control-plane language, hard refresh or open `http://127.0.0.1:8765/?cb=<timestamp>`.

The expected current page has title `Dev-Flow Operating Layer` and a first viewport centered on `Brainstorm`, `Pipeline`, `Worker lanes`, `Review queue`, and `Evidence stream`.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8765` | Port (use `0` for ephemeral) |
| `--open` | `false` | Open in default browser |

### What it serves

- `/` — DevFlow operating layer UI
- `/api/snapshot` — read-only JSON snapshot of project state
- `/api/snapshot?project=<id>` — multi-project drilldown
- `/api/actions/run` — supervisor-safe command execution
- `/api/agents` — configured agent list
- `/api/brainstorm/sessions` — brainstorm transcripts
- `/api/brainstorm/message` — advisory brainstorm chat
- `/api/brainstorm/escalate` — write spec/plan artifacts from brainstorm
- `/healthz` — health check

### Prerequisites

```bash
source .venv/bin/activate
```

### Install as login service on macOS

```bash
devflow operating-layer install-service
```

This installs a per-user LaunchAgent that starts the server at login from the current project root.

### Troubleshooting

- **Port conflict**: pass `--port 0` for an ephemeral port. The ready message prints the actual address.
- **Stale browser cache**: use a cache-busted URL after UI asset changes.
- **No provider key**: brainstorm endpoints fail closed when the configured provider key is unavailable.
- **Can't reach from another machine**: server binds to `127.0.0.1` by default. Pass `--host 0.0.0.0` and configure firewall rules if remote access is needed.

## References

- `AGENTS.md`
- `docs/DEVFLOW_SOURCE_OF_TRUTH.md`
- `docs/README.md`
- `docs/local-worker-policy.md`
- `docs/verification-ledger.md`
