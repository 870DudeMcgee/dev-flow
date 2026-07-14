# SubAgent Rulebook

Status: active; global Codex rulebook

Authority: subordinate to the global
[`session-operating-contract.md`](/Users/jewelbait/.codex/session-operating-contract.md)
and the active repository's `AGENTS.md`. Follow the higher authority and report
conflicts.

## Outcome

Codex delegates one grounded, independently verifiable result at a time. The
worker gets the live evidence and exact capabilities it needs—no less and no
unrelated toolbox. The supervisor owns routing truth, integration, verification,
cost, and the final answer.

Default cost policy: use the cheapest capable free worker route first. Native
Luna is a fallback after the free retry budget is exhausted, not a prerequisite
for beginning or continuing free work.

## Non-negotiable rules

1. Orient before dispatch; inspect the active authority and worktree state.
2. Select the actual worker surface. Native Codex, configured local lanes,
   native Hermes delegation, and the standalone HY3 adapter are not aliases.
3. Use capability-minimal workers. `TOOLS_REQUIRED NONE` is valid only for a
   purely textual task whose complete evidence is supplied verbatim.
4. One packet owns one observable behavior/state transition, coherent ownership
   boundary, acceptance contract, and validator or evidence criterion.
5. Give exact current paths, symbols, signatures, references, file states, and
   acceptance conditions. Permit `NEED_CONTEXT`; never reward API invention.
6. Preserve packet newlines, code, JSON, and anchors through the transport.
7. A named provider/model was used only when the dispatch surface can select it
   and returned evidence proves it. Configuration text is not execution proof.
8. A terminal result is evidence, not authority. The supervisor checks current
   source, diffs, receipts, tool traces, and deterministic verification.
9. Report dispatch failure, capability mismatch, retry, fallback, partial
   output, and unresolved risk. Never silently change route or cost class.

## Route selection

Capability requirements outrank receipt convenience.

| Need | Route | Capability boundary |
| --- | --- | --- |
| Default tool-using cloud worker | HY3-free through native Hermes `delegate_task` | Exact task toolsets; optional verified `worker_lane` |
| Default durable synthesis from supplied text | Standalone HY3-first adapter with ordered OpenRouter `:free` fallbacks | No tools; one turn per provider; receipt required |
| Read-only complex local scout | Verified configured Ornith custom agent, when present | Live configured read-only boundary |
| Bounded local implementation | Verified configured Ornith custom agent, when present | Owned edits plus exact checks |
| Spec/planning/research synthesis | Configured Agents-A1 Q4 lane | No silent native-agent substitution |
| Independent judge | Configured Qwen 27B lane | Runs after implementation; no edit ownership |
| Final cloud fallback after free exhaustion | Native Codex custom agent `luna`, pinned to `gpt-5.6-luna` | Parent Codex tools/permissions plus Luna packet instructions |
| Native Codex work explicitly authorized by user/repo/skill | Codex `default`, `worker`, `explorer`, or verified custom agent | Only controls exposed by that surface |

An unavailable downstream fallback never blocks an available free route. Do not
preflight Luna before dispatching free work, terminate free workers because
Luna is absent, or discard valid free-worker progress. `luna` is native Codex;
do not route it through Hermes or rename a generic child Luna. Do not rename
generic children HY3, Ornith, or Qwen.

## Cost-first fallback ladder

`FREE_RETRY_BUDGET = 3` means: make the initial free attempt, then allow up to
three corrected free retries for the same packet before Luna. Each retry must
have a valid basis: repaired transport, a requested live anchor, a narrowed
slice, exact validator/judge evidence, newly available required capability, or
automatic advancement within the configured free-provider chain.

- Packet packaging/launch failure with no terminal provider receipt does not
  consume the free retry budget; repair delivery and retry the same semantics.
- HY3 and every configured OpenRouter `:free` fallback remain ahead of Luna.
- Weak output is not a reason to jump immediately to Luna. Re-anchor or shrink
  the packet and spend the remaining free retries.
- After the initial free attempt plus three grounded free retries fail, native
  Luna is the authorized next fallback; record the free attempt receipts in its
  packet so it does not repeat discovery.
- If Luna is unavailable at that point, preserve all successful work and let
  the supervisor continue with safe available tools. Report the unavailable
  fallback, but stop the overall task only when no safe completion path remains.
- If the user explicitly requests Luna directly, that request overrides the
  default cost ladder for that packet.

Treat custom-agent definitions, lane mappings, adapter behavior, and capacity as
mutable snapshots. Preflight current config/source and verify the returned route.
Codex custom agents live in `~/.codex/agents/*.toml` or project
`.codex/agents/*.toml`. Luna is the native custom agent named `luna`, defined at
`~/.codex/agents/luna.toml` and pinned to `gpt-5.6-luna`. New definitions may
require a fresh Codex session before the active spawn surface exposes them.

