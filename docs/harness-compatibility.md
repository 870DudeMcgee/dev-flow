# Harness Compatibility Matrix

This document provides a compatibility matrix for DevMode integration across various AI development environments and harnesses.

| AI Harness / IDE | Support Status | Configuration Files | Automatic Discovery | Notes |
|---|---|---|---|---|
| **Claude Code** | supported | `.claude-plugin/plugin.json`, `skills/` | yes | Full custom skill auto-discovery via symlinks |
| **Gemini CLI** | supported | `gemini-extension.json`, `GEMINI.md` | yes | Autoloads context prompt on bootstrap |
| **Cursor** | supported | `skills/using-devmode/SKILL.md` | yes | Configured as custom system prompt instructions |
| **Codex** | supported | `.codex-plugin/` | yes | Auto-discovered from installed plugin directory |
| **OpenCode** | supported | `.opencode/` | yes | Custom bootstrap loader config |
| **VS Code / GitHub Copilot** | documented / experimental | `.github/copilot-instructions.md`, `.github/instructions/`, `.github/prompts/` | not yet captured unless manually verified | Support depends on Copilot client/version; instructions are guidance, not guaranteed behavior |
