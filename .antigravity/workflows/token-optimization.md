# /token-optimization

Use this workflow to activate the Dev-Flow token optimization skill system, establish strict context discipline, and enforce token efficiency.

## Overview

This workflow is a thin wrapper that guides the active agent to enforce token optimization policies in Dev-Flow.

## Directives

1. **Follow Operating Rules**:
   - Strictly read and follow the active rules in [AGENTS.md](AGENTS.md).
   - Activate the canonical token-optimization meta-routing skill: [skills/token-optimization/SKILL.md](skills/token-optimization/SKILL.md).

2. **Load Target Subskills**:
   - Depending on your current action, load only the specific relevant subskills inside [skills/token-optimization/skills/](skills/token-optimization/skills/):
     - For code lookup: Use `search_before_reading.md`.
     - For state parsing: Use `summarize_before_expanding.md`.
     - For context boundary: Use `role_context_selection.md`.
     - For messaging/handoff: Use `transcript_bloat_prevention.md`.

3. **Context & Search Discipline**:
   - **Concise & Technical**: Keep all replies crisp and action-oriented. Do not repeat plans, rules, or code blocks in the transcript.
   - **No Broad Repo Scans**: Avoid broad repository scans unless the task is architecture-level. Read only the minimum context required.
   - **Search Before Reading**: Use targeted search utilities (`rg`, `grep_search`, symbol search, or other nearest search tools) before opening full files.
   - **Summarize Before Expanding**: Inspect lightweight summaries (`task.yaml`, `summary.json`, `events.jsonl`) and tail failure logs before parsing raw implementation files.

4. **Multi-Agent Coordination**:
   - **One Writer at a Time**: Respect that only one agent may modify files in the repository at a time.
   - **Clarify Roles**: If it is unclear whether you are currently the active writer or a reviewer, ask the user to clarify before making edits or staging/committing files.
