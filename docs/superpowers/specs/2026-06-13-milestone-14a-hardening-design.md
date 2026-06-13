# Milestone 14A Hardening Design

## Goal

Dogfood the implemented Milestone 14 goal execution control loop against the live Dev-Flow checkout, capture release-readiness evidence, and leave the next agent a clean multi-project control-room handoff.

## Scope

This is a hardening and evidence slice, not a new feature milestone.

Included:

- Run the freshness goal loop against current canonical goal and task state.
- Resolve lifecycle findings with the least risky explicit human-approved state change.
- Run bounded freshness iterations after lifecycle repair.
- Run the production-readiness dogfood suite.
- Run full pytest and capture the log as release-readiness evidence.
- Run stale-context scans and capture the log as release-readiness evidence.
- Run operating-layer visual QA evidence generation.
- Run `devflow release readiness` against the captured evidence.
- Update active docs and handoffs so the next planned slice is multi-project control room.

Excluded:

- No provider calls.
- No autonomous routing.
- No worker adapter expansion.
- No Hermes, Aider, OpenCode, or PR automation runtime work.
- No multi-project implementation in this slice.
- No automatic goal completion.

## Lifecycle Repair Policy

The first freshness loop after Milestone 14 may find pre-existing goals without `goal-state.yaml`. If a goal is the current active work, activate it explicitly. If a goal is not the current planned lane, block it with an explicit reason instead of activating it into the dispatch queue.

For this slice, `G-0001` is a Hermes rollout goal and not the approved next lane. If it lacks lifecycle state, mark it blocked with a reason that keeps Hermes deferred while preserving the goal evidence.

## Evidence Gates

The slice is complete only when these checks have fresh evidence:

- `devflow freshness loop --json`
- `devflow freshness run --max-iterations 3 --json`
- `devflow freshness run --all-projects --max-iterations 1 --json`
- `devflow dogfood run --suite production-readiness`
- full pytest captured to a log file
- stale-context scan captured to a log file
- `devflow operating-layer visual-qa --write-current`
- `devflow release readiness --pytest-evidence <log> --stale-context-evidence <log>`
- `git diff --check`
- `devflow git status`

## Multi-Project Handoff

The next-agent handoff should focus on multi-project control-room work only. It should point to the existing multi-project architecture and current command surface, list boundaries, and leave one concrete next safe action.
