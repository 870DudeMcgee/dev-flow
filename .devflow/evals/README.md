# devflow Evals Harness

This directory contains deterministic evaluation fixtures used to assert role-specific agent behavior without executing live model invocations.

## Fixture JSON Schema

Each evaluation fixture is defined as a JSON file matching the following schema:

```json
{
  "name": "string (name of the evaluation test)",
  "role": "string (implementer | reviewer | repair)",
  "task_markdown": "string (raw task markdown contents representing the initial task state)",
  "mock_model_response": "string (pre-seeded static response to be returned by mock invoke_local_model calls)",
  "assertions": {
    "expected_status": "string (e.g. COMPLETED | FAILED | PREVIEWED)",
    "must_touch_files": ["string (list of files that must be touched/created)"],
    "must_not_touch_files": ["string (list of files that must not be mutated)"]
  }
}
```

## Running Evaluations

You can execute evaluations via the devflow CLI:

```bash
devflow eval run --role <role>
```
