# DevMode Git Policy Bridge

Dev-Flow delegates agent-facing Git and worktree discipline to DevMode. DevMode tells agents how to behave; Dev-Flow verifies and enforces repository, task, workspace, verification, and promotion state.

Relevant DevMode skills:

- `using-devmode`
- `workspace-isolation`
- `using-git-worktrees`
- `finishing-a-development-branch`
- `verification-before-completion`
- `worker-handoff`

Dev-Flow commands must not depend on agents remembering those skills. Runtime commands check unsafe Git states directly before operations that can affect `main`, task promotion, or push safety.

Dev-Flow enforcement surfaces:

- `devflow git status` reports branch, dirty state, operations in progress, origin/main relationship, push/promotion safety, and DevMode skill presence.
- `devflow git checkpoint --message "<message>"` previews a local checkpoint commit; `--yes` stages all unignored changes and commits only when `main` is safe, origin is not ahead/diverged, and no Git operation or conflict is present. It does not push, promote, merge, or open a PR.
- `devflow task orchestrate <task-id> --plan-only` records Git/DevMode baseline assumptions and stop conditions as planning evidence only; it does not execute workers or promote.
- `devflow sync-main` fetches origin, switches to `main`, and fast-forwards only. It does not merge or rebase.
- `devflow push-main` pushes `main` only when the worktree is clean, no Git operation is in progress, and `origin/main` is not ahead or diverged.
- `devflow task promote-preview` and `devflow task promote` remain human-controlled promotion gates and refuse unsafe Git-native promotion states.

This bridge is intentionally short. Do not paste DevMode skill rulebooks into Dev-Flow docs.
