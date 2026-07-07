# Efficiency-first local worker protocol

Status: accepted

Dev-Flow is the operator-facing authority for local worker protocol decisions, while Hermes, Codex, MCP servers, and local model servers remain execution or telemetry backends. When choosing between local-worker designs, prefer the option that is simpler and more efficient; if the simpler design preserves needed evidence and safety, it wins.

For local model fleet questions, passive MCP fleet telemetry is the default because it is cheaper, smaller, and less disruptive than model calls. Active smoke completions are explicit decision-point evidence only: run them before launching a local worker, after routing/config changes, or when telemetry reports a mismatch; do not bake smoke calls into normal inventory.

MCP telemetry servers are disabled by default unless the current session needs that operator surface. Read-only MCP is still context overhead, so a server should be enabled for local-worker or operator sessions and disabled again when the session no longer needs it.

Default verification for telemetry MCP servers uses deterministic mocked unit tests. Live fleet checks, port probes, and smoke completions belong behind explicit reality-check commands so routine verification stays fast and does not depend on which local models happen to be running.

Current Codex/local-worker session behavior is defined by
`/Users/jewelbait/.codex/session-operating-contract.md`.

Operational summary: [docs/local-worker-policy.md](../local-worker-policy.md).
