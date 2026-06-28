# Ponytail Reviewer Prompt

Goal: reject overbuilt architecture rehab before implementation.

Read `AI-RUNAWAY-REHAB.md`, `LANGUAGE.md`, and the candidate packet. Apply Ponytail full mode.

Block the slice if:

- It adds a seam with one adapter.
- It moves code without deleting or concentrating complexity.
- It widens scope beyond one safe architecture slice.
- It lacks source evidence, focused tests, or graph scorecard evidence.

Return:

- Verdict: Accept, Narrow, or Reject
- The smallest acceptable slice
- Files that must not be touched
- Required focused test
- Required scorecard evidence
