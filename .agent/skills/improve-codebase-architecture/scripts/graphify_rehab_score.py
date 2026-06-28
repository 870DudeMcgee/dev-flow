#!/usr/bin/env python3
"""Build a small architecture rehab scorecard from Graphify artifacts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPORT = Path("graphify-out/GRAPH_REPORT.md")
DEFAULT_GRAPH = Path("graphify-out/graph.json")
DEFAULT_SCORECARD_DIR = Path(".devflow/architecture-rehab/scorecards")


def _number(text: str) -> int:
    return int(text.replace(",", "").strip())


def _percent(text: str) -> int:
    return int(text.strip().rstrip("%"))


def parse_graph_report(text: str) -> dict[str, Any]:
    metrics: dict[str, Any] = {}

    if match := re.search(r"-\s*([\d,]+)\s+files\s+.\s+~([\d,]+)\s+words", text):
        metrics["files"] = _number(match.group(1))
        metrics["approximate_words"] = _number(match.group(2))

    if match := re.search(
        r"-\s*([\d,]+)\s+nodes\s+.\s+([\d,]+)\s+edges\s+.\s+([\d,]+)\s+communities"
        r"\s+\(([\d,]+)\s+shown,\s+([\d,]+)\s+thin omitted\)",
        text,
    ):
        metrics.update(
            {
                "nodes": _number(match.group(1)),
                "edges": _number(match.group(2)),
                "communities": _number(match.group(3)),
                "shown_communities": _number(match.group(4)),
                "thin_omitted_communities": _number(match.group(5)),
            }
        )

    if match := re.search(
        r"Extraction:\s*(\d+)%\s+EXTRACTED\s+.\s+(\d+)%\s+INFERRED\s+.\s+(\d+)%\s+AMBIGUOUS",
        text,
    ):
        metrics.update(
            {
                "extracted_edge_percent": _percent(match.group(1)),
                "inferred_edge_percent": _percent(match.group(2)),
                "ambiguous_edge_percent": _percent(match.group(3)),
            }
        )

    commit = ""
    if match := re.search(r"Built from commit:\s*`?([0-9a-fA-F]+)`?", text):
        commit = match.group(1)

    return {"metrics": metrics, "built_from_commit": commit}


def _node_id(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("id") or value.get("name") or "")
    return str(value)


def graph_json_metrics(graph_path: Path) -> dict[str, Any]:
    data = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = data.get("nodes") or []
    links = data.get("links") or data.get("edges") or []
    node_to_file = {
        str(node.get("id")): str(node.get("source_file") or "")
        for node in nodes
        if isinstance(node, dict) and node.get("id")
    }
    file_degrees: dict[str, int] = {}

    for link in links:
        if not isinstance(link, dict):
            continue
        for endpoint in ("source", "target"):
            source_file = node_to_file.get(_node_id(link.get(endpoint)))
            if source_file:
                file_degrees[source_file] = file_degrees.get(source_file, 0) + 1

    return {
        "graph_json_nodes": len(nodes),
        "graph_json_edges": len(links),
        "graph_json_hyperedges": len(data.get("hyperedges") or []),
        "graph_json_source_files": len({value for value in node_to_file.values() if value}),
        "max_file_degree": max(file_degrees.values(), default=0),
        "built_at_commit": str(data.get("built_at_commit") or ""),
    }


def _current_commit(repo: Path) -> str:
    result = subprocess.run(
        ["git", "-C", repo.as_posix(), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _same_commit(left: str, right: str) -> bool:
    if not left or not right or "unknown" in (left, right):
        return False
    return left.startswith(right) or right.startswith(left)


def _threshold(name: str, passed: bool, detail: str) -> dict[str, str]:
    return {"name": name, "status": "pass" if passed else "fail", "detail": detail}


def _load_baseline(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _deltas(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, int]:
    base_metrics = baseline.get("metrics") or {}
    keys = ("nodes", "edges", "communities", "max_file_degree")
    return {
        key: int(current.get(key, 0)) - int(base_metrics.get(key, 0))
        for key in keys
        if key in current and key in base_metrics
    }


def compute_scorecard(
    repo: str | Path,
    *,
    report_path: str | Path | None = None,
    graph_path: str | Path | None = None,
    baseline_path: str | Path | None = None,
    current_commit: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    report = Path(report_path) if report_path else repo_path / DEFAULT_REPORT
    graph = Path(graph_path) if graph_path else repo_path / DEFAULT_GRAPH

    report_data = parse_graph_report(report.read_text(encoding="utf-8"))
    metrics = dict(report_data["metrics"])
    graph_metrics = graph_json_metrics(graph)
    metrics.update({key: value for key, value in graph_metrics.items() if key != "built_at_commit"})

    current = current_commit or _current_commit(repo_path)
    report_commit = report_data.get("built_from_commit", "")
    graph_commit = graph_metrics.get("built_at_commit", "")
    fresh = _same_commit(current, report_commit) and (_same_commit(current, graph_commit) or not graph_commit)

    thresholds = {
        "fresh_graph": _threshold("fresh_graph", fresh, f"current={current} report={report_commit} graph={graph_commit}"),
        "extracted_edges": _threshold(
            "extracted_edges",
            int(metrics.get("extracted_edge_percent", 0)) >= 80,
            f"{metrics.get('extracted_edge_percent', 0)}% extracted",
        ),
        "ambiguous_edges": _threshold(
            "ambiguous_edges",
            int(metrics.get("ambiguous_edge_percent", 100)) <= 1,
            f"{metrics.get('ambiguous_edge_percent', 100)}% ambiguous",
        ),
    }
    baseline = _load_baseline(Path(baseline_path) if baseline_path else None)
    deltas = _deltas(metrics, baseline)

    return {
        "kind": "graphify-rehab-scorecard",
        "repo": repo_path.as_posix(),
        "generated_at": generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": {
            "current": current,
            "graph_report": report_commit,
            "graph_json": graph_commit,
            "fresh": fresh,
        },
        "metrics": metrics,
        "deltas": deltas,
        "thresholds": thresholds,
        "verdict": "pass" if all(item["status"] == "pass" for item in thresholds.values()) else "fail",
    }


def write_scorecard(card: dict[str, Any], output: str | Path | None = None) -> Path:
    if output:
        path = Path(output)
    else:
        repo = Path(card["repo"])
        stamp = card["generated_at"].replace("-", "").replace(":", "")
        path = repo / DEFAULT_SCORECARD_DIR / f"scorecard-{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Repository root. Defaults to cwd.")
    parser.add_argument("--report", default=None, help="Path to GRAPH_REPORT.md.")
    parser.add_argument("--graph", default=None, help="Path to graph.json.")
    parser.add_argument("--baseline", default=None, help="Prior scorecard JSON for delta calculation.")
    parser.add_argument("--output", default=None, help="Where to write the scorecard JSON.")
    parser.add_argument("--no-write", action="store_true", help="Print only; do not write a scorecard file.")
    parser.add_argument("--fail-on-stale", action="store_true", help="Exit non-zero if graph freshness fails.")
    args = parser.parse_args(argv)

    card = compute_scorecard(
        args.repo,
        report_path=args.report,
        graph_path=args.graph,
        baseline_path=args.baseline,
    )
    if not args.no_write:
        card["path"] = write_scorecard(card, args.output).as_posix()
    print(json.dumps(card, indent=2, sort_keys=True))
    if args.fail_on_stale and card["thresholds"]["fresh_graph"]["status"] != "pass":
        return 2
    return 0 if card["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
