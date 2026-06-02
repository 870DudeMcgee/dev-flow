@./skills/using-devmode/SKILL.md

Dev-Flow Git-changing actions must use Dev-Flow guardrail commands where available: `devflow git status`, `devflow sync-main`, `devflow task promote-preview`, `devflow task promote`, and `devflow push-main`; do not run raw `git push origin main`, raw promotion merges, or conflict-resolution rebases unless the human explicitly authorizes it.
