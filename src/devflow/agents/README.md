# Legacy Agent Shims

This directory contains compatibility shims for the old agent system.

The files here re-export modules from `devflow._legacy.agents` so older imports and archived tests can still resolve. They are not the Ollama supervisor loop, not current worker-adapter code, and not active product authority.

Do not add new agent features here.

Active supervisor or worker-control code belongs in `src/devflow/control_room/`.
