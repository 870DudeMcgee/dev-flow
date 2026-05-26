# Master Goal: Finish devflow End-to-End

Date: 2026-05-26
Status: READY
Owner: Human-directed peer orchestrator

## Recommended `/goal`

```text
/goal Finish devflow end-to-end as a safe multi-orchestrator AI development workflow system.

Outcome:
Take the current devflow repo from its stabilized MVP foundation to a coherent, committed, usable system where Codex Desktop, VS Code/Cline, and Antigravity can each act as independent peer orchestrators with their own local-model subagent dev teams, all coordinating safely through one shared repo, .devflow task files, git branches, verification, and reports.

Core product definition:
devflow is a conservative, file-based execution and coordination layer for AI-generated unified diffs. It is not an LLM provider router in the MVP. It lets any IDE orchestrator or human generate a patch, then devflow validates, previews, applies with explicit approval, verifies, rolls back if needed, updates task status, mirrors plan status best-effort, and writes audit reports.

Architecture:
- Shared repo + .devflow files are the coordination plane.
- Git is the safety and recovery plane.
- Task markdown files are the executable work units and canonical task status source.
- plan.json files are secondary indexes and mirror task status best-effort.
- Reports are the audit trail.
- Codex Desktop, VS Code/Cline, and Antigravity are peer orchestrators.
- Each IDE may run a complete internal subagent dev team: analyst, architect, planner, implementer, tester, verifier, reporter.
- Local models are worker subagents used by orchestrators, not owners of repo state.
- Work is divided by claimed task and touched-file scope, not by permanent IDE role.

Current MVP CLI contract:
- devflow init
- devflow status
- devflow run .devflow/tasks/<task>.md
- devflow run .devflow/tasks/<task>.md --yes

Current MVP run contract:
- Without --yes, devflow validates and previews only.
- With --yes, devflow applies, verifies, reports, and updates status.
- Dirty git worktrees block before mutation.
- Protected paths block before apply.
- Allowed Files supports exact paths, glob patterns, and ... shorthand.
- Verification command priority is task, then config, then auto-detection.
- Failed verification rolls source changes back to checkpoint state.
- Task Markdown status is canonical.
- plan.json status mirroring is best-effort only.

Phase 0: Consolidate and commit the current stabilized MVP
1. Inspect the full current diff for coherence.
2. Confirm no generated caches or accidental artifacts are present.
3. Ensure docs, tests, and implementation all describe the same contract.
4. Add or refresh README quickstart for a fresh human/agent.
5. Run verification:
   PYTHONPATH=src python3 -m unittest discover -s tests -q
6. If possible, run a real sample flow in a temporary git repo:
   - devflow init
   - create a task with embedded unified diff
   - devflow run task
   - inspect preview task/report/plan metadata
   - commit or reset preview metadata so the worktree is clean
   - devflow run task --yes
   - inspect task status, plan mirror, and report
7. If verification passes, create one stable git commit for the current MVP consolidation.

Phase 1: Make task ownership first-class
Build the minimum task lifecycle commands needed for safe peer-orchestrator collaboration:
- devflow task claim <task> --agent <codex|vscode|antigravity> --lock <session/team>
- devflow task release <task>
- devflow task status <task>

Status: COMPLETE in commit following Phase 0.

Acceptance criteria:
- Claim updates task header metadata: Status, Assigned Agent, Owner Lock, Branch, Touched Files if provided.
- Claim refuses already claimed/running tasks unless explicit force is provided.
- Release clears Owner Lock and returns task to PENDING or BLOCKED as appropriate.
- Status prints task metadata, allowed files, touched files, latest report path, and plan mirror status.
- Tests cover claim/release/status and ownership collision behavior.

Phase 2: Add canonical task scaffolding
Add commands or templates that make good tasks easy to create:
- devflow task new
- canonical task template with ownership headers
- example embedded diff task
- example plan JSON

Status: COMPLETE in commit following Phase 1.

Acceptance criteria:
- New task files contain sections 1 through 10.
- Task files include Status, Goal, Plan, Assigned Agent, Owner Lock, Risk, Branch, and Touched Files headers.
- Generated examples work with devflow run preview and --yes apply.
- Docs explain that task Markdown is canonical.

Phase 3: Add orchestrator/team scaffolding
Create a visible .devflow/orchestrators or .devflow/skills structure for peer IDE teams:
- codex team template
- vscode/cline team template
- antigravity team template
- local model worker policy

Status: COMPLETE in commit following Phase 2.
- handoff and report expectations

Acceptance criteria:
- No orchestrator is assigned a permanent global role.
- Each orchestrator template describes a full internal dev team.
- Local models are documented as bounded worker agents.
- Task ownership and touched-file locking are the collision-prevention mechanism.

Phase 4: Improve reports and audit trail
Strengthen reports so another orchestrator can review or continue work:
- include status transitions
- include dirty-worktree/protected-path decisions
- include allowed-files decisions
- include checkpoint branch and rollback details
- include verification stdout/stderr snippets or log links
- include plan mirror warnings

Acceptance criteria:
- Reports are human-readable Markdown.
- Reports contain enough detail to recover or audit a task run.
- Tests cover important report fields.

Phase 5: Prepare post-MVP routing without implementing model calls
Document, but do not yet execute, future model/provider routing:
- planner role
- coder role
- reviewer role
- tester role
- verifier role
- summarizer role
- local model worker pool

Acceptance criteria:
- No MVP execution path calls Codex, Gemini, Claude, Copilot, Ollama, or other model providers.
- Future routing is represented as docs/templates/config only.
- Active CLI behavior remains deterministic and testable.

Constraints:
- Do not silently apply patches.
- Do not run mutation on dirty worktrees.
- Do not touch protected files without explicit approval flow.
- Do not reintroduce XML search/replace as the active patch protocol.
- Do not add model/provider calls to MVP execution.
- Do not assume fixed global IDE roles.
- Do not overwrite unrelated human/agent changes.
- Do not use destructive git operations unless they are part of the established safe checkpoint rollback model and covered by tests.
- Keep changes small, test-driven, and easy to inspect.

Verification standard:
- Add or update tests before implementation where practical.
- Run targeted tests for each slice.
- Run full suite before declaring done:
  PYTHONPATH=src python3 -m unittest discover -s tests -q
- Note that pytest/editable install may require a healthy Python toolchain; report environment blockers honestly.
- Clean generated __pycache__ and temporary files before final response.

Definition of done:
- The current MVP is consolidated and committed.
- README quickstart exists and works.
- devflow init/status/run/run --yes are documented and tested.
- Task claim/release/status exists and is tested.
- Canonical task templates/examples exist.
- Peer orchestrator team scaffolding exists.
- Reports are sufficiently auditable.
- Docs consistently describe peer orchestrators, task ownership, unified diffs, clean-worktree gating, explicit apply, checkpoint rollback, and best-effort plan mirroring.
- Full verification passes.

Stop conditions:
- Safety semantics become ambiguous around dirty worktrees, rollback, protected files, or ownership locks.
- Another active agent has claimed the same task or touched-file scope.
- The task requires irreversible git cleanup or destructive operations outside the checkpoint rollback model.
- Tests fail in a way unrelated to the current slice and require human triage.
```

## Operator Notes

Use this as the high-level goal for any IDE orchestrator. The first instruction after loading this goal should be: consolidate the current diff, verify it, and commit a stable checkpoint before adding new capabilities.
