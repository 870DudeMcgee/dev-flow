# Changelog

> **Historical pre-V2 draft:** the `0.1.0` notes below describe the removed V1
> checkout and are retained only as release history. They are not an active
> runtime contract or roadmap. Current behavior is governed by
> [`docs/DEVFLOW_SOURCE_OF_TRUTH.md`](docs/DEVFLOW_SOURCE_OF_TRUTH.md),
> `AGENTS.md`, and the current CLI help.

All notable DevFlow V2 changes should be recorded here before a tag is cut.

Dev-Flow follows semantic versioning for public releases:

- MAJOR: incompatible CLI, task-state, or workspace contract changes.
- MINOR: backward-compatible commands, artifacts, safety gates, or visibility improvements.
- PATCH: backward-compatible fixes, docs corrections, and packaging repairs.

State compatibility is part of the release contract. Any change to `.devflow/config.yaml`, `task.yaml`, `verification.json`, `merge-readiness.json`, task event records, or workspace layout must be called out here with either a backward-compatibility note, a migration path, or a clear refusal/upgrade message.

## 0.1.0 - Unreleased

### Added

- Shell-worker runtime milestone with local task creation, isolated workspaces, logs, verification evidence, dashboard visibility, promotion preview, and human-controlled promotion.
- Manual proof-agent handoff path for `devflow-manual-codex-worker` without provider API execution.
- Adapter maturity boundary that allows only stable runtime adapters to execute.
- Shell worker hardening for environment allowlisting, timeouts, and log-size limits.
- Shell and verification timeout hardening now terminates POSIX child processes in the same process group.
- Atomic write-then-replace persistence for `task.yaml`, `summary.json`, `verification.json`, and `merge-readiness.json`.
- Explicit patch review/application flow for provider-generated `proposal.patch` evidence.
- Public package metadata now uses the top-level Dev-Flow README as the long description and declares alpha CLI project metadata.
- Schema version markers for task state, verification, merge-readiness, and summary artifacts, with unknown task schema versions refused by `doctor`.
- Task-local mutation locks with owner metadata and stale-lock recovery for run, verify, apply-patch, and promote operations.
- Hash-chained task event records with `doctor` validation for malformed or edited `events.jsonl` streams.
- Opt-in Git-native shell-worker task lane via `devflow task create --git-worktree`, with worker branch/worktree evidence, commit-bound verification, Git-native promotion preview, strict Git integrity checks, and human-controlled Git-aware promotion.
- Dry-run-first Git cleanup commands for the opt-in shell-worker lane: worktree/branch inventory, orphaned worktree pruning, task branch archiving, and task-local Git resource cleanup.

### Notes

- No public release artifact has been published yet.
- Task event records now include `event_index`, `previous_event_hash`, and `event_hash`; older unhashed task events remain readable as legacy evidence, and new events chain from the legacy tail.
- Provider-backed adapters, autonomous routing, web dashboard, database state, and provider-backed worktree orchestration remain outside the stable runtime contract.
- Shell execution remains trusted local execution: path-isolated in copied task workspaces, not OS-sandboxed.
