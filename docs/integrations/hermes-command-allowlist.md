# Hermes Command Allowlist

Hermes may use this allowlist when acting as a Dev-Flow operator gateway. Prefer this command prefix from Josh's active checkout:

```bash
PYTHONPATH=src .venv/bin/python -m devflow.cli
```

Josh's current canonical checkout is `/Users/jewelbait/Desktop/Local AI Dev Team`. The old path `/Users/jewelbait/Desktop/DevFlow` is quarantined and forbidden for current work. Other operators should use their actual repo root or `<repo-root>`.

Dev-Flow artifacts beat Hermes memory. Human approval controls mutation and promotion.

## Read-Only Allowed

Hermes may run these for inspection, summarization, and non-promoting preview work. They must not be treated as approval to mutate source files, task state, git state, or promotion state.

- `devflow status --json`
- `devflow dashboard --json`
- `devflow supervisor policy --json`
- `devflow supervisor packet --json`
- `devflow hermes imessage-check --json`
- `devflow task list`
- `devflow task show <task-id>`
- `devflow task log <task-id>`
- `devflow task next-action <task-id> --json`
- `devflow task review <task-id> --json`
- `devflow task promote-preview <task-id>`
- `devflow git status`
- `devflow worktree list`
- `devflow branch list`
- `devflow knowledge list`
- `devflow knowledge show <knowledge-id>`
- `devflow knowledge search <query>`

## Explicit Approval Mutation

Hermes may recommend these commands only after explicit human approval. They can create tasks, write evidence, run workers, run verification, apply patches, or change task-local state.

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

## High-Risk Explicit Approval

These commands require direct human approval plus current Dev-Flow readiness evidence. Hermes must never run them autonomously.

- `devflow task promote <task-id>`
- `git commit`
- `git merge`
- `git push`
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
