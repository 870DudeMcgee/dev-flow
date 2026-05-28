# Subskill: Transcript Bloat Prevention

This subskill governs how to write clean, concise, and lightweight messages and artifacts to preserve tokens.

## Guidelines

1. **Be Concise and Professional**: Avoid filler words, overly-long pleasantries, and repeating unchanged plans or rules.
2. **Never Paste Unchanged Code**: When modifying a file, specify precise replacements (`replace_file_content` or `multi_replace_file_content` chunks) with minimal lines. Avoid reading or rewriting the entire file.
3. **Summarize Terminal Outputs**: If a command produces long logs, list only the critical lines (e.g., matching failures or the run command and concise success status).
4. **Use Handoff Templates**: Always wrap up your task or role swap using the lightweight format specified in [docs/handoff-template.md](file:///Users/jewelbait/Desktop/Local%20AI%20Dev%20Team/docs/handoff-template.md).
5. **No Redundant Plan Restatements**: Once a plan or walkthrough is written as a markdown file, do not copy-paste or re-summarize its contents in the chat transcript. Let the file act as the single source of truth.
