# Design Spec: devflow MVP Safe Unified-Diff Runner

Date: 2026-05-26
Status: AUTHORITATIVE FOR MVP

## Summary

devflow is a vendor-neutral protocol and CLI that executes bounded task files safely through git-native unified diffs.

Codex Desktop, VS Code/Copilot, and Antigravity are peer orchestrators. Each orchestrator may run a full internal subagent dev team and own a task end-to-end. The shared repo, task files, branches, and reports are the coordination surface between orchestrators.

The CLI is intentionally narrow for MVP:
- init
- status
- run <task-file>
- run <task-file> --yes

`run <task-file>` previews by default. `--yes` is required to apply code changes.

## Canonical Architecture

Task file -> clean-worktree gate -> diff validation -> protected-file gate -> dry-run patch -> PREVIEWED report or --yes apply -> verification -> failure classification -> rollback if needed -> task report.

Source of truth remains files + git state in-repo.

## Canonical Config Responsibilities

config.json is enforceable policy:
- checkpoint strategy and branch prefix
- protected path patterns
- verification commands and fallback behavior
- retry budget taxonomy

constitution.md is advisory and human-facing.

## Canonical Task Format

Task markdown schema:
- header metadata (Status, Goal, Plan, Assigned Agent, Owner Lock, Risk, Branch, Touched Files)
- sections 1..10 (Objective, Allowed Files, Do Not Touch, Required Context, Implementation Instructions, Patch Protocol, Verification Commands, Failure Handling, Execution Results, Final Report)

Patch content is supplied as a fenced diff block.

Task ownership is explicit. PENDING tasks may be claimed by any orchestrator. CLAIMED/RUNNING tasks belong to their Assigned Agent and Owner Lock until released, completed, failed, blocked, or overridden by the human.

## MVP Safety Behavior

Required:
- stop before mutation when the git worktree is dirty
- detect files in diff
- block protected-file changes before apply
- create checkpoint branch before patch operations
- dry-run patch before apply
- run verification from task/config/auto-detect order
- classify failures and honor retry budgets
- rollback when run fails after apply
- write one report file per run

Deferred:
- full risk scoring engine
- automated route-to-agent execution by failure type
- AST-aware code editing
- orchestration planning commands

## Deprecations (Explicit)

Deprecated for MVP:
- XML search/replace edit protocol
- slim .devflow-only prototype shape
- hardcoded model-specific orchestration coupling

Replaced by:
- full .devflow protocol tree
- unified diff patching
- model-configurable orchestrator metadata (future milestone)
