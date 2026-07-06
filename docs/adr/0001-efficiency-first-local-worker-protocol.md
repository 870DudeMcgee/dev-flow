# Efficiency-first local worker protocol

Status: accepted

Dev-Flow is the operator-facing authority for local worker protocol decisions, while Hermes, Codex, MCP servers, and local model servers remain execution or telemetry backends. When choosing between local-worker designs, prefer the option that is simpler and more efficient; if the simpler design preserves needed evidence and safety, it wins.

For local model fleet questions, passive MCP fleet telemetry is the default because it is cheaper, smaller, and less disruptive than model calls. Active smoke completions are explicit decision-point evidence only: run them before launching a local worker, after routing/config changes, or when telemetry reports a mismatch; do not bake smoke calls into normal inventory.

MCP telemetry servers are disabled by default unless the current session needs that operator surface. Read-only MCP is still context overhead, so a server should be enabled for local-worker or operator sessions and disabled again when the session no longer needs it.

Default verification for telemetry MCP servers uses deterministic mocked unit tests. Live fleet checks, port probes, and smoke completions belong behind explicit reality-check commands so routine verification stays fast and does not depend on which local models happen to be running.

For local implementation work, Qwen 3.6 27B Q5 MTP is the trusted single local coding worker. In Codex, the supported workflow is a visible `qwen36_27b_mtp_coder` subagent spawn; the returned subagent output is the session-level proof that the lane is exposed. In Hermes, `hermes-qwen-mtp` mirrors the same bounded packet semantics with `qwen_ready(smoke=true)` before `qwen_run`. Qwen remains one-lane and must not run beside another big local model; the supervisor still owns final verification and semantic review.

This supersedes earlier local-scout-by-default and multi-route preference docs for current sessions. The old routes remain installed for explicit diagnostics and scout-only exceptions, but they are not automatic defaults.

Operational summary: [docs/local-worker-policy.md](../local-worker-policy.md).
