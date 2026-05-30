# CLI Verification Visibility Milestone Checkpoint

Status: historical checkpoint. This records completed behavior only; current authority remains [mvp-contract.md](mvp-contract.md) and [control-room-mvp.md](control-room-mvp.md).

This document records the successful completion of the **CLI Verification Visibility** milestone. This slice enhances CLI task transparency and observability during task lifecycle states using only existing canonical data.

## Completed Capabilities

1. **Canonical Verification State Surface**:
   - `devflow task show <id>` now directly surfaces verification information using canonical files.
   - It parses `verification.json` and gracefully falls back to `task.yaml` properties if `verification.json` is missing or malformed.
   - Surfaced fields include:
     - `verification_status`
     - `verification_exit_code` (displayed only when a verification run has occurred)
     - `verification_log_path`
2. **Suggested Next Action Guidance**:
   - Computes a simple, text-based `suggested_next_action` based on current task lifecycle and verification states:
     - `created`: Recommend running the task (`devflow task run ...`).
     - `running`: Recommend waiting / monitoring execution logs.
     - `complete`: Recommend verifying the task (`devflow task verify ...`).
     - `verified` / `passed`: Recommend reviewing results before human promotion.
     - `verification_failed` / `failed`: Recommend fixing failures and re-running verification.
     - `worker_failed`: Recommend checking logs, resolving the issue, and re-running the task.
     - `timeout`: Recommend running with an increased `--timeout-seconds`.
     - `blocked`: Recommend resolving the safety / workspace block before running again.
3. **Strictly Read-Only Operation**:
   - The show command remains entirely read-only. It does not write to the filesystem or mutate any task properties.
4. **Acceptance Test Coverage**:
   - A robust end-to-end test suite (`test_task_show_verification_and_next_action`) validates:
     - Output matching of all fields and actions under various states.
     - Successful fallback when canonical files are missing.
     - Strong assertions proving that the command is non-mutating and remains read-only.

## Core Architectural Boundaries & Constraints

* **Derived State Separation**:
  - `packet.json` remains a derived task context projection and is **not** canonical.
  - `summary.json` is derived/cached-only and is **not** an authority for `task show`.
* **Human-Controlled Promotion Boundary**:
  - Verification does not imply or execute automatic promotion.
  - The suggested next action for verified tasks explicitly guides: `Task is verified. Review the result before any human-controlled promotion.`
* **No Future Out-Of-Scope Architecture**:
  - No database dependencies or local model routers are added.
  - External adapters (Codex, Aider, Hermes), browser/web dashboards, automatic merge behavior, and PR automation remain completely out of scope.
