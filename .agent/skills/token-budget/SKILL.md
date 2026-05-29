---
name: token-budget
description: Use when context is growing, reads are repeating, transcripts are bloating, or you're about to scan a whole repo — enforces token-efficient investigation before any broad context gathering
---

# Token Budget

## Overview

Tokens cost money. Wasted context costs time. Broad reads are the #1 source of wasted tokens in agent sessions.

**Core principle:** Search before you read. Read sections before files. Read files before directories. Never read what you've already read.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO BROAD READS WITHOUT TARGETED SEARCH FIRST
```

If you haven't searched for the specific term, function, or pattern, you cannot read the full file.

## The Decision Tree

```
BEFORE reading any file:

1. SEARCH: grep/search for the specific term, function, or pattern
2. TARGETED: Read only the matching lines + surrounding context (50-100 lines)
3. SECTION: If needed, expand to a section of the file
4. FULL FILE: Only if the above three were insufficient AND you can explain why
5. NEVER: Read multiple full files to "understand the codebase"

Skip any step = wasting tokens
```

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "I need to understand the whole codebase" | No you don't. Search for what's relevant. |
| "Let me read the full file for context" | Read the section around your search hit. |
| "I should check all related files" | Check one. Then decide if you need more. |
| "I'll scan the repo structure first" | List the directory. Don't read every file. |
| "I need to re-read this file" | You already read it. Use what you learned. |
| "Let me check the tests too" | Only if the task involves tests. |
| "Context is cheap" | Context costs tokens. Tokens cost money. |
| "Being thorough is good" | Being efficient is better. Thoroughness ≠ reading everything. |
| "I want to make sure I'm not missing something" | Missing context you searched for is fine. Missing context you didn't search for is a problem. Search. |

## Red Flags — STOP

If you're about to:

- Read a file you've already read this session
- List more than 2 directories before starting work
- Read more than 3 full files before making a change
- Produce a summary that repeats earlier output
- Write a handoff doc nobody asked for
- Re-explain something you already said

**STOP. You're burning tokens. Cut to the action.**

## Transcript Hygiene

- Don't repeat file contents in responses
- Don't summarize what you just showed
- Don't produce ceremonial output (progress narration, skill-loading announcements)
- Don't create handoff docs unless explicitly requested
- Don't run extra checks beyond the requested or narrowest meaningful checks
- Stop when the next action is obvious

## When Broad Reads Are Justified

Sometimes you genuinely need to read a full file:

- The file is the primary target of your edit
- The file is small (<100 lines) and you need the whole thing
- You searched and the results show the entire file is relevant
- The user explicitly asked you to read the file

In these cases, read it once. Don't re-read it.

## Integration

Every other DevMode skill should be token-aware. This skill is the reference standard.

**Skills that especially benefit:**
- `devmode:brainstorming` — explore with searches, not full reads
- `devmode:systematic-debugging` — trace from error, don't read the whole codebase
- `devmode:subagent-driven-development` — provide subagents with exactly what they need, not everything
- `devmode:writing-plans` — plan which files to touch, don't pre-read them all

## Verification

Before completing any task, check: "Did I read more than I needed to?" If yes, note it for next time.

## The Bottom Line

**Search first. Read less. Work more.**

The best agent session is one where the minimum context was loaded and the maximum work was done.
