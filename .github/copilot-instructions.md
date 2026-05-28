# DevMode Default

For all development work in this repository, operate in DevMode.

DevMode is the master engineering workflow for this repo. It combines:

- Superpowers execution discipline from `using-superpowers`
- Matt Pocock engineering skills when relevant
- repo-local token optimization
- Dev-Flow project rules and verification discipline

## Default DevMode Contract

Use Superpowers-style disciplined execution by default:

- clarify the task type
- inspect only necessary context
- make a small plan when useful
- execute one small vertical slice
- verify before claiming success
- report concise evidence

Use token optimization at all times:

- search before broad reads
- read targeted sections before whole files
- summarize before expanding
- avoid repeated context
- do not load unrelated skills or docs

## Repo Guardrails

- Follow [AGENTS.md](../AGENTS.md) as the repo-level operating rule.
- Read [PRODUCT_NORTH_STAR.md](../PRODUCT_NORTH_STAR.md) before implementation decisions and check the Periodic Self-Check section.
- Read [docs/control-room-mvp.md](../docs/control-room-mvp.md) before non-trivial code changes.
- Keep the first milestone focused on shell workers only.
- Do not use archived legacy workflows as process authority.
- Do not implement Aider, Hermes, OpenCode, memory, complex scheduling, or model routing yet.

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

## Output Format

Use this format unless the user asks otherwise:

Decision:
Files inspected:
Files changed:
Verification:
Risks:
Next safe action:
