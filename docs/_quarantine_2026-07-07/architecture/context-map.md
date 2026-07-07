# Context Map

Status: future architecture idea. This document does not enable autonomous
routing, non-local worker execution, hidden memory, automatic patching,
verification, promotion, merge, or push.

## Purpose

Context Map is a standalone read-only codebase orientation tool for answering:

```text
Where should I look, and why?
```

The goal is to reduce cold-start codebase scanning and stale-context mistakes
for coding agents without turning generated maps or memory notes into authority.

The tool should be usable by Codex, Hermes, Dev-Flow, or any MCP-compatible
client. The MCP server is an interface around the standalone core, not the
first implementation or the owner of the data model.

## V1 Identity

Context Map combines:

- current source indexes
- Graphify evidence
- root `CODE_MAP.md`
- active architecture and product docs
- selected Obsidian memory notes

It returns compact, cited orientation for a codebase task. It does not solve the
task, edit files, route workers, verify readiness, promote work, or silently
write durable vault notes.

## Relationship To Existing Layers

- `CODE_MAP.md` remains human-authored orientation.
- Graphify remains generated architecture evidence, not authority.
- Obsidian remains durable human-readable memory.
- Dev-Flow remains owner of task state, evidence, verification, and promotion.
- Hermes may call Context Map through MCP or CLI, but does not own the index.
- Codex may call Context Map through MCP or CLI, but does not own the index.
- Dev-Flow may ingest Context Map answers as task evidence, but does not own the
  standalone core.
- The future Context Agent Service may ask Context Map for source-backed map
  material, but the Context Agent remains a question-answering service rather
  than execution authority.

## Authority Order

When sources conflict, Context Map must rank evidence in this order:

1. Live source and tests win.
2. Active repo docs win over inactive docs.
3. `CODE_MAP.md` is trusted for orientation, but not behavior.
4. Fresh Graphify is trusted for graph evidence, not product truth.
5. Stale Graphify can only be returned with a warning.
6. Obsidian notes are memory and prior rationale, not current authority unless
   they point back to live source or active docs.
7. External articles and videos are inspiration only until checked against the
   actual repo.

## Persistent Index Location

The v1 executable index should be repo-local and vault-readable, not
vault-primary:

```text
<repo>/.context-map/
  index.json
  graphify-freshness.json
  source-index.json
  docs-index.json
  obsidian-links.json
```

The index belongs beside the repository it describes because freshness depends
on that repo's HEAD, ignored files, tests, source layout, and active docs.

Obsidian should receive optional human-readable summaries and rationale, for
example:

```text
/Users/jewelbait/Documents/Obsidian Vault/Handoffs/YYYY-MM-DD Context Map - <repo>.md
```

Obsidian is the review and memory surface, not the live index database for every
codebase.

## Freshness Contract

Every answer must return freshness metadata:

```yaml
freshness:
  repo_head: <current git sha>
  indexed_head: <sha used for source index>
  graphify_head: <sha used for graphify evidence>
  dirty_worktree: true|false
  stale:
    source_index: true|false
    graphify: true|false
    obsidian_links: true|false
```

If `source_index` is stale, Context Map may still answer, but it must set
`confidence: low` and include a `next_lookup` that uses live source search. If
Graphify alone is stale, the answer may still use live source and active docs
while marking only graph evidence as stale.

## Indexing Strategy

V1 should be structural and search-first.

Use:

- file paths
- imports
- symbol names
- Graphify nodes and edges
- `CODE_MAP.md` sections
- active doc headings
- Obsidian wikilinks and frontmatter
- `rg`, SQLite, or JSON indexes

Do not use embeddings in v1. Embeddings add operational complexity, stale-cache
ambiguity, and "sounds related" matches before deterministic lookup has been
proven insufficient. Embeddings can be a v2 experiment only after missed-query
evidence shows structural lookup is not enough.

## Implementation Home

Context Map should live in its own repository, not inside Dev-Flow, Hermes, or
the Obsidian vault:

```text
/Users/jewelbait/Desktop/context-map/
  src/context_map/
    core.py
    indexer.py
    orient.py
    trace.py
    blast_radius.py
    mcp_server.py
  tests/
  docs/
  pyproject.toml
```

Dev-Flow, Hermes, Codex, and other clients may call Context Map through the CLI
or later MCP server. Dev-Flow should dogfood Context Map against this repository
and may ingest its answers as task evidence, but Context Map's core code should
not live under `src/devflow/control_room/`.

## Runtime Choice

