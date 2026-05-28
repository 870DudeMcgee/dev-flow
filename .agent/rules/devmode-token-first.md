# DevMode Token-First Rule

For all development work in this workspace, operate in DevMode.

DevMode means: spend the fewest useful tokens, read the least necessary context, make the smallest safe change, and verify before claiming success.

## Default Behavior

* Be concise.
* Do not explain obvious steps.
* Do not narrate every tool call.
* Search before reading large files.
* Read targeted sections before whole files.
* Prefer one small vertical slice over broad rewrites.
* Do not run architecture review, codebase review, documentation grilling, or simplification rituals unless the task actually needs them.
* Do not load or invoke multiple skills/workflows by default.
* Ask only blocking questions.
* If a reasonable assumption can be made safely, make it and state it briefly.
* Before editing, check relevant repo state when appropriate.
* After editing, run the narrowest meaningful verification command.
* Never claim completion without evidence.

## Skill/Workflow Budget

Default budget: no extra skills.

Use extra workflows only when the task clearly matches:

* Architecture/design/refactor boundaries: architecture review.
* Validating against docs/specs: docs grill.
* Overbuilt or clever implementation: caveman simplification.
* Large context risk: token optimization.
* Normal coding task: DevMode only.

If a skill or workflow is not clearly needed, do not call it.

## Output Format

Use this format unless the user asks otherwise:

Decision:
Files inspected:
Files changed:
Verification:
Risks:
Next safe action:
