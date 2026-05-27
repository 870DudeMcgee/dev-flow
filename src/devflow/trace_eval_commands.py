from __future__ import annotations

import json
import os
import sys


def trace_list_command() -> None:
    from devflow.traces import Span

    trace_dir = Span.LOG_DIR
    if not os.path.isdir(trace_dir):
        print("No traces found (logs directory does not exist).")
        return

    files = [f for f in os.listdir(trace_dir) if f.endswith(".json")]
    if not files:
        print("No traces found.")
        return

    print(f"{'Trace ID':<34} | {'Start Time':<20} | {'Spans':<5} | {'Duration':<10} | {'Status':<8}")
    print("-" * 88)
    for filename in sorted(files):
        trace_id = filename[:-5]
        path = os.path.join(trace_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                spans = json.load(handle)
            if not spans:
                continue

            oldest = min(spans, key=lambda span: span.get("start_time", ""))
            start_time = oldest.get("start_time", "Unknown")[:19]

            total_duration = sum(span.get("duration_ms", 0.0) for span in spans if span.get("parent_span_id") is None)
            if total_duration == 0:
                total_duration = sum(span.get("duration_ms", 0.0) for span in spans)

            overall_status = "SUCCESS"
            if any(span.get("status") == "ERROR" for span in spans):
                overall_status = "ERROR"

            print(f"{trace_id:<34} | {start_time:<20} | {len(spans):<5} | {total_duration:>8.2f}ms | {overall_status:<8}")
        except Exception:
            pass


def trace_inspect_command(trace_id: str) -> None:
    from devflow.traces import Span

    path = os.path.join(Span.LOG_DIR, f"{trace_id}.json")
    if not os.path.exists(path):
        print(f"Error: Trace ID '{trace_id}' not found.")
        sys.exit(1)

    try:
        with open(path, "r", encoding="utf-8") as handle:
            spans = json.load(handle)
    except Exception as exc:
        print(f"Error reading trace data: {exc}")
        sys.exit(1)

    print(f"Trace Execution Graph for ID: {trace_id}")
    print("=" * 60)

    tree: dict[str, list[dict]] = {}
    roots: list[dict] = []
    for span in spans:
        parent = span.get("parent_span_id")
        if not parent:
            roots.append(span)
        else:
            if parent not in tree:
                tree[parent] = []
            tree[parent].append(span)

    def print_tree(span: dict, indent: str = "", is_last: bool = True) -> None:
        marker = "└── " if is_last else "├── "
        status_suffix = ""
        if span.get("status") == "ERROR":
            status_suffix = f" [ERROR: {span.get('error_message')}]"

        duration = span.get("duration_ms", 0.0)
        print(f"{indent}{marker}{span.get('name')} ({duration:.2f}ms){status_suffix}")

        children = tree.get(span.get("span_id"), [])
        next_indent = indent + ("    " if is_last else "│   ")
        for index, child in enumerate(children):
            print_tree(child, next_indent, index == len(children) - 1)

    for index, root in enumerate(roots):
        print_tree(root, "", index == len(roots) - 1)


def eval_run_command(role: str) -> None:
    from devflow.evals import run_role_eval

    print(f"Executing deterministic evaluations for role: {role}...")
    print("=" * 60)

    results = run_role_eval(role, root_dir=os.getcwd())
    if results["total"] == 0:
        print(f"No mock fixtures found for role '{role}' under .devflow/evals/fixtures/.")
        return

    for failure in results["failures"]:
        print(f"Fixture {failure.get('fixture')} ({failure.get('name')}): FAILED")
        print(f"  Error: {failure.get('message')}")
        print("-" * 40)

    passed = results["passed"]
    total = results["total"]
    success_rate = (passed / total) * 100 if total > 0 else 0
    print("\nEvaluation Summary:")
    print(f"Passed: {passed}/{total} (Success Rate: {success_rate:.1f}%)")

    if len(results["failures"]) > 0:
        sys.exit(1)
    else:
        sys.exit(0)


def eval_compare_command(prompt_a: str, prompt_b: str) -> None:
    from devflow.evals import compare_prompts

    results = compare_prompts(prompt_a, prompt_b)

    print("Prompt Performance Comparison Report:")
    print("=" * 60)
    print(f"Prompt A: {results.get('prompt_a')}")
    print(f"Prompt B: {results.get('prompt_b')}")
    print("-" * 60)

    metrics = results.get("metrics", {})
    a_met = metrics.get("prompt_a", {})
    b_met = metrics.get("prompt_b", {})

    print(f"{'Metric':<20} | {'Prompt A':<15} | {'Prompt B':<15} | {'Difference':<12}")
    print("-" * 68)

    token_diff = b_met.get("tokens", 0) - a_met.get("tokens", 0)
    token_diff_pct = (token_diff / a_met.get("tokens", 1)) * 100
    print(f"{'Tokens':<20} | {a_met.get('tokens'):<15} | {b_met.get('tokens'):<15} | {token_diff_pct:>+6.1f}%")

    dur_diff = b_met.get("duration_ms", 0.0) - a_met.get("duration_ms", 0.0)
    dur_diff_pct = (dur_diff / a_met.get("duration_ms", 1.0)) * 100
    print(f"{'Duration':<20} | {a_met.get('duration_ms'):>13.2f}ms | {b_met.get('duration_ms'):>13.2f}ms | {dur_diff_pct:>+6.1f}%")

    cost_diff = b_met.get("cost_usd", 0.0) - a_met.get("cost_usd", 0.0)
    cost_diff_pct = (cost_diff / a_met.get("cost_usd", 1.0)) * 100
    print(f"{'Estimated Cost':<20} | ${a_met.get('cost_usd'):<14.6f} | ${b_met.get('cost_usd'):<14.6f} | {cost_diff_pct:>+6.1f}%")
    print("=" * 68)
    print(f"Conclusion: {results.get('comparison')}")
