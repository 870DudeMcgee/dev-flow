# Patch Application and Verification Readiness Gating (Milestones 9 & 10)

This document specifies the design contracts, state mutations, and gating mechanics for **Milestone 9 (Explicit Reviewed Patch Apply)** and **Milestone 10 (Verification/Readiness Hardening)** of the Dev-Flow control room.

---

## 1. Explicit Patch Application Gating (Milestone 9)

To ensure model-generated code is safely inspected before it modifies the isolated workspace, `apply-patch` acts as a strict gating boundary.

### CLI Command
```bash
devflow task apply-patch <task-id> [--agent <agent-id>] [--run-id <run-id>]
```

### Pre-conditions & Verification Gates
Before mutating any workspace files, the control room enforces that the target patch has matching, fresh verification evidence:
1. **Patch Review Requirement**:
   - A `patch-review.json` record must exist.
   - The review status must be in `["low_risk_candidate", "review_required"]`.
   - Statuses like `["dangerous_patch", "invalid_patch", "no_patch_candidate"]` must be rejected.
2. **Patch Dry-run Requirement**:
   - A `patch-dry-run.json` record must exist.
   - The dry-run status must be in `["would_apply_cleanly", "would_create_files", "would_modify_with_warnings"]`.
   - Statuses like `["missing_target_file", "hunk_mismatch", "rejected_by_patch_review", "invalid_patch", "workspace_missing"]` must be rejected.

### State & File Mutations on Success
When the gates are satisfied, the control room performs the following atomic mutations:
1. Mutates the files in the isolated workspace (e.g., `.devflow/workspaces/<task_id>/`).
2. Writes a hash-addressed patch record under `.devflow/tasks/<task_id>/patches/<patch-hash>.json` containing the patch data and metadata.
3. Writes the latest application pointer under `.devflow/tasks/<task_id>/patch-application.json`.
4. Appends a `patch_applied` event to `.devflow/tasks/<task_id>/events.jsonl`.

---

## 2. Verification & Promotion Gating Hardening (Milestone 10)

Applying a patch mutates the workspace, which immediately invalidates all previous test execution and verification evidence.

### Invalidation Trigger
When a patch is applied:
- Prior verification evidence is discarded (status resets to `not_run`, logs and verification command metadata are cleared).
- Merge readiness status (`merge-readiness.json`) is set to `ready = False`.

### Binding Verification to the Patch Hash
To satisfy the promotion gate, the user or worker must trigger a fresh verification run:
```bash
devflow task verify <task-id> --shell "<command>"
```
On successful completion, the verification service:
1. Executes the verification command in the workspace.
2. Captures stdout/stderr and writes `verify.log`.
3. Writes `.devflow/tasks/<task_id>/verification.json`, explicitly setting `verified_patch_hash` to the patch hash recorded in `patch-application.json`.

### Strict Promotion Gating
The `devflow task promote <task-id>` command enforces the following readiness checks:
- The task must have a verification record (`verification.json`) marked as successful.
- The `verified_patch_hash` in `verification.json` **must exactly match** the current patch hash in `patch-application.json`.
- If the hashes do not match (or `patch-application.json` exists but `verified_patch_hash` is missing/stale), promotion is blocked.
