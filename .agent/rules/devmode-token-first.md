# DevMode Rule

For all development work in this workspace, operate in DevMode.

DevMode is the master engineering workflow for this repo. It combines Superpowers execution discipline, Matt Pocock engineering skills, token optimization as a budget discipline, and Dev-Flow project rules.

## Default DevMode Contract

Use Superpowers-style disciplined execution by default:

- clarify the task type
- inspect only necessary context
- make a small plan when useful
- execute one small vertical slice
- verify before claiming success
- report concise evidence

Use token optimization at all times as a budget discipline:

- search before broad reads
- read targeted sections before whole files
- summarize before expanding
- avoid repeated context
- do not load unrelated skills, workflows, or docs
- stop when the next safe action is obvious

## Skill Routing

Do not invoke every skill automatically.

Route deliberately:

- Use `using-superpowers` as the baseline development discipline.
- Use `improve-codebase-architecture` for architecture, refactor, coupling, module boundaries, codebase health, or AI-navigability.
- Use `grill-with-docs` for checking plans, specs, docs, assumptions, and implementation alignment.
- Use `caveman` when a solution is overbuilt, clever, abstract, or too complex.
- Use `token-optimization` when context size, repeated reads, or transcript bloat are a risk.

If a task does not clearly need a sub-skill, do not load it.

## Dev-Flow Project Rules

- Dev-Flow is a local-first control-room kernel, not a coding-agent wrapper.
- Agents are replaceable; state is sacred.
- Visibility is mandatory.
- Isolation comes before autonomy.
- Verification belongs to Dev-Flow.
- Humans control promotion to main.
- Prefer small vertical slices.
- Do not implement future architecture unless the milestone requires it.
- Do not claim success without evidence.

## Silent Work Mode

Run DevMode silently.

Use Superpowers, Matt Pocock skills, token optimization, and Dev-Flow rules internally. Do not narrate the workflow.

Do not produce progress narration unless the user explicitly asks for a live walkthrough.

Avoid phrases like:

- "I'll..."
- "I'm going to..."
- "I'm reading..."
- "I'm checking..."
- "Let me..."
- "Good..."
- "Actually..."
- "Now I..."
- "Starting..."
- "Completed..."
- "The plan is..."

Only speak when:

- asking a blocking question
- reporting the final result
- reporting a verification failure
- reporting a risk that changes the next safe action

## Output Format

Report only after the work is done. Use this format:

Decision:
Skills used:
Files changed:
Verification:
Risks:
Next safe action:
