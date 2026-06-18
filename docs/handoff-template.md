# DevMode Handoff Template

Use this template to coordinate between agent sessions, shifts, or workers. Keep handoffs short enough to paste into a new chat without dragging the entire previous conversation forward.

Use a handoff at every major feature, milestone, or product-direction change after active docs are aligned, verification has run, and the tree has been committed/merged/pushed as requested.

The handoff should be useful to the human first and resumable by the next agent second. Do not hide the real outcome behind only a safety gate. Separate:

- what actually changed
- what is verified
- what is still unclear or risky
- what the human should probably do next
- the single safest action if another agent resumes cold

WARNING: stale context is harmful when it presents itself as current authority. Handoffs must call out remaining risks, but they must not preserve obsolete plans or conflicting product direction as casual background. Future architecture can be linked when relevant, but it should be labeled as roadmap/reference rather than active runtime behavior.

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
