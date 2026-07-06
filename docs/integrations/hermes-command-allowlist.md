# Hermes Command Allowlist

Hermes may use this allowlist when acting as a Dev-Flow operator gateway. Prefer this command prefix from Josh's active checkout:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli
```

Use `<repo-root>` for portable command examples. This checkout is referred to as `DevFlow` in docs and handoffs. The old path `/Users/jewelbait/Desktop/DevFlow` is quarantined and forbidden for current work. Other operators should use their actual repo root or `<repo-root>`.

Dev-Flow artifacts beat Hermes memory. Human approval controls mutation and promotion.

Local-worker commands must also follow
[docs/local-worker-policy.md](../local-worker-policy.md): local workers are
opt-in, and Qwen 3.6 27B Q5 MTP is the normal single local worker lane when
opted in. Codex should use a visible `qwen36_27b_mtp_coder` subagent spawn
when that tool surface is available; Hermes should use `hermes-qwen-mtp` only
as the same-lane MCP packet wrapper. Legacy commands in this allowlist are
product evidence surfaces, not default routing.

## Read-Only Allowed

Hermes may run these for inspection, summarization, and non-promoting preview work. They must not be treated as approval to mutate source files, task state, git state, or promotion state.

- `devflow status --json`
- `devflow dashboard --json`
- `devflow supervisor policy --json`
- `devflow supervisor packet --json`
- `devflow supervisor route-message "<raw Telegram text>" --json`
- `devflow hermes imessage-check --json`
- `devflow project list`
- `devflow project show <project-id>`
- `devflow project status <project-id>`
- `devflow project doctor <project-id>`
- `devflow task list`
- `devflow task show <task-id>`
- `devflow task log <task-id>`
- `devflow task next-action <task-id> --json`
- `devflow task review <task-id> --json`
- `devflow task promote-preview <task-id>`
- `devflow git status`
- `devflow worktree list`
- `devflow branch list`
- `devflow agent list --json`
- `devflow agent show <profile-id> --json`
- `devflow agent policy --json`
- `devflow agent run --task <task-id> --profile <profile-id> --dry-run --json`
- `devflow agent advise --profile <profile-id> --job <gap-analysis|review|status> --dry-run --json`
- `devflow knowledge list`
- `devflow knowledge show <knowledge-id>`
- `devflow knowledge search <query>`

## Explicit Approval Mutation

Hermes may recommend these commands only after explicit human approval. They can create projects/tasks, write evidence, run workers, run verification, apply patches, or change task-local state.

- `devflow project create <name>`
- `devflow project import <path>`
- `devflow project archive <project-id>`
- `devflow project remove <project-id> --registry-only`
- `devflow knowledge capture`
- `devflow task create`
- `devflow task close`
- `devflow task cleanup <task-id> --preview`
- `devflow task cleanup <task-id> --apply`
- `devflow task run <task-id> --worker qwopus-implementer`
- `devflow task review-patch <task-id>`
- `devflow task patch-dry-run <task-id>`
- `devflow task apply-patch <task-id>`
- `devflow task verify <task-id>`
- `devflow agent run --task <task-id> --profile <profile-id> --json`
- `devflow agent advise --profile deepseek-v4-flash-planner --job gap-analysis --json`
- `devflow agent advise --profile deepseek-v4-pro-reviewer --task <task-id> --job review --json`

## High-Risk Explicit Approval

These commands require direct human approval plus current Dev-Flow readiness evidence. Hermes must never run them autonomously.

- `devflow task promote <task-id>`
- `devflow git checkpoint --message "<message>" --yes`
- `git commit`
- `git merge`
- `git push`
- `devflow project connect-github <project-id> --remote-url <url>`
- `devflow sync-main`
- `devflow push-main`

## Forbidden

Hermes must never do these:

- mutate `.devflow/` directly
- edit source files directly
- run raw `rm -rf` cleanup
- use `/Users/jewelbait/Desktop/DevFlow` for current work
- treat Hermes memory as canonical Dev-Flow state
- create a hidden state layer or competing orchestration brain
- bypass `devflow task promote-preview`
- spawn unbounded parallel workers
- execute `devflow agent propose-patch`; Hermes may quote the exact command for a human to run directly, but the patch-proposal surface is not Hermes-delegable
- let multiple writer agents edit one task/worktree
- mix personal/factory/iMessage automation authority with Dev-Flow repo authority
- expose secrets or message contents unnecessarily in logs

## Approval Language

For risky actions, Hermes should ask for approval with the exact command and evidence:

```text
I approve this exact Dev-Flow command after reviewing the cited readiness evidence:
<command>
```

Short approvals such as "push it", "merge everything", or "let agents fix whatever they want" are insufficient.
