# V2-06: Verification Adapter

## Goal
Create the v2 verification adapter. After builder/judge passes and the loop enters `verification`, this adapter records verification receipts and advances the loop toward `human_decision` when evidence is passing.

## Files to create
- `src/devflow/loop/verification.py`
- `tests/test_loop_verification.py`

## Do NOT modify
- Existing files

## Models

### `VerificationStatus(str, Enum)`
Values:
- `passed`
- `failed`
- `blocked`
- `needs_review`

### `VerificationReceipt(BaseModel)`
Fields:
- `run_id: str`
- `receipt_id: str`
- `status: VerificationStatus`
- `command: str | None = None`
- `summary: str`
- `evidence_path: str | None = None`
- `exit_code: int | None = None`
- `created_at: str`

## Functions

### `record_verification_receipt(root: Path | str, receipt: VerificationReceipt) -> tuple[DevFlowLoopState, VerificationReceipt]`
Record a verification receipt and update loop state.

Behavior:
1. Load loop state with `load_loop_state`.
2. Require state is `verification`, unless it is already `human_decision` and receipt is being appended. Raise ValueError otherwise.
3. Write receipt to pipeline run dir as `verification-receipt-<receipt_id>.json`.
4. Append the receipt path to `state.verification_receipts` if absent.
5. If receipt status is `passed` and current state is `verification`, advance to `human_decision`.
6. If receipt status is `failed` or `needs_review`, stay at `verification` and set `next_human_decision` to a clear review/fix prompt.
7. If receipt status is `blocked`, transition to `blocked` and set `next_human_decision` to the receipt summary.
8. Save loop state.
9. Return `(updated_state, receipt)`.

### `verification_ready_for_human(state: DevFlowLoopState) -> bool`
Return True when:
- state.stage == `human_decision`, and
- at least one verification receipt exists.

## Tests required
- `VerificationReceipt` serializes/validates.
- `record_verification_receipt` rejects stages before verification.
- `record_verification_receipt(status=passed)` advances `verification -> human_decision`.
- Passed receipt path is added to `state.verification_receipts`.
- Duplicate receipt path is not added twice.
- Failed receipt stays at `verification` and sets `next_human_decision`.
- Needs-review receipt stays at `verification` and sets `next_human_decision`.
- Blocked receipt transitions to `blocked` and sets `next_human_decision`.
- Receipt JSON is written to pipeline run directory.
- Additional receipt can be appended while already at `human_decision`.
- `verification_ready_for_human` returns True only with human_decision + receipts.
- Enum has all four statuses.

## Constraints
- Import from `devflow.loop.models`, `devflow.loop.adapter`
- Import from `devflow.control_room.pipeline_run` only for `update_pipeline_run_record`
- Keep verification.py under 200 lines
- Pydantic v2
- Use tmp_path for filesystem tests
- Deterministic only. No shell execution, no model calls. This adapter records receipts; a separate runner executes commands.
