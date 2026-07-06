# Agent Operating Contract

Status: active
Date: 2026-07-06
Related: [AGENTS.md](../../AGENTS.md), [ADR 0002](../adr/0002-repo-loop-cockpit-over-hermes-runtime.md), [fleet-contract.json](../../.devflow/fleet-contract.json)

## Purpose

This is the hot context layer — always loaded, concise, authoritative. It
defines the scout-first context supply chain that governs how the frontier
agent interacts with the codebase, local fleet, and evidence system.

Research basis: [Anthropic multi-agent research](https://www.anthropic.com/engineering/multi-agent-research-system),
[Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents),
[Chroma context rot](https://research.trychroma.com/context-rot),
[SWE-agent ACI](https://proceedings.neurips.cc/paper_files/paper/2024/file/5a7c947568c1b1328ccc5230172e1e7c-Paper-Conference.pdf),
[Codified Context](https://arxiv.org/html/2602.20478v1).

## Core Principle

> **The frontier model should not "map first." The system should "scout first."**

Mapping, search, file reading, and compression are scout responsibilities. The
frontier receives a compact scout packet — including symbols, imports, module
structure — and makes routing decisions from that packet alone.

The goal is the smallest high-signal context that maximizes decision quality.
Long context degrades attention even when it fits the window (context rot).

The scout is a **context firewall**: it burns the messy tokens and returns a
compact, structured artifact the frontier can route from without reading raw
source files.

## Authority Order

1. This contract (hot context)
2. AGENTS.md (workflow and fleet routing)
3. Named handoff/plan (task-specific)
4. Scout packet (codebase evidence)
5. Specialist skills (warm context, loaded when relevant)
6. Cold docs (retrieved by scout, not blindly loaded)

## Frontier Agent Role

The frontier agent interprets intent, dispatches scout, chooses route, approves
bounded implementation, verifies evidence, and communicates with the user.

### Allowed before scout

- Read user prompt
- Read named handoff/plan
- Load relevant skill
- Read this contract
- Inspect git status / live state if needed
- At most two targeted file reads/searches for orientation

### Not allowed before scout

- Broad repository search
- Multiple source file reads
- Implementation / file edits
- Builder/judge dispatch
- Commit

### Manual read/search budget

```text
manual_frontier_reads_allowed_before_scout = 2
```

After two file reads or searches, the frontier must request or produce a scout
packet. This budget is machine-enforced by the `devflow agent preflight`
receipt.

## Scout Lane

The scout owns mapping, search, file reads, compression, and freshness
checks. It returns a compact orientation packet. No edits. No commits.

The scout also owns **context extraction**: it reads the Context Map source
index and returns per-file symbols, imports, module structure, and headings
in the `context_brief` field. The frontier reads this instead of raw source.

Dirty worktree state is **never** used as implementation scope by itself. If
no handoff, task record, referenced files, or explicit `--file-to-touch` are
provided, the scout returns `recommended_lane=ask_user` with empty
`files_to_touch` and a blocked verification message.

Generated artifacts (`.context-map/*`, `.devflow/*`) are evidence, not
implementation targets.

### Scout tools

- Agent Proxy `codebase_search` (when indexed, pass `project=<agent_proxy_project>`)
- Context Map `orient` / `build_index` (pass `repo=<repo_root>`)
- `search_files` / `read_file` (scout only, not frontier)
- `compress_tool_output.py`
- `codebase_survey.py`
- `extract_methods.py`
- Graphify freshness checks
- Context Map source index (for `context_brief` extraction)

### ScoutPacket JSON schema

```json
{
  "task_id": "string",
  "map_source": "context_map | agent_proxy | source_search",
  "map_freshness": {
    "source_index": "ok | stale | missing | unreadable | empty",
    "graphify": "present | stale | missing | unreadable",
    "confidence": "high | medium | low"
  },
  "files_to_touch": ["path/to/file.py"],
  "files_to_read_next": [
    {
      "path": "path/to/file.py",
      "reason": "why this file matters"
    }
  ],
  "tests": ["tests/test_file.py"],
  "risks": ["risk description"],
  "recommended_lane": "direct_tiny_edit | deterministic_tool | builder | judge | ask_user",
  "verification": "local_test_runner.py --pytest ... --ruff ...",
  "evidence_paths": [".devflow/evidence/scout-<task_id>.json"],
  "context_brief": [
    {
      "path": "src/devflow/control_room/scout.py",
      "kind": "module",
      "module": "devflow.control_room.scout",
      "symbols": [
        {"name": "RepoScout", "type": "class", "line": "16"},
        {"name": "get_changed_files", "type": "method", "line": "46"}
      ],
      "imports": ["subprocess", "pathlib.Path"],
      "headings": []
    }
  ]
}
```

The scout writes its packet to `.devflow/evidence/scout-<task_id>.json`.

A scout packet is **actionable** only if:
- `recommended_lane != "ask_user"`
- `files_to_touch` is non-empty

A blocked scout packet (`ask_user` or empty files) does **not** open the edit
gate, even if it exists on disk.

## Route Table

The frontier may only choose a route after reading the scout packet.

| Trigger | Scout focus | Likely lane |
|---|---|---|
| Pipeline run / snapshot | `operating_layer.py`, `pipeline_run.py`, snapshot builders | Direct edit or builder |
| Module function extraction | `extract_module.py` (deterministic) | Deterministic tool — no builder/judge |
| Large file understanding | `compress_tool_output.py` or `codebase_survey.py` | Compression lane |
| UI change | UI scout + browser validation | Builder + visual QA |
| Post-change review | Judge/reviewer lane | Qwen 27B judge |
| Docs-only cleanup | Scout for stale phrases, then edit | Direct edit |

## Builder Lane

Receives: scout packet, exact writable files, acceptance criteria,
verification command.

Does not receive: entire repo, broad handoff history, unrelated docs.

Builder/judge is forbidden without scout/map evidence naming:

- target files
- scope
- risks
- verification command

## Judge Lane

Receives: scout packet, diff, test result summary.

Does not redo full mapping unless asked.

## Verifier

Uses `local_test_runner.py` — no raw pytest/ruff unless wrapper unavailable and
explicitly recorded.

`devflow agent verify --task <id> --json` runs the verification command from
the scout packet and writes a verification receipt to
`.devflow/evidence/verify-<task_id>.json`.

## Preflight Receipt

`devflow agent preflight --task <id> --json` writes:

```json
{
  "handoff_read": true,
  "skills_loaded": ["local-fleet-efficiency"],
  "scout_required": true,
  "scout_packet_exists": false,
  "scout_packet_actionable": false,
  "scout_packet_status": "missing",
  "scout_recommended_lane": null,
  "repo_root": "/absolute/path/to/repo",
  "agent_proxy_indexed": true,
  "agent_proxy_project": "Users-jewelbait-Desktop-Local-AI-Dev-Team",
  "agent_proxy_status": "ok",
  "context_map_available": true,
  "context_map_source_index": "ok",
  "mapping_tools_ready": true,
  "context_map_hint": "mcp_context_map_orient(..., repo='/absolute/path')",
  "agent_proxy_hint": "mcp_agent_proxy_codebase_search(..., project='project-name')",
  "fleet_state_captured": true,
  "allowed_to_edit": false,
  "next_action": "run devflow agent scout --task <id>"
}
```

After an actionable scout packet exists with mapping tools ready:

```json
{
  "scout_packet_exists": true,
  "scout_packet_actionable": true,
  "scout_packet_status": "actionable",
  "mapping_tools_ready": true,
  "allowed_to_edit": true,
  "next_action": "route implementation with scout evidence"
}
```

If mapping tools are not ready, `allowed_to_edit` stays `false` even if a
scout packet exists, and `next_action` is `"repair repo map indexes before
scout"`.

If the scout packet exists but is not actionable (blocked/ask_user),
`allowed_to_edit` stays `false` and `next_action` is `"provide scoped handoff
or explicit file scope before editing"`.

Tools or policy can check this receipt mechanically.

## Context Tiers

### Hot context (always loaded, tiny)

This file. Rules, routing, authority order, violation behavior.

### Warm context (specialist skills)

Loaded only when relevant:

- `local-fleet-efficiency`
- `devflow-analysis`
- `mcp-workflow-design`
- `github-pr-workflow`

### Cold context (detailed docs)

Retrieved by scout, not blindly loaded:

- Fleet history and ADRs
- Integration docs
- Old handoffs
- Architecture baseline docs

## Drift Detection

Stale specs cause silent failures. The active fleet contract is
`.devflow/fleet-contract.json` — only Ornith 35B (:8084, builder/scout) and
Qwen 27B (:8083, judge) are active. Ornith 9B, Qwopus, and Qwen3-Coder-Next
are retired.

Any doc that references retired models or wrong ports as active must be
marked historical or fixed.

## Violation Behavior

If the frontier agent skips preflight or scout:

1. Stop immediately
2. State the missed step
3. Do not commit
4. Wait for or perform the corrective preflight/scout before continuing
5. Record as a severity-10 workflow failure
