# Current State

Dev-Flow has a completed shell-worker control-room slice and a stable manual proof-agent contract for `devflow-manual-codex-worker`: task creation, isolated workspace execution/handoff, verification, task listing, task inspection, dashboard visibility, and task packet projection.

The current active work is keeping the shell-worker and manual proof-agent loop stable before any provider-backed adapters, routing, scheduling, or multi-agent orchestration. Future routing must use task-fit scoring, deterministic context estimates, model capability profiles, role-specific context packs, scout evidence, and routing-quality feedback instead of selecting agents by name first.

Intentionally not built in this slice:

- provider-backed adapter execution
- autonomous control-loop execution
- autonomous routing
- task-fit/context routing runtime
- dashboard changes
- provider-backed non-shell worker adapters
- automatic merge or PR automation

Existing tracked `.devflow/config.json`, `.devflow/evals/`, `.devflow/plans/`, and older untracked task artifacts are preserved as historical or salvage material unless explicitly promoted into active context.
