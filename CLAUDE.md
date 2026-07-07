Read `AGENTS.md` first.

Read `docs/DEVFLOW_SOURCE_OF_TRUTH.md` for current product direction and `docs/README.md` for the active docs allowlist.

Historical DevMode, control-room, roadmap, and north-star material is not active authority unless the user explicitly asks for historical recovery.

Dev-Flow Git-changing actions must use Dev-Flow guardrail commands where available: `devflow git status`, `devflow sync-main`, `devflow task promote-preview`, `devflow task promote`, and `devflow push-main`; do not run raw `git push origin main`, raw promotion merges, or conflict-resolution rebases unless the human explicitly authorizes it.
