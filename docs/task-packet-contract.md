# Task Packet Contract

Status: design-only contract. No runtime behavior is implemented by this document.

This document defines the minimal read-only task packet a future worker adapter may receive from Dev-Flow. It does not change the frozen shell-worker MVP contract in [mvp-contract.md](mvp-contract.md).

## Goal

A task packet is the bounded read-only context Dev-Flow gives to a worker adapter.

It exists to prevent workers from grabbing arbitrary repository context, while still giving them enough task state and evidence to work reproducibly. It should support token efficiency, deterministic replay, and safe worker handoff.

A task packet must not become a new source of truth. It is a derived projection assembled from Dev-Flow-owned canonical artifacts and explicit metadata.

## Canonical Inputs

A task packet may be assembled from these Dev-Flow-owned inputs:

- `task.yaml`, for canonical task identity, title, status, workspace path, worker, timestamps, and current state;
- `events.jsonl`, bounded to recent or relevant events only;
- `verification.json`, for latest verification state and evidence pointers;
- `logs/worker.log`, summarized or tail-limited only;
- `logs/verify.log`, summarized or tail-limited only;
- optional `summary.json`, as derived/cache state only;
- explicit Dev-Flow-owned metadata, such as adapter name, constraints, allowed artifact paths, timeout policy, or truncation notes;
- the explicit workspace path under `.devflow/workspaces/<task-id>/`.

Dev-Flow chooses which inputs to include. Worker adapters do not decide their own read surface by walking the repository.

## Explicitly Excluded By Default

A task packet must not include these by default:

- entire repository contents;
- arbitrary hidden files;
- credentials or secrets;
- provider tokens;
- full event history unless explicitly requested by Dev-Flow;
- full logs unless explicitly requested by Dev-Flow;
- files outside the isolated workspace;
- main checkout paths intended for mutation.

If a future packet needs any excluded content, the inclusion must be explicit, bounded, logged, and justified by Dev-Flow-owned policy.

## Proposed Future Packet Shape

A future packet can be represented as structured data with this minimum shape:

```text
task_id: string
title: string
status: string
workspace_path: string
worker_adapter: string
summary: string | null
recent_events: list[event_summary]
verification: verification_summary
result_summary: string | null
constraints: list[string]
allowed_artifacts: list[path]
omitted_counts: map[string, int]
truncation_notes: list[string]
```

Suggested field meanings:

- `task_id`: task identity from canonical `task.yaml`.
- `title`: task title from canonical `task.yaml`.
- `status`: current task status from canonical `task.yaml`.
- `workspace_path`: explicit isolated workspace path under `.devflow/workspaces/<task-id>/`.
- `worker_adapter`: the adapter Dev-Flow intends to invoke.
- `summary`: a human-readable task summary assembled from canonical state, optionally accelerated by `summary.json` when it agrees with canonical files.
- `recent_events`: bounded event summaries from `events.jsonl`.
- `verification`: latest verification state from `verification.json`, with log pointers rather than full logs by default.
- `result_summary`: bounded summary of `result.md` or relevant worker output, if present.
- `constraints`: explicit worker rules, such as workspace containment, no main-checkout writes, no verification self-certification, and timeout expectations.
- `allowed_artifacts`: explicit Dev-Flow-approved artifacts or paths the adapter may read or write.
- `omitted_counts`: counts of omitted events, log lines, files, or other bounded sections.
- `truncation_notes`: human-readable notes explaining what was omitted and why.

The exact serialization format is future work. JSON is likely the simplest first format, but this contract does not require an implementation choice.

## Token Limits And Truncation

Task packets must be bounded and deterministic:

- Recent events should be limited by count, age, relevance, or an explicit policy chosen by Dev-Flow.
- Logs should be tail-limited, summarized, or both.
- Task summaries may use `summary.json` only as derived/cache state after canonical checks pass.
- Omitted content must be disclosed with counts or notes.
- Ordering must be deterministic so repeated packet builds are comparable.
- If two candidate inputs have the same ordering key, tie-break with stable path or timestamp ordering.
- Missing, malformed, stale, or conflicting derived inputs must fall back to canonical artifacts.

The first implementation should prefer conservative defaults: small recent-event windows, short log tails, and explicit omitted-count notes.

## Authority Rules

- `task.yaml` remains canonical for task identity, title, status, workspace path, worker, and timestamps.
- `verification.json` remains canonical for latest verification state.
- `events.jsonl` remains canonical append-only evidence.
- `logs/worker.log` and `logs/verify.log` remain canonical raw execution output.
- `summary.json` is derived/cache only.
- Task packets are derived/read-only projections.
- If a packet conflicts with canonical files, canonical files win.
- If `summary.json` conflicts with canonical files, ignore it and build from canonical files.
- If a packet is missing or stale, Dev-Flow may regenerate it without losing state.

Workers may use the packet to understand assigned work. They must not treat it as a mutable state store.

## Adapter Rules

- Adapters may read the task packet Dev-Flow provides.
- Adapters may not mutate the packet and treat it as state.
- Adapters may not use the packet to bypass workspace containment.
- Adapters may not infer permission to read arbitrary repository paths from packet content.
- Adapters may not self-certify verification or merge readiness.
- Adapters may write only through approved worker output paths and workspace-local artifacts.
- Adapters must treat omitted-count and truncation notes as boundaries, not invitations to fetch everything else.

## Future Implementation Slice, For Later

The smallest useful implementation should be narrow and test-first:

1. Add a `TaskPacket` data structure.
2. Add a task-packet builder that reads canonical task artifacts and optional derived summaries.
3. Add tests for bounded recent events and tail-limited logs.
4. Add tests for `summary.json` fallback when the cache is missing, malformed, stale, or conflicts with canonical files.
5. Add tests for omitted counts and truncation notes.
6. Add tests proving canonical files take precedence over packet or summary conflicts.
7. Keep the packet builder unused by Codex until a later explicit adapter integration pass.

This slice should not change current shell-worker CLI behavior.

## Out Of Scope

This contract does not define or implement:

- Codex implementation;
- provider APIs;
- prompt orchestration;
- model selection;
- secrets handling;
- copy-back;
- merge automation;
- pull request automation;
- dashboard expansion;
- database state;
- worktrees;
- memory systems;
- DAG systems;
- trace systems;
- eval systems.

## Open Design Risks

- A packet can accidentally become too broad if explicit artifact selection is vague.
- Large logs and event streams can silently exceed token budgets unless truncation is enforced and disclosed.
- Derived summaries can drift from canonical files unless canonical precedence is tested.
- Credential leakage remains possible if future metadata or logs are added without redaction policy.
- A worker may treat omitted-count notes as permission to fetch missing context unless adapter rules are enforced.
- Packet regeneration needs stable ordering, or review and replay become noisy.