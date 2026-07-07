# Local Worker Policy

Status: active pointer

The single source of truth for Codex session behavior, local-worker routing,
active fleet, Agent Proxy use, and freshness closeout is:

`/Users/jewelbait/.codex/session-operating-contract.md`

Use that contract for current local-worker policy. DevFlow-specific scripts
remain available where the contract or repo `AGENTS.md` routes to them:

```bash
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/compress_tool_output.py
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/extract_methods.py
python3 ~/.hermes/skills/software-development/local-fleet-efficiency/scripts/codebase_survey.py
```
