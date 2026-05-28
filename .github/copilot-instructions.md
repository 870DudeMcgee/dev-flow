# DevMode Default

For all development work in this repository, operate in DevMode.

DevMode is the master engineering workflow for this repo. It combines:

- Superpowers execution discipline from `using-superpowers`
- Matt Pocock engineering skills when relevant
- repo-local token optimization
- Dev-Flow project rules and verification discipline

## Default DevMode Contract

When `/devmode` is invoked, output exactly one confirmation line:

```text
DevMode loaded: token optimization, repo discipline, read-only/implementation gating.
```

Then continue silently. Do not output a skills-used line.

Use Superpowers-style disciplined execution by default:

- clarify the task type
- inspect only necessary context
- make a small plan when useful
- execute one small vertical slice
- verify before claiming success
- report concise evidence

Use token optimization at all times as a mandatory budget discipline:

- search before broad reads
- inspect only files needed for the task
- read targeted sections before whole files
- summarize before expanding
- avoid repeated context
- avoid repeated summaries and ceremonial output
- do not load unrelated skills, workflows, or docs
- do not create handoff docs unless explicitly requested
- do not run extra checks beyond the requested or narrowest meaningful checks
- do not run ruff
- do not scan the whole repo unless needed

## Read-Only / Implementation Gate

Classify mode before acting:

- Read-only prompts include audit, review, investigate, explain, plan, summarize, or unclear write permission. Do not edit, stage, commit, or create files.
- Implementation prompts include fix, build, update, apply, or explicit permission to edit. Edit only relevant files, run targeted verification, and commit only when explicitly requested or permitted and verification passes.

If write permission is ambiguous, ask one blocking question or stay read-only.

## Repo Guardrails

- Follow [AGENTS.md](../AGENTS.md) as the repo-level operating rule.
- Read [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md) before implementation decisions and check the Periodic Self-Check section.
- Read [docs/control-room-mvp.md](../docs/control-room-mvp.md) before non-trivial code changes.
- Keep the first milestone focused on shell workers only.
- Do not use archived legacy workflows as process authority.
- Do not implement Aider, Hermes, OpenCode, memory, complex scheduling, or model routing yet.
- Do not add dashboard/web servers, databases, merge automation, or PR automation unless the current task explicitly requires them.

## Skill Routing

Do not invoke every skill automatically. Route deliberately:

- Use `using-superpowers` as the baseline development discipline.
- Use `improve-codebase-architecture` for architecture, refactor, coupling, module boundaries, or codebase health.
- Use `grill-with-docs` for checking plans, specs, docs, assumptions, and implementation alignment.
- Use `caveman` when a solution is overbuilt, clever, abstract, or too complex.
- Use `token-optimization` when context size, repeated reads, or transcript bloat are a risk.

If a skill, prompt, custom agent, or workflow is not clearly needed, do not call it.

## Dev-Flow Project Rules

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

Use this format unless the user asks otherwise:

Decision:
Files changed:
Verification:
Risks:
Next safe action:
