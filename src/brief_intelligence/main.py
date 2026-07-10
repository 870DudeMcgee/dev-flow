"""CLI entrypoint: briefs -> dedup -> score -> Obsidian note + Brainstorm queue.

Usage:
    python -m brief_intelligence.main --reference Reference --out Obsidian/Brief.md
                                       --queue BrainstormQueue.md [--offline]

--offline: skip the live Hermes model call; assign a stub tier so the
pipeline can be exercised (tests, backfill dry-runs) without subscription use.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from .formatter import format_obsidian
from .loader import load_briefs
from .queue_appender import append_to_queue
from .scorer import score_items


def run(
    reference_dir: Path,
    out_note: Path,
    queue_path: Path,
    *,
    offline: bool = False,
) -> dict:
    items = load_briefs(reference_dir)
    if offline:
        # deterministic stub scoring so offline runs are reproducible
        for idx, it in enumerate(items):
            it.tier = "High" if idx % 2 == 0 else "Low"
            it.reason = "offline-stub"
    else:
        score_items(items)

    note = format_obsidian(items)
    out_note.parent.mkdir(parents=True, exist_ok=True)
    out_note.write_text(note + "\n", encoding="utf-8")

    appended = append_to_queue(items, queue_path)
    return {
        "total": len(items),
        "high": sum(1 for i in items if i.tier == "High"),
        "medium": sum(1 for i in items if i.tier == "Medium"),
        "low": sum(1 for i in items if i.tier == "Low"),
        "appended_to_queue": appended,
        "note_path": str(out_note),
        "queue_path": str(queue_path),
    }


def run_daily(
    reference_dir: Path,
    out_note: Path,
    queue_path: Path,
    *,
    offline: bool = False,
    today: datetime.date | None = None,
) -> dict:
    """Process only today's brief.

    Finds the markdown file whose name contains today's date (YYYY-MM-DD)
    and runs the pipeline on just that file.
    """
    if today is None:
        today = datetime.date.today()
    date_str = today.strftime("%Y-%m-%d")

    # Find today's brief
    today_brief = None
    for md_path in sorted(reference_dir.rglob("*.md")):
        if date_str in md_path.name:
            today_brief = md_path
            break

    if today_brief is None:
        raise FileNotFoundError(f"No brief found for date {date_str} in {reference_dir}")

    # Create a temporary directory with just today's brief
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Copy today's brief to the temp directory
        import shutil
        shutil.copy2(today_brief, tmp_path / today_brief.name)
        result = run(tmp_path, out_note, queue_path, offline=offline)
    return result


def run_backfill(
    reference_dir: Path,
    out_note: Path,
    queue_path: Path,
    *,
    offline: bool = False,
) -> dict:
    """Process ALL existing briefs in the reference directory."""
    return run(reference_dir, out_note, queue_path, offline=offline)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Brief Sorter")
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--mode", choices=["backfill", "daily"], default="backfill",
                        help="Processing mode: backfill (default) or daily")
    args = parser.parse_args(argv)

    if args.mode == "daily":
        result = run_daily(args.reference, args.out, args.queue, offline=args.offline)
    else:
        result = run_backfill(args.reference, args.out, args.queue, offline=args.offline)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
