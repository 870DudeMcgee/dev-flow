# Repo loop cockpit over Hermes runtime

Status: accepted

Dev-Flow will narrow from broad command center to repo loop cockpit: Obsidian owns broad capture, project context, daily context, parking lots, and cross-project knowledge, while Dev-Flow owns selected-repo guided pipeline work and repo execution artifacts under `.devflow/pipeline-runs/`. Hermes remains the runtime for deterministic tool lanes, proven loop execution, fleet routing, codebase mapping, compression, local model work, and handoff mechanics; Dev-Flow wraps those capabilities through packet preview, monitoring, steering, review, verification, and promotion gates instead of rebuilding them.

This decision preserves the working Hermes loop setup, prevents Dev-Flow from becoming a second Obsidian command center, and gives future agents a clear boundary: improve the cockpit and packet lifecycle first, prefer deterministic tools for mechanical work, then refine model routing after the V1 path works.

Consequences: V1 exposes four edit-capable loop presets, links existing Brainstorm and Task artifacts instead of migrating them, treats Hermes output as execution evidence rather than promotion proof, and excludes Ornith 9B from active Dev-Flow loop routing while leaving physical Hermes fleet cleanup as a separate migration.