V1 should be Python-first with minimal dependencies.

Reasons:

- Dev-Flow, Hermes scripts, Graphify workflow, and local automation already lean
  Python.
- `rg`, Git, JSON, Markdown/frontmatter parsing, and subprocess Graphify calls
  are straightforward from Python.
- A Python MCP server can wrap the same core later.
- V1 should not depend on a Node app, desktop UI, database server, vector
  database, web app, or Obsidian plugin.

## Implementation Sequence

Build a repo-local CLI prototype before creating an MCP server:

```bash
context-map build --repo .
context-map orient "Where should I look to change task packet context packing?" --repo .
context-map trace src/devflow/control_room/task_packet.py --repo .
```

The CLI prototype must prove the output contract before MCP wrapping begins.

Prototype acceptance:

- `context-map build` writes `.context-map/*.json`.
- It detects current `HEAD` and dirty worktree state.
- It reads `CODE_MAP.md`.
- It reads active docs headings.
- It can ingest Graphify freshness when `graphify-out/` exists.
- It links relevant Obsidian notes by frontmatter, wikilink, or search.
- It returns compact cited answers with confidence and `next_lookup`.
- It performs no source edits and no vault writes.

## MCP-Start Gate

Start MCP creation only after the CLI passes a 10-query orientation benchmark
against Dev-Flow.

Required gate:

- `context-map build` completes and writes repo-local JSON indexes.
- `orient_task` answers 10 saved real questions.
- At least 8 of 10 answers point to the correct primary files and docs.
- 10 of 10 answers include freshness metadata.
- 10 of 10 answers include citations and `next_lookup`.
- 0 answers claim Graphify authority when stale.
- 0 answers write source, write vault notes, launch workers, verify, or promote.
- Human review marks the output useful enough to reduce cold-start scanning.

Initial Dev-Flow benchmark questions:

1. Where should I look to change task packet context packing?
2. Where should I look to change `CODE_MAP.md` validation?
3. Where should I look to change operating-layer task controls?
4. Where should I look to change Obsidian scout-pack preview/create?
5. Where should I look to change local-worker readiness display?
6. Trace `src/devflow/control_room/task_packet.py`.
7. Trace `src/devflow/control_room/code_map.py`.
8. Trace `src/devflow/control_room/obsidian_task_bridge.py`.
9. What is the blast radius of changing `task_packet.py`?
10. What is the blast radius of changing `operating_layer_server.py`?

## Shared Response Schema

All v1 commands and tools should return one JSON-compatible response shape:

```yaml
answer: short human-readable answer
primary_targets:
  - path: src/devflow/control_room/task_packet.py
    why: owns task packet assembly and rendering
sources:
  - path: CODE_MAP.md
    authority: orientation
    why: names task_packet.py as an entry point
graphify:
  status: fresh|stale|missing
  nodes: []
obsidian:
  notes: []
freshness:
  repo_head:
  indexed_head:
  graphify_head:
  dirty_worktree:
  stale:
    source_index:
    graphify:
    obsidian_links:
confidence: high|medium|low
next_lookup: rg or graphify command to verify live
refusals: []
```

The shared schema keeps CLI output testable and makes MCP wrapping mechanical.

## V1 Tool Set

### `orient_task`

Input: a task or question plus optional repository path.

Output:

- top source files to inspect
- active docs to read
- relevant Graphify nodes or paths
- relevant Obsidian notes
- known freshness and stale-context risks
- next lookup to run if confidence is low

Refuse or narrow:

- "Summarize the whole repo."
- "Find every possible bug."
- "Tell me what to build next."
- "Choose and run the best worker."
- "Update Obsidian with what you learned."
- "Verify this is complete."
- "Which model should handle this?"
- "Apply this patch."

When input is too broad or authority-bearing, return a narrowing prompt:

```text
orient_task needs a concrete task, subsystem, file, symbol, or patch summary.
Try: "Where should I look to change task packet context packing?"
```

### `trace_symbol`

Input: a symbol, file, or path.

Output:

- callers and callees
- imports and imported-by edges
- related tests
- related docs
- confidence and missing-context notes

### `review_blast_radius`

Input: changed files or a patch summary.

Output:

- likely affected source files
- likely affected tests
- related docs or contracts
- stale-context risks
- Graphify freshness caveats

## V1 Non-Goals

- no vault write tools
- no task creation tools
- no worker launch tools
- no verification or promotion tools
- no "summarize entire repository" tool
- no claim that Graphify output is current without freshness evidence
