# Graph Scout Prompt

Goal: find one architecture rehab candidate from fresh Graphify evidence.

Read `LANGUAGE.md`, `GRAPHIFY-SCORING.md`, and the target repo's current architecture docs. Use Graphify report metrics and source inspection. Do not propose implementation.

Return:

- Candidate name
- Module goal
- Graphify evidence: report commit, node IDs, hotspots, diagnostics
- Source evidence: files and tests inspected
- Ponytail gate result: deletion test, seam test, existing code to reuse
- Conflict map: files likely touched
- Recommendation: Strong, Worth exploring, or Speculative
- Next safe action
