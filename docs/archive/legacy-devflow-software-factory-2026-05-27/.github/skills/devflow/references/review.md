# Devflow Review Mode

Use this reference when reviewing a Devflow task, current diff, or completed implementation.

Check:

- Task compliance: does the diff satisfy acceptance criteria?
- Scope creep: did unrelated changes sneak in?
- Protected file changes: were any protected files modified?
- Missing tests: are behavior changes covered by tests?
- Verification gaps: was verification actually run?
- Token or context waste: could the change be smaller?
- Simpler implementation options: is there a simpler approach?

Return:

```json
{
  "status": "approve | changes_requested | blocked",
  "blocking_findings": [],
  "non_blocking_findings": [],
  "verification_required": [],
  "summary": ""
}
```