"""Load briefs from a reference directory."""
from __future__ import annotations

from pathlib import Path
from typing import Union

from .dedup import deduplicate_items
from .models import Item
from .parser import parse_markdown


def load_briefs(reference_dir: Union[str, Path]) -> list[Item]:
    """Walk reference_dir for *.md, parse each, deduplicate, return Items."""
    ref = Path(reference_dir)
    all_items: list[Item] = []
    for md_path in sorted(ref.rglob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        all_items.extend(parse_markdown(text, source_file=str(md_path)))
    return deduplicate_items(all_items)
