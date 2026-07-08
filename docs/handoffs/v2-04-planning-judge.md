# V2-04: Planning Judge

## Goal
Create a first-class planning judge artifact. This is the gate between planning and assignment — it reviews a plan and decides whether it's ready to be broken into bounded tasks.

## Files to create
- `src/devflow/loop/planning_judge.py`
- `tests/test_planning_judge.py`

## Do NOT modify
- Any existing files

## JudgeDecision enum

```python
class JudgeDecision(str, Enum):
    approve = "approve"
    revise = "revise"
    block = "block"
    escalate_to_user = "escalate_to_user"
```

## PlanningJudgeReport model

Pydantic BaseModel:

- `run_id: str`
- `decision: JudgeDecision`
- `repo_grounding: str` — assessment of whether plan is grounded in real repo constraints
- `task_boundaries: str` — assessment of whether tasks are properly bounded
- `verification_reality: str` — assessment of whether verification commands are real
- `overbuild_risk: str` — assessment of whether plan is overbuilt
- `simpler_path: str` — assessment of whether a simpler approach exists
- `required_changes: list[str] = []` — specific changes needed before approval (empty if approved)
- `next_safe_action: str` — what the human/loop should do next
- `created_at: str`

## PlanningEvidence input model

Pydantic BaseModel for the plan evidence the judge reviews:

- `run_id: str`
- `plan_path: str | None = None` — path to plan artifact
- `spec_path: str | None = None` — path to spec artifact
- `target_files: list[str] = []` — files the plan intends to touch
- `verification_command: str | None = None` — proposed verification
- `constraints: list[str] = []` — plan constraints
- `files_exist: bool = False` — whether target files actually exist in the repo
- `has_verification: bool = False` — whether a real verification command exists

## Functions

### `judge_plan(evidence: PlanningEvidence) -> PlanningJudgeReport`
Evaluate planning evidence and produce a judge report.

Decision logic (deterministic rule-based, NOT LLM):

1. **BLOCK** if:
   - `target_files` is empty, OR
   - `spec_path` is None/empty, OR
   - `plan_path` is None/empty

2. **REVISE** if:
   - `files_exist` is False (plan references files that don't exist), OR
   - `has_verification` is False (no real verification command), OR
   - more than 8 target_files (likely overbuilt scope)

3. **ESCALATE_TO_USER** if:
   - `files_exist` is True and `has_verification` is True but constraints contain "escalate" or "user_decision"

4. **APPROVE** if:
   - target_files is non-empty
   - spec_path and plan_path exist
   - files_exist is True
   - has_verification is True
   - target_files count <= 8

Each report must include human-readable `repo_grounding`, `task_boundaries`, `verification_reality`, `overbuild_risk`, `simpler_path`, and `next_safe_action` strings based on the evidence.

### `run_planning_judge(root: Path | str, run_id: str, evidence: PlanningEvidence) -> tuple[DevFlowLoopState, PlanningJudgeReport]`
Full planning judge step:
- Load current loop state
- Call `judge_plan(evidence)`
- Write the report to the pipeline run dir as `planning-judge.json`
- If decision is APPROVE and state is at `planning_judge` stage, advance to `assignment`
- If decision is BLOCK, transition to `blocked`
- If decision is REVISE, stay at `planning_judge`
- If decision is ESCALATE_TO_USER, transition to `blocked` with next_human_decision set
- Save loop state
- Return (updated_state, report)

## Tests required

- `judge_plan` returns BLOCK when no target files
- `judge_plan` returns BLOCK when no spec_path
- `judge_plan` returns BLOCK when no plan_path
- `judge_plan` returns REVISE when files_exist is False
- `judge_plan` returns REVISE when no verification command
- `judge_plan` returns REVISE when too many target files (>8)
- `judge_plan` returns ESCALATE_TO_USER when constraints say escalate
- `judge_plan` returns APPROVE when all evidence is valid
- APPROVE report has empty required_changes
- BLOCK/REVISE reports have non-empty required_changes
- All reports have non-empty assessment strings
- `run_planning_judge` advances to assignment on APPROVE
- `run_planning_judge` transitions to blocked on BLOCK
- `run_planning_judge` stays at planning_judge on REVISE
- `run_planning_judge` writes planning-judge.json to run dir
- JudgeDecision enum has all four values
- PlanningJudgeReport serialization round-trip

## Constraints
- Import from `devflow.loop.models`, `devflow.loop.adapter`
- Import from `devflow.control_room.pipeline_run` only for `update_pipeline_run_record` (writing evidence)
- Keep planning_judge.py under 250 lines
- Pydantic v2
- Use tmp_path for filesystem tests
- The judge is deterministic/rule-based — no LLM calls, no model routing