Luna availability is checked only when the free ladder is exhausted or the user
explicitly requests Luna. Its absence is not a pre-dispatch blocker for HY3,
other free providers, or local free workers.

Spawn Luna with the native Codex agent selector and no full-history fork:

```text
spawn_agent(agent_type="luna", fork_turns="none", message=<complete packet>)
```

A full-history fork inherits the parent agent type, model, and reasoning effort;
Codex rejects a simultaneous Luna override. Because `fork_turns="none"` carries
no conversation, the message must contain the complete packet. Do not retry the
rejected full-history shape with prompt variations.

## Dispatch preflight

Before writing the prompt, prove:

- the dispatch API's real fields and the controls it cannot enforce;
- resolved provider/model or worker lane when route identity matters;
- resolved tools, inheritance, sandbox/approval boundary, and edit ownership;
- working directory, timeout, cost ceiling, receipt behavior, and concurrency;
- transport preserves multiline input and actually attaches stdin;
- the proposed RED reaches the intended behavior. Import/collection failure is
  not a behavioral RED.

If a required control is unsupported, choose a capable surface or stop. Prompt
text cannot create a model selector, tool allowlist, sandbox, or receipt.

## Packet contract

Every new work-dispatch packet contains the fields its selected surface can
enforce. Mark unsupported nonessential controls `UNSUPPORTED`; switch surfaces
when an unsupported control is essential.

```text
PACKET <stable-id>
ROLE <explorer|researcher|planner|builder|tester|reviewer|reader-test>
GOAL <one independently verifiable result>
STAGE <workflow stage>
DEPENDS <packet IDs|NONE>
CWD </absolute/repository/path>
AUTH
- <ordered live authority path/artifact>
STATE
- <path>: <clean|staged|modified|untracked|ignored-generated|absent>
READ
- <path>#<symbol|lines> :: <why, or NONE>
REFERENCE <known-good path#symbol|NONE>
OWN <editable paths|NONE>
EXCLUDE <paths/behaviors>
TOOLS_REQUIRED <exact tool/toolsets|NONE>
TOOLS_OPTIONAL <exact tool/toolsets|NONE>
TOOLS_FORBIDDEN <irrelevant/high-risk capabilities>
NETWORK <none|official-docs-only|allowlist>
NETWORK_ALLOWLIST [<domain>, ...]
COST <local|free-only|explicit paid ceiling>
TIMEOUT <seconds|surface default>
RECEIPT_PATH <path|NONE>
START <first exact inspection or argv>
CONTRACT
- Preserve: <signatures/invariants/user changes>
- Produce: <exact files/data/behavior>
- Do not reconstruct unseen APIs.
ACCEPTANCE
- A1: <observable condition>
VERIFY
- A1: {cwd: <path>, argv: [<args>], expect: <exit/output/artifact>}
STOP
- NEED_CONTEXT: <missing path/symbol/signature>
- BLOCKED: <external/runtime blocker>
- SCOPE_CONFLICT: <required edit outside OWN>
- CONTRACT_MISMATCH: stop after first mismatch
RETURN <receipt schema below>
CAP <max tokens/lines; no raw logs>
```

For edits, name owned paths, live anchors, invariants, and acceptance criteria.
Include exact replacement boundaries when known; for a new file, name the whole
file as owned and constrain the public contract.

For a packet family, define a shared immutable envelope once and express later
packets as `BASE <packet-id>` plus changed fields. Expand the full packet before
dispatch so every worker is self-contained. Do not repeat policy prose in the
worker's return.

## Grounding and atomicity

Use orientation/index search to compress discovery, not as source authority.
Check freshness, then confirm against `git status`, `rg`, exact live reads,
imports, and focused tests. A tool-capable worker receives exact starting
anchors and inspects live source. A no-source worker receives verbatim excerpts
and callable signatures; summaries and pseudocode are insufficient.

Split when a packet spans unrelated lifecycle stages, independent validators,
or a second unseen API. Example: initialization, receipt model, append, replay,
immutability, and projection are separate ledger packets. Establish the
smallest callable/importable contract before a behavioral test.

Evidence format:

```text
claim -> locator(path:line | argv | URL | receipt field) -> observation -> uncertainty
```

## Hermes workers

Within Hermes routes, native `delegate_task` is the default for tasks requiring
tools. It accepts `goal`, `context`, `toolsets`, `role`, optional `worker_lane`,
or independent `tasks`. Iterations are bounded by the active delegation config;
model-supplied per-call overrides are ignored. Direct per-call provider/model
fields are not public controls; use a configured lane/default and verify the
result.

| Role | Exact Hermes toolsets |
| --- | --- |
| Source explorer | `file_readonly` |
| Current web research | `web` (`browser` only for interactive actions) |
| Builder | `file`, `terminal` |
| One-test failure analyst | `terminal`, `file_readonly` |
| Reviewer/reader-test | `file_readonly`; add `terminal` only for named checks |
| Plugin operation | Exact plugin/custom toolset; create a one-tool toolset when needed |

