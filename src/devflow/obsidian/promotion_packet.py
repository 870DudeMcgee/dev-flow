"""Promotion packet materialization (M1-S5).

Generates an inspectable ``promotion-packet.md`` after an operator ``accept``
decision. The packet is **derived and non-authoritative** — it assembles
information from existing run artifacts without inventing evidence.

Honesty rules (non-negotiable):

- If independent review / adversarial findings are not yet produced (they are
  part of M4), the section says so explicitly.
- If verification receipts or reliability reports are missing, the section says
  "not available" with the source reference.
- No section is ever populated with fabricated content.

Usage::

    from devflow.obsidian.promotion_packet import emit_promotion_packet

    path = emit_promotion_packet(root, run_id)
    if path:
        print(f"Promotion packet written to {path}")
"""

from __future__ import annotations

from pathlib import Path

from devflow.loop.independent_review import load_reviews
from devflow.loop.metrics_aggregator import (
    aggregate_metrics,
    format_metrics_section,
)
from devflow.loop.pipeline_run import load_pipeline_run, pipeline_runs_dir
from devflow.loop.workflow_ledger import (
    DECISION_RECEIPTS_DIR,
    DecisionReceipt,
    DecisionType,
)
from devflow.obsidian.render import END_MARKER, START_MARKER

PROMOTION_PACKET_FILE = "promotion-packet.md"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_dir(root: Path, run_id: str) -> Path:
    return pipeline_runs_dir(root) / run_id


def _load_accept_decision(run_dir: Path) -> DecisionReceipt | None:
    """Find the first accept-type decision receipt, or None."""
    receipts_dir = run_dir / DECISION_RECEIPTS_DIR
    if not receipts_dir.is_dir():
        return None
    for child in sorted(receipts_dir.iterdir()):
        if not child.is_file() or child.suffix != ".json":
            continue
        try:
            receipt = DecisionReceipt.model_validate_json(
                child.read_text(encoding="utf-8")
            )
        except Exception:
            continue
        if receipt.decision_type == DecisionType.accept:
            return receipt
    return None


def _read_intent(run_data: dict) -> str:
    """Extract objective text from intent.md."""
    intent = run_data.get("intent.md", "")
    if isinstance(intent, str) and intent.strip():
        return intent.strip()
    return "_No objective recorded._"


def _read_spec(run_data: dict) -> str:
    """Extract spec text if present."""
    spec = run_data.get("fixture-spec.md", "")
    if isinstance(spec, str) and spec.strip():
        return spec.strip()
    return ""


def _find_verification_receipts(run_data: dict) -> list[str]:
    """Return filenames of verification receipts found in the run."""
    return sorted(
        key for key in run_data
        if key.startswith("verification-receipt-") and key.endswith(".json")
    )


def _summarize_verification_receipt(run_data: dict, receipt_file: str) -> str:
    """Summarize one verification receipt from the run data."""
    receipt = run_data.get(receipt_file)
    if not receipt or not isinstance(receipt, dict):
        return f"- `{receipt_file}` — **malformed or unreadable**"

    passed = receipt.get("passed")
    summary = receipt.get("summary", "")
    command = receipt.get("command", "")

    status = "**passed**" if passed else "**failed**"
    line = f"- `{receipt_file}` — {status}"
    if summary:
        line += f": {summary}"
    if command:
        line += f" (`{command}`)"
    return line


def _summarize_reliability(run_data: dict) -> str:
    """Summarize the reliability report if present."""
    report = run_data.get("reliability-report.json")
    if not report or not isinstance(report, dict):
        return "> **Not available.** No reliability report found in the run directory."

    safe = report.get("safe")
    action = report.get("action", "")
    breaches = report.get("breaches", [])

    status = "**safe**" if safe else "**unsafe**"
    lines = [f"- Reliability assessment: {status}"]
    if action:
        lines.append(f"- Action: {action}")
    if breaches:
        lines.append(f"- Breaches: {', '.join(breaches)}")
    return "\n".join(lines)


def _summarize_independent_review(root_path: Path, run_id: str) -> str:
    """Summarize independent review findings if they exist (M4-S4 upgrade).

    Falls back to the honest 'not yet produced' message when no reviews exist.
    """
    try:
        reviews = load_reviews(root_path, run_id)
    except Exception:
        reviews = ()

    if not reviews:
        return (
            "> **Not yet produced.** Independent adversarial review is part of the "
            "M4 control-plane milestone. This section will be populated when "
            "the adversarial reviewer runs."
        )

    lines: list[str] = []
    for review in reviews:
        verdict_line = f"- **{review.verdict.upper()}** — reviewer family: `{review.reviewer_family}`"
        if not review.families_independent:
            verdict_line += " ⚠️ model family overlap with builder"
        lines.append(verdict_line)
        if review.findings:
            for finding in review.findings:
                lines.append(f"  - {finding}")
    return "\n".join(lines)


