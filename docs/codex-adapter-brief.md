# Codex Adapter Brief

Status: design-only brief. No runtime behavior is implemented by this document.

This brief defines a future Codex worker adapter slice that could fit inside the current Dev-Flow control-room model. It does not change the current shell-worker control-room contract in [mvp-contract.md](mvp-contract.md). Codex is not the next adapter to implement unless the registry/manual/shell-alignment sequence in [docs/architecture/agent-registry-and-adapter-runtime.md](architecture/agent-registry-and-adapter-runtime.md) has already been satisfied.

## Goal

Codex should be just another worker adapter.

It must conform to the same `WorkerAdapter` boundary used by the shell adapter: Dev-Flow validates the workspace, supplies Dev-Flow-owned paths, invokes the adapter, and receives a structured worker result back.

Codex must receive a bounded Dev-Flow task packet, not arbitrary repository context; the packet contract is described in [task-packet-contract.md](task-packet-contract.md).

Dev-Flow remains the control plane. It continues to own task state, workspace containment, logs, result summaries, verification evidence, merge-readiness decisions, and human approval gates.

## Non-Goals

This pass does not define or implement:

- provider integration;
- agent registry or routing implementation;
- authentication or secrets handling;
- prompt orchestration;
- multi-agent scheduling;
- copy-back, merge, or pull request automation;
- dashboard expansion;
- runtime changes to the current shell-only MVP.

## Proposed Future Adapter Behavior

A future Codex adapter should follow the existing worker adapter shape:

1. Dev-Flow reads canonical task state and chooses what context to expose.
2. Dev-Flow validates `.devflow/workspaces/<task-id>/` before the adapter runs.
3. Dev-Flow passes only the isolated task workspace and approved task artifact paths to the adapter.
4. Codex works inside the isolated task workspace, treating it as the only writable jobsite.
5. Codex writes output files and task artifacts inside the workspace.
6. Dev-Flow captures Codex logs through Dev-Flow-owned log paths.
7. The adapter returns a `WorkerResult`-like structured result with status, exit code or failure reason, latest log line, log path, and result path.
8. Dev-Flow records task state transitions, events, result summaries, verification state, and merge-readiness evidence after the adapter returns.

The Codex adapter may produce notes or suggested verification commands as workspace artifacts, but those suggestions are worker output only. They are not authoritative verification.

## Required Safety Rules

- Workspace containment remains mandatory. Codex work happens inside `.devflow/workspaces/<task-id>/` unless Dev-Flow explicitly exposes another artifact.
- Canonical task state remains Dev-Flow-owned. The adapter must not write directly to `task.yaml`, mutate task status, or append lifecycle events except through future Dev-Flow-owned APIs.
- `summary.json` remains derived/cache only. It must never be treated as source of truth.
- Codex must not write directly to the main checkout.
- Verification remains Dev-Flow-owned. Codex must not mark verification as passed or failed.
- Merge readiness remains Dev-Flow-owned. Codex must not mark work as merge-ready.
- Human approval gates remain required before any promotion, copy-back, pull request, or merge behavior.
- Logs and result summaries remain Dev-Flow-owned evidence surfaces, even when adapter output is produced by Codex.

## Minimal First Implementation Slice, For Later

The smallest future implementation should be a disabled-safe slice:

1. Add Codex only after the registry can load agents/providers/roles and the manual adapter exists.
2. Add a Codex adapter stub that conforms to the registry-selected adapter contract but refuses to run unless explicitly enabled.
3. Add configuration or environment detection only if the stub needs it to produce a clear disabled message.
4. Add focused tests proving the disabled Codex adapter fails safely, does not execute provider calls, does not write worker logs as if work ran, and does not mutate task state beyond a Dev-Flow-owned refusal path.
5. Keep `shell` as the only default supported worker until a later pass deliberately enables Codex.
6. Do not call a real provider, spawn a Codex CLI, handle secrets, or construct prompt orchestration in this first slice.

This slice should be reversible and boring. Its purpose is to prove the adapter registry can refuse a future adapter safely before any real Codex execution exists.

## Open Questions

- How should credentials be supplied without leaking into logs, task artifacts, or shell history?
- Should the adapter run a Codex CLI command, call an API directly, or support both behind the same adapter boundary?
- What task packet should Codex receive: only `task.yaml` plus selected files, a generated context packet, a task-specific instruction file, or another Dev-Flow-owned artifact?
- How should logs be redacted before they become durable Dev-Flow evidence?
- What timeout, process, file-size, token, and network limits are required before real execution is safe?
- Should Codex be allowed to ask structured questions, and if so, what Dev-Flow-owned question artifact or API should receive them?
- How should failures distinguish provider unavailable, authentication missing, prompt rejected, timeout, workspace violation, and worker-generated failure?

## Design Risks

- Credential leakage is the highest-risk unsolved area and must be designed before provider calls exist.
- Prompt/context shape can quietly erode workspace containment if Codex receives broad repository paths instead of explicit exposed artifacts.
- Provider logs may contain sensitive prompts, file contents, or environment details unless redaction is designed up front.
- A future implementation could accidentally let Codex self-certify by writing verification-looking artifacts; Dev-Flow must keep verification state separate.
- Enabling networked provider execution changes the threat model beyond the current local shell-worker MVP and should require an explicit safety review.
