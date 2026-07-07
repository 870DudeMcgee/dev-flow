# DevMode Handoff Template

Use this template only when the human explicitly asks for a handoff or when an
existing workflow command requires one. Do not create handoff docs by default;
update existing authority docs or report continuation state in the final
response instead.

For major feature, milestone, or product-direction changes, align active docs
and verification first. Create a handoff only when requested; otherwise keep
the continuation notes in the final response and existing task/state artifacts.

The handoff should be useful to the human first and resumable by the next agent second. Do not hide the real outcome behind only a safety gate. Separate:

- what actually changed
- what is verified
- what is still unclear or risky
- what the human should probably do next
- the single safest action if another agent resumes cold

WARNING: stale context is harmful when it presents itself as current authority. Handoffs must call out remaining risks, but they must not preserve obsolete plans or conflicting product direction as casual background. Future architecture can be linked when relevant, but it should be labeled as roadmap/reference rather than active runtime behavior.

Handoffs provide task-specific details only. They must not override
orientation-first workflow, duplicate fleet routing, or tell agents to bypass
Context Map, Agent Proxy, scout packets, local worker routing, or verification.

## Status

[complete | in-progress | blocked | needs-review | failed]

## Outcome

- What was actually accomplished in plain language.
- What is intentionally not included or not finished.
- Any important state the user would otherwise have to infer from logs.

## Files Changed

- path/to/file (what changed)

## Verification

- `command run`: pass/fail + actual output logs

## Risks

- Specific technical risks, limitations, or potential side-effects

## Recommended Next Steps

- Best next move for the human or project, stated plainly.
- Follow-up actions in priority order when there is more than one useful next move.
- Do not dump a broad backlog; include only steps that are relevant because of this work.

## Next Safe Action

- The single safest concrete action for a fresh agent or operator to take if they must resume from this handoff.
- This may match the best recommended step, but it does not have to. When they differ, explain why in one sentence.
