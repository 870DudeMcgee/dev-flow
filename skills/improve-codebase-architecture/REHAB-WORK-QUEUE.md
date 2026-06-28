# Rehab Work Queue

Use this file as the template for Graphify-backed architecture slice packets. Keep the durable queue in the target repo, not inside this skill package, unless the skill itself is being tested.

## Candidate Packet Template

```markdown
## Candidate: <short name>

Recommendation: Strong | Worth exploring | Speculative

Module goal:
<one sentence naming the module and desired depth/locality gain>

Graphify evidence:
- Report commit:
- Scorecard:
- Node IDs:
- Hotspot/delta:
- Diagnostics:

Source evidence:
- <file>: <what was verified>
- <test>: <current coverage or gap>

Ponytail gate:
- Existing code reused/deleted:
- Deletion test:
- Seam test:
- Slice size:

Implementation slice:
1. <smallest behavior-preserving step>
2. <focused test>
3. <after scorecard>

Conflict map:
- Files touched:
- Cannot run in parallel with:

Verification:
```bash
<focused test command>
python skills/improve-codebase-architecture/scripts/graphify_rehab_score.py --repo . --baseline <before.json>
```

Risks:
- <real risk or none>

Next safe action:
<single command or decision>
```

## Queue Rules

- Unlimited capture is fine; active execution is constrained.
- Promote only one candidate into a loop at a time unless worktrees isolate file overlap.
- Keep stale candidates marked stale instead of deleting useful future context.
- A packet without Graphify evidence and source evidence is an idea, not a ready slice.
