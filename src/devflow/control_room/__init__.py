"""V2-native control room — brainstorm chat surface and loop gate.

This package is the clean V2 surface: a single web-based chat that gates the
disciplined DevFlow pipeline (idea → definition → spec → planning →
planning_judge → assignment → build_judge → verification → human_decision →
complete).

No legacy imports. All persistence goes through ``devflow.loop.pipeline_run``
and all model access goes through ``devflow.loop.model_router``.
"""
