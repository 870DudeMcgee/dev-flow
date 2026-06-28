# AI Runaway Rehab

Use this when architecture work smells like generated sprawl rather than concentrated implementation.

## Symptoms

- Many shallow modules with names that explain routing, not behavior.
- Interfaces as wide as the implementation they wrap.
- New seams with one adapter and no real variation.
- Plans, handoffs, or comments claim progress without code, tests, or graph deltas.
- Tests assert internal helpers instead of the module interface.
- The agent proposes "framework", "pipeline", "manager", "registry", or "orchestrator" before proving deletion fails.

## Ponytail Gates

Every candidate must pass these gates before implementation:

1. Existing code first: name the module/helper already available or say none exists.
2. Deletion test: state what breaks if the shallow module disappears.
3. Seam test: require two real adapters before adding a seam.
4. Slice size: one behavior-preserving architecture slice, not a rewrite.
5. Test surface: tests cross the module interface, not private internal seams.
6. Evidence: before scorecard, focused tests, after scorecard.

## Stop Conditions

Stop and hand off when:

- The graph is stale.
- The slice needs product direction rather than architecture judgment.
- The worker starts expanding scope to adjacent modules.
- Progress is only a renamed file, rephrased plan, or speculative abstraction.

## Accepted Progress

Progress means at least one of:

- Deleted shallow code while tests stayed green.
- Concentrated scattered behavior behind one smaller interface.
- Replaced N caller-specific checks with one shared module behavior.
- Removed a fake seam or one-adapter indirection.

Anything else is planning until proven.
