"""Score brief items using a Hermes-routed frontier model (no per-token API).

The scorer shells out to the `hermes chat` CLI, which uses the user's existing
Z.AI / OpenAI OAuth subscriptions (configured in Hermes). It does NOT make raw
per-token API calls. Primary model: zai/glm-5.2. Fallback on failure:
openai-codex/gpt-5.5.
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Callable, Optional

from .models import Item

PRIMARY_MODEL = "glm-5.2"
PRIMARY_PROVIDER = "zai"
FALLBACK_MODEL = "gpt-5.5"
FALLBACK_PROVIDER = "openai-codex"

def build_prompt(item: Item) -> str:
    """Build the scorer prompt without using str.format (avoids brace conflicts)."""
    return (
        "You are a relevance scorer for an AI brief queue. Given the brief item "
        "below, score how relevant it is to active projects on a 0-1 scale and "
        "assign a tier. Respond with ONLY a JSON object: "
        '{"score": <float 0-1>, "tier": "High"|"Medium"|"Low", "reason": "<one line>"}.'
        "\n\nItem title: " + item.title +
        "\nWikilink: " + item.wikilink +
        "\nSnippet: " + item.snippet + "\n"
    )


def _call_hermes(prompt: str, *, model: str, provider: str, timeout: int = 90) -> str:
    """Invoke `hermes chat` and return its stdout text. Raises on failure."""
    cmd = [
        "hermes", "chat",
        "-q", prompt,
        "-Q",
        "-m", model,
        "--provider", provider,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"hermes chat failed ({model}/{provider}): {proc.stderr.strip()[:200]}")
    return proc.stdout


def _parse_score(text: str) -> dict:
    """Extract the first JSON object from model output."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"No JSON found in scorer output: {text[:120]!r}")
    data = json.loads(m.group(0))
    return {
        "score": float(data["score"]),
        "tier": str(data.get("tier", "Low")),
        "reason": str(data.get("reason", "")),
    }


def score_item(
    item: Item,
    *,
    scorer: Optional[Callable[[str], str]] = None,
    timeout: int = 90,
) -> dict:
    """Score a single item. Returns a dict with score/tier/reason.

    `scorer` lets tests inject a fake Hermes call (no live model). If None,
    uses the real Hermes CLI with GLM primary and GPT fallback.
    """
    prompt = build_prompt(item)
    if scorer is None:
        try:
            raw = _call_hermes(prompt, model=PRIMARY_MODEL, provider=PRIMARY_PROVIDER, timeout=timeout)
        except Exception:
            raw = _call_hermes(prompt, model=FALLBACK_MODEL, provider=FALLBACK_PROVIDER, timeout=timeout)
    else:
        raw = scorer(prompt)
    return _parse_score(raw)


def score_items(
    items: list[Item],
    *,
    scorer: Optional[Callable[[str], str]] = None,
    timeout: int = 90,
) -> list[Item]:
    """Score all items in place (mutates tier/reason) and returns them."""
    for item in items:
        result = score_item(item, scorer=scorer, timeout=timeout)
        item.tier = result["tier"]
        item.reason = result["reason"]
    return items
