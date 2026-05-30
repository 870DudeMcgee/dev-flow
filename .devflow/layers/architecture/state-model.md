# State Model

Canonical runtime state belongs in YAML, JSON, and JSONL files.

Current expected state homes:

- project state: `.devflow/project/project.yaml`
- goal state: `.devflow/goals/<goal-id>/goal.yaml`
- task state: `.devflow/tasks/<task-id>/task.yaml`
- verification state: `.devflow/tasks/<task-id>/verification.json`
- event evidence: `events.jsonl`
