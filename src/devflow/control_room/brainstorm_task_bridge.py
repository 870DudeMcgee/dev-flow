"""Compatibility adapter for the Brainstorm -> Task bridge.

The deeper Interface now lives in ``brainstorm_pipeline`` so session artifacts,
pipeline state, implementation context, task creation, and launchpad selection
stay in one Module. This file remains for older imports.
"""

from __future__ import annotations

from devflow.control_room.brainstorm_pipeline import create_task_from_brainstorm

__all__ = ["create_task_from_brainstorm"]
