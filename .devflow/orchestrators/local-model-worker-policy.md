# Local Model Worker Policy

Local models are worker subagents for peer orchestrators.

They may help with:

- patch drafting
- test generation
- failure explanation
- small repair loops
- summarization

They must not mutate repo state directly.

All local-model outputs should flow back through an orchestrator, then through task files, unified diffs, verification, and reports.

Current preferred endpoint:

- http://127.0.0.1:11434

Candidate models:

- qwen2.5-coder:1.5b
- qwen2.5-coder:7b-instruct
- qwen2.5-coder:32b-instruct