def _decision_action_text(decision: DecisionReceipt) -> str:
    """Map decision type to human-readable action."""
    if decision.decision_type == DecisionType.accept:
        return "Approve — the operator has accepted this verified change."
    if decision.decision_type == DecisionType.reject:
        return "Reject — the operator has rejected this change."
    return "Request changes — the operator requests modifications before approval."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_promotion_packet(
    root: Path | str,
    run_id: str,
) -> str | None:
    """Build the promotion packet Markdown for a run with an accept decision.

    Returns the Markdown string, or ``None`` if no accept decision exists.
    """
    root_path = Path(root).resolve()
    run_dir = _run_dir(root_path, run_id)

    decision = _load_accept_decision(run_dir)
    if decision is None:
        return None

    run_data = load_pipeline_run(root_path, run_id)

    objective = _read_intent(run_data)
    spec_text = _read_spec(run_data)
    verification_files = _find_verification_receipts(run_data)
    reliability_summary = _summarize_reliability(run_data)
    action_text = _decision_action_text(decision)

    # --- Build sections ---
    sections: list[str] = []

    sections.append(f"# Promotion Packet — `{run_id}`")
    sections.append("")
    sections.append(
        f"> _Derived, non-authoritative. Generated from run artifacts. "
        f"Canonical state lives in `{run_dir}`._"
    )
    sections.append("")

    # Objective
    sections.append("## Objective")
    sections.append(objective)
    if spec_text:
        sections.append("")
        sections.append("### Specification")
        sections.append(f"```markdown\n{spec_text}\n```")
    sections.append("")

    # Changed Files
    sections.append("## Changed Files")
    sections.append(
        "> Changed-path tracking from integration receipts will appear here "
        "when the integration layer records them (Phase 5 integration ledger)."
    )
    sections.append(
        f"_Integration head: `{decision.integration_head[:12]}…`_"
    )
    sections.append("")

    # Deterministic Verification
    sections.append("## Deterministic Verification")
    if verification_files:
        for vf in verification_files:
            sections.append(_summarize_verification_receipt(run_data, vf))
    else:
        sections.append(
            "> **Not available.** No verification receipts found in the run directory."
        )
    sections.append("")

    # Reliability
    sections.append("## Reliability Assessment")
    sections.append(reliability_summary)
    sections.append("")

    # Workflow Metrics (M5-S3)
    metrics = aggregate_metrics(root_path, run_id)
    sections.append(format_metrics_section(metrics))
    sections.append("")

    # Independent Review — upgraded with M4-S4 reviews when available
    sections.append("## Independent Review")
    sections.append(_summarize_independent_review(root_path, run_id))
    sections.append("")

    # Open Risks
    sections.append("## Open Risks")
    report = run_data.get("reliability-report.json")
    if isinstance(report, dict) and report.get("breaches"):
        for breach in report["breaches"]:
            sections.append(f"- {breach}")
    else:
        sections.append("_None recorded in the reliability report._")
    sections.append("")

    # Recommended Action
    sections.append("## Recommended Action")
    sections.append(action_text)
    sections.append("")

    # Decision metadata
    sections.append("## Decision Metadata")
    sections.append(f"- **Decision ID:** `{decision.decision_id}`")
    sections.append(f"- **Actor:** {decision.actor}")
    sections.append(f"- **Decision Type:** {decision.decision_type.value}")
    sections.append(f"- **Promotion Eligible:** {'yes' if decision.promotion_eligible else 'no'}")
    sections.append(f"- **Timestamp:** {decision.created_at.isoformat() if hasattr(decision.created_at, 'isoformat') else decision.created_at}")
    sections.append(f"- **Integration ID:** `{decision.integration_id}`")
    sections.append("")

    sections.append(f"_Canonical run directory: `{run_dir}`_")

    body = "\n".join(sections)
    return f"{START_MARKER}\n{body}\n{END_MARKER}\n"


def emit_promotion_packet(
    root: Path | str,
    run_id: str,
) -> Path | None:
    """Write the promotion packet to the run directory if an accept exists.

    Returns the path to the written file, or ``None`` if no accept decision.
    Idempotent: re-emit produces identical content (no overwrite if unchanged).
    """
    content = build_promotion_packet(root, run_id)
    if content is None:
        return None

    run_dir = _run_dir(Path(root).resolve(), run_id)
    target = run_dir / PROMOTION_PACKET_FILE

    # Idempotent: skip write if content is unchanged
    if target.exists() and target.read_text(encoding="utf-8") == content:
        return target

    target.write_text(content, encoding="utf-8")
    return target


__all__ = [
    "PROMOTION_PACKET_FILE",
    "build_promotion_packet",
    "emit_promotion_packet",
]
