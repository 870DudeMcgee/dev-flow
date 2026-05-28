---
name: token-optimization
description: "Use when starting any Dev-Flow task to select context strategy, role bounding, or transcript compression."
argument-hint: "Describe your current intent (e.g., searching, loading task summaries, bounding context, handing off)"
user-invocable: true
---

# Dev-Flow Token Optimization Meta-Router

This skill is a **meta-skill router**. When invoked, assess your current activity and immediately delegate to the appropriate subskill:

## Routing Table

Depending on your immediate intent, read and follow the instructions in the specified subskill file:

| Activity / Intent | Subskill File | Primary Guidance |
| :--- | :--- | :--- |
| Searching for code patterns, symbols, or references | [search_before_reading.md](file:///Users/jewelbait/Desktop/Local%20AI%20Dev%20Team/skills/token-optimization/skills/search_before_reading.md) | Enforce grep-first and symbol-first lookups over full-file reads |
| Gathering task state, logs, or command results | [summarize_before_expanding.md](file:///Users/jewelbait/Desktop/Local%20AI%20Dev%20Team/skills/token-optimization/skills/summarize_before_expanding.md) | Check YAML, JSON, and append-only event files before parsing source code |
| Aligning your workspace access with your current role | [role_context_selection.md](file:///Users/jewelbait/Desktop/Local%20AI%20Dev%20Team/skills/token-optimization/skills/role_context_selection.md) | Set up strict boundary boxes for Planner, Writer, Reviewer, or Debugger roles |
| Preparing replies, plans, code patches, or handoff notes | [transcript_bloat_prevention.md](file:///Users/jewelbait/Desktop/Local%20AI%20Dev%20Team/skills/token-optimization/skills/transcript_bloat_prevention.md) | Minimize transcript footprint, avoid redundant dumps, use handoff template |

## Context Reference
* Canonical Guidelines: [docs/token-optimization.md](file:///Users/jewelbait/Desktop/Local%20AI%20Dev%20Team/docs/token-optimization.md)
* Handoff Template: [docs/handoff-template.md](file:///Users/jewelbait/Desktop/Local%20AI%20Dev%20Team/docs/handoff-template.md)
