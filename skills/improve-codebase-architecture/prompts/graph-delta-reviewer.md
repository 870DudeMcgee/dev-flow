# Graph Delta Reviewer Prompt

Goal: verify that an implementation slice has trustworthy graph and test evidence.

Read `GRAPHIFY-SCORING.md`, the before scorecard, after scorecard, test output, and diff.

Check:

- Graph freshness passes.
- Generated `graphify-out/` files are not staged or committed.
- Deltas are explained with source evidence.
- Focused tests cover the module interface.
- The diff improves locality or leverage instead of adding shallow indirection.

Return:

- Verdict: Pass, Needs correction, or Stop
- Scorecard summary
- Test summary
- Diff risk
- Injection text if the loop should be corrected
