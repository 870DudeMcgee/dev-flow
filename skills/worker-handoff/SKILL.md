---
name: worker-handoff
description: Use when completing work, switching agents, or passing task state between workers — requires structured status, evidence, and next-action before any handoff claim
---

# Worker Handoff

## Overview

Handoffs fail when context is lost. A handoff without evidence is a handoff that wastes the next agent's time re-investigating.

**Core principle:** Every handoff must include status, outcome, evidence, useful next steps, and the safest cold-resume action. No exceptions.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO HANDOFF WITHOUT STATUS, OUTCOME, EVIDENCE, AND NEXT ACTIONS
```

If you haven't included all of them, your handoff is incomplete.

## Required Handoff Format

```markdown
## Status

[complete | in-progress | blocked | needs-review | failed]

## Outcome

- What was actually accomplished in plain language
- What is intentionally not included or not finished
- Important state the user would otherwise have to infer from logs

## Files Changed

- path/to/file (what changed and why)

## Verification

- `command run`: pass/fail + brief result
- (If verification cannot run, say exactly why)

## Risks

- Known issues, limitations, or things that might break
- (If no risks, say "None identified" — don't leave blank)

## Recommended Next Steps

- Best next move for the human or project
- Follow-up actions in priority order when there is more than one useful next move
- Keep this relevant to the work just handed off, not a broad backlog

## Next Safe Action

- The single safest thing a receiving agent should do if resuming cold
- (Must be specific and actionable, not "continue working")
```

## When to Produce a Handoff

**Required:**
- Switching to a different agent or worker
- Completing a task
- Getting blocked and need escalation
- Session ending with work in progress
- Worker failed and needs rescue

**Not required:**
- Continuing work in the same session
- Unless explicitly asked by the user
- (Token budget: don't create docs nobody asked for)

## Receiving a Handoff

```
BEFORE accepting a handoff:

1. READ the status — is work actually done?
2. CHECK verification — were commands actually run?
3. INSPECT risks — anything that changes your plan?
4. READ Recommended Next Steps — understand the useful project direction
5. START with the Next Safe Action when resuming cold — don't re-investigate from scratch
```

**Red flags in received handoffs:**
- Empty Verification section → don't trust the status
- "Everything works" without commands → verify independently
- Missing Outcome section → ask what actually changed before acting
- Missing Recommended Next Steps → ask what the useful follow-up is
- Vague Next Safe Action → ask for specifics before proceeding
- Missing Risks section → assume there are risks you don't know about

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "It's obvious what to do next" | Not to the next agent. Write it. |
| "I'll remember the context" | You won't. The next agent definitely won't. |
| "No time for a handoff" | 30 seconds now saves 10 minutes of re-investigation. |
| "No risks" | There are always risks. State them or say "None identified." |
| "The code speaks for itself" | Code doesn't explain decisions, trade-offs, or what was tried. |
| "I'll just finish later" | You might not. Leave a handoff. |
| "It's almost done" | "Almost" is the most dangerous status. Document what's left. |

## Red Flags — STOP

- Handoff with empty Verification section
- "Everything works" without verification commands
- Status says "complete" but no verification was run
- Missing Next Safe Action
- Missing Recommended Next Steps
- Missing Outcome section
- Missing Files Changed section
- Status says "in-progress" but no explanation of what's left
- About to end session without handoff for incomplete work

**All of these mean: Fix the handoff before sending it.**

## Common Handoff Mistakes

| Mistake | Fix |
|---------|-----|
| "Done" without verification | Run verification commands, report results |
| Vague next action: "keep working" | Specific: "Run `pytest tests/test_cli.py` to verify the fix" |
| Missing risks | Think: what could go wrong? What assumptions did you make? |
| No files listed | `git diff --name-only` shows what changed |
| Status inflation ("complete" when blocked) | Be honest. "blocked" is a valid status. |

## Integration

- Pairs with `devmode:verification-before-completion` — verify before claiming done
- Pairs with `devmode:workspace-isolation` — report workspace boundaries in handoff
- Pairs with `devmode:finishing-a-development-branch` — final handoff at merge time

## The Bottom Line

**A good handoff takes 30 seconds. A missing handoff wastes 10 minutes.**

Status. Evidence. Next action. Every time.
