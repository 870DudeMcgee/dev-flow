# Current State

Dev-Flow has a completed shell-worker control-room slice: task creation, isolated workspace execution, verification, task listing, task inspection, and task packet projection.

The current active work is aligning all source-of-truth docs around the next architecture direction: an Agent Registry and Adapter Runtime layered on top of the stable shell-worker control room.

Intentionally not built in this slice:

- provider-backed adapter execution
- autonomous control-loop execution
- autonomous routing
- dashboard changes
- enabled non-shell worker adapters
- automatic merge or PR automation

Existing tracked `.devflow/config.json`, `.devflow/evals/`, `.devflow/plans/`, and older untracked task artifacts are preserved as historical or salvage material unless explicitly promoted into active context.
