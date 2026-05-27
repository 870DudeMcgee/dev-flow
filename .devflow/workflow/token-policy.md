# Devflow Token Policy

## Rule 1: Search before reading

Use targeted search (ripgrep, symbol search) before opening full files.
Never read an entire file when a search result would suffice.

## Rule 2: Summarize before expanding

Read summaries first, in this order:

1. Repo map (`.devflow/context/repo-map.short.md`)
2. Task packet
3. Symbol map
4. Failure summary

Only expand to full files when the summary is insufficient.

## Rule 3: Role-specific context

Each role receives only what it needs:

| Role | Context |
|------|---------|
| **Planner** | Goal, repo summary, constraints |
| **Implementer** | Task packet, relevant files, relevant tests |
| **Tester** | Task packet, implementation files, test fixtures |
| **Reviewer** | Task packet, final diff, verification result |
| **Repair** | Latest failure, current diff, touched files only |

Use `devflow context build <task> --role <role>` to generate bounded context packs.

## Rule 4: No transcript bloat

- Do not restate full plans repeatedly.
- Do not paste unchanged files.
- Do not quote long logs when a summary is enough.
- Do not include full diffs unless requested.
- Do not produce large plans for tiny edits.
- Do not include long explanations in code-edit responses.
- Do not repeat unchanged code.

## Rule 5: Compress between phases

After each workflow phase, produce a short artifact summary:

- Decisions made
- Files involved
- Risks identified
- Next action

This summary becomes the handoff to the next phase, not the full transcript.
