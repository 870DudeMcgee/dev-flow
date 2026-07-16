"""Obsidian package — read-only Command Center projection for DevFlow runs.

This package derives human-facing projections from canonical workflow state.
It never mutates canonical state, never calls advancement/decision APIs,
and never overwrites human-authored notes. All output lands under
``.generated/`` with atomic replace semantics.
"""