```json
{
  "goal": "Complete one packet and return its receipt.",
  "context": "<complete multiline packet>",
  "toolsets": ["file_readonly"],
  "role": "leaf"
}
```

Parent capabilities are the ceiling. Lane toolsets may override task toolsets;
MCP toolsets may inherit. When inherited MCP access would violate the packet,
use a dedicated parent/profile or disable `delegation.inherit_mcp_toolsets`
before dispatch. Do not expose delegation, messaging, memory, or unrelated MCP
capabilities without a requirement. Terminal is mutation-capable: instruct
testers to run only named argv. If command enforcement is essential, use a
dedicated validator tool or sandbox/approval boundary instead of general
`terminal`.

If HY3 is named and no HY3 lane exists, preflight the active delegation default
and returned provider/model. Do not invent a lane or infer HY3 from the prompt.

### Text-only HY3 adapter

`/Users/jewelbait/.hermes/scripts/hermes_hy3_worker.py` currently hardcodes no
tools and one model turn. Use it only for a complete text-only packet requiring
a durable receipt—not source inspection, code, tests, or web research.

```bash
/Users/jewelbait/.hermes/hermes-agent/venv/bin/python \
  /Users/jewelbait/.hermes/scripts/hermes_hy3_worker.py \
  --packet-id "$packet_id" --stdin --receipt-path "$receipt_path" <<'PACKET'
<complete multiline packet>
PACKET
```

`--stdin` does not supply input. Require a nonempty matching receipt and inspect
provider, model, status, fallback, and prior failures. Packaging failure does
not advance fallback. Keep configured fallbacks free unless the user explicitly
authorizes paid inference.

Any transport that flattens the packet, forces tools to none, limits a
tool-required worker to one turn, or ignores active rules is invalid. Select a
capable route instead of lengthening the prompt.

## Worker receipt

Workers return decision data, not a diary:

```json
{
  "packet_id": "...",
  "status": "COMPLETE|FAILED|NEED_CONTEXT|BLOCKED|SCOPE_CONFLICT|CONTRACT_MISMATCH",
  "route": {"surface": "...", "worker_lane": null, "provider": null, "model": null},
  "resolved_tools": ["..."],
  "tools_used": ["..."],
  "claims": [{"claim": "...", "locator": "path:line|argv|URL|receipt", "uncertainty": null}],
  "changes": [{"path": "...", "effect": "..."}],
  "checks": [{"acceptance": "A1", "argv": ["..."], "exit": 0, "evidence": "..."}],
  "fallback_used": false,
  "prior_failures": [],
  "retry_basis": null,
  "missing": [],
  "next_action": "one concrete action"
}
```

Fields unsupported by the surface may be `null`; never fabricate them. Omit
chronology, generic recommendations, full logs, and repeated prompt text.

## Failure, retry, and shrink

| Evidence | Class | Action |
| --- | --- | --- |
| No launch/result, empty stdin, flattened packet | Dispatch/transport failure | Repair delivery; retry identical semantic packet on same route |
| Required tool unavailable | Capability mismatch | Stop; change capability/surface or supply verbatim evidence |
| Output violates signature/ownership/schema | Contract mismatch | Stop on first mismatch; re-anchor or shrink |
| Import/collection fails before assertion | Invalid RED | Establish the smallest callable contract |
| `NEED_CONTEXT` | Under-anchored | Add only the requested live anchor |
| Weak nonempty output | Completed attempt | Reject or request focused revision; no silent reroute |
| Receipt records provider exception/empty response | Proven provider failure | Let the authorized fallback chain advance |
| Paid route without approval | Policy violation | Reject and investigate routing drift |

Retry only when semantic input or transport changes. Valid bases: requested
anchor, narrower slice, newly available capability, exact validator/judge
evidence, repaired packet delivery, or an authorized provider fallback. Do not
retry by paraphrasing, adding generic explanation, or asking the worker to guess
again. Stop dependent pending workers after the first contract mismatch;
preserve valid independent receipts.

## Concurrency and acceptance

Parallelize independent read-only packets and non-overlapping edits within
capacity proven by terminal results. Keep dependent implementation stages
serial. After implementation, independent specification and quality reviews
may run in parallel when neither edits. Back down after collision, hang, empty
result, or rate limit. One failed packet does not erase valid independent work.

Before acceptance, the supervisor confirms packet identity; actual route and
resolved tools; current cited source; scoped diff; acceptance evidence; and
deterministic checks. Verify fallback/prior failures only when the surface
returns them. The builder does not approve itself, a judge does not replace
tests, and the supervisor retains final accountability.

## Primary research basis

- [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- [Codex AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [OpenAI harness engineering](https://openai.com/index/harness-engineering/)
- [How OpenAI uses Codex](https://openai.com/business/guides-and-resources/how-openai-uses-codex/)
