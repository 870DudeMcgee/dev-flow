# Current State

Dev-Flow has a completed shell-worker control-room slice: task creation, isolated workspace execution, verification, task listing, task inspection, and task packet projection.

The current active work is aligning all source-of-truth docs around the next architecture direction: an Agent Registry and Adapter Runtime layered on top of the stable shell-worker control room. Future routing must use task-fit scoring, deterministic context estimates, model capability profiles, role-specific context packs, scout evidence, and routing-quality feedback instead of selecting agents by name first.

Intentionally not built in this slice:

- provider-backed adapter execution
- autonomous control-loop execution
- autonomous routing
- task-fit/context routing runtime
- dashboard changes
- enabled non-shell worker adapters
- automatic merge or PR automation

Existing tracked `.devflow/config.json`, `.devflow/evals/`, `.devflow/plans/`, and older untracked task artifacts are preserved as historical or salvage material unless explicitly promoted into active context.
