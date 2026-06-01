from __future__ import annotations

import os


os.environ.setdefault("DEVFLOW_EXPERIMENTAL", "1")
os.environ.setdefault("OPENAI_API_KEY", "dummy-openai-key")
os.environ.setdefault("ANTHROPIC_API_KEY", "dummy-anthropic-key")
os.environ.setdefault("GEMINI_API_KEY", "dummy-gemini-key")
