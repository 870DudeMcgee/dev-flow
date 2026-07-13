"""Deterministic role cases for opt-in local-model auditions.

The casebook is data only.  It deliberately owns no routing, execution, or
scoring behavior so the same bounded cases can be replayed against different
local models and judged from explicit evidence.
"""

from __future__ import annotations

from copy import deepcopy


_ROLE_BUDGETS = {
    "brainstorm": 2048,
    "planner": 4096,
    "planning_judge": 2048,
    "builder": 16384,
    "build_judge": 2048,
    "verifier": 2048,
    "final_judge": 2048,
}


_CASES = (
    {
        "case_id": "local-brainstorm-brief-v1",
        "role": "brainstorm",
        "system_prompt": "Clarify a rough product idea without inventing requirements.",
        "user_prompt": (
            "Turn a request for a local-model audition into a brief covering user, "
            "outcome, scope, exclusions, success evidence, assumptions, and decisions."
        ),
        "max_tokens": 2048,
        "required_output": {
            "format": "json_object",
            "required_keys": [
                "user", "outcome", "scope", "out_of_scope", "success_evidence",
                "assumptions", "unresolved_decisions",
            ],
        },
        "checks": [
            {
                "name": "idea_brief_contract",
                "expectation": {"required_keys_present": True, "unknowns_are_labeled": True},
            },
        ],
    },
    {
        "case_id": "local-planner-packet-v1",
        "role": "planner",
        "system_prompt": "Produce the smallest repo-grounded executable plan.",
        "user_prompt": (
            "Plan a pure Python helper and focused test in exactly two declared files. "
            "Name dependencies, task order, file boundaries, and the pytest command."
        ),
        "max_tokens": 4096,
        "required_output": {
            "format": "json_object",
            "required_keys": [
                "spec", "plan", "target_files", "dependencies", "verification_command",
            ],
        },
        "checks": [
            {
                "name": "bounded_plan_contract",
                "expectation": {"target_file_count": 2, "verification_is_explicit": True},
            },
        ],
    },
    {
        "case_id": "local-planning-judge-v1",
        "role": "planning_judge",
        "system_prompt": "Judge plan safety, grounding, boundaries, and verification reality.",
        "user_prompt": (
            "Review a two-file plan that omits its verification command. Return a bounded "
            "decision and the exact required correction."
        ),
        "max_tokens": 2048,
        "required_output": {
            "format": "json_object",
            "required_keys": ["decision", "required_changes", "next_safe_action"],
            "allowed_decisions": ["approve", "revise", "block", "escalate_to_user"],
        },
        "checks": [
            {
                "name": "missing_verification_detected",
                "expectation": {"decision": "revise", "names_missing_command": True},
            },
        ],
    },
    {
        "case_id": "local-builder-function-v1",
        "role": "builder",
        "system_prompt": "Implement only the declared target and return its complete contents.",
        "user_prompt": (
            "Implement normalize_names(values), returning unique nonblank string values in "
            "input order after trimming whitespace. Use only the standard library."
        ),
        "max_tokens": 4096,
        "required_output": {
            "format": "file_blocks",
            "target_files": ["src/example.py", "tests/test_example.py"],
        },
        "checks": [
            {
                "name": "builder_behavior",
                "expectation": {
                    "unique_input_order": True,
                    "trims_whitespace": True,
                    "ignores_non_strings": True,
                },
            },
            {
                "name": "builder_scope",
                "expectation": {"only_declared_files": True, "stdlib_only": True},
            },
        ],
    },
    {
        "case_id": "local-build-judge-v1",
        "role": "build_judge",
        "system_prompt": "Review supplied code evidence without repairing or self-approving it.",
        "user_prompt": (
            "Judge an implementation that keeps duplicate normalized names despite a unique-"
            "values requirement. Cite the defect and return a structured verdict."
        ),
        "max_tokens": 2048,
        "required_output": {
            "format": "json_object",
            "required_keys": ["status", "rationale", "diff_evidence"],
            "allowed_statuses": ["passed", "failed", "needs_review"],
        },
        "checks": [
            {
                "name": "duplicate_defect_detected",
                "expectation": {"status": "failed", "evidence_is_specific": True},
            },
        ],
    },
    {
        "case_id": "local-verifier-receipts-v1",
        "role": "verifier",
        "system_prompt": "Reconcile deterministic receipts and gate evidence independently.",
        "user_prompt": (
            "A build judge passed, but pytest exited 1. Return the verification outcome that "
            "follows from the deterministic receipt."
        ),
        "max_tokens": 2048,
        "required_output": {
            "format": "json_object",
            "required_keys": ["status", "rationale", "evidence_refs"],
            "allowed_statuses": ["passed", "failed", "needs_review"],
        },
        "checks": [
            {
                "name": "failed_receipt_precedence",
                "expectation": {"status": "failed", "cites_test_receipt": True},
            },
        ],
    },
    {
        "case_id": "local-final-judge-handoff-v3",
        "role": "final_judge",
        "system_prompt": "Synthesize evidence into the next explicit human decision.",
        "user_prompt": (
            "The implementation and tests passed, but served-model identity is missing. "
            "Produce a release handoff that does not silently qualify the model."
        ),
        "max_tokens": 2048,
        "required_output": {
            "format": "json_object",
            "required_keys": [
                "schema_version",
                "decision",
                "rationale",
                "evidence_refs",
                "residual_risks",
                "next_action",
            ],
            "allowed_decisions": ["qualify", "hold", "block"],
            "allowed_next_actions": [
                "none",
                "repair_and_reverify",
                "provide_missing_evidence",
                "reconcile_conflicting_evidence",
                "human_choice_required",
            ],
        },
        "checks": [
            {
                "name": "identity_evidence_required",
                "expectation": {
                    "decision": "hold",
                    "next_action": "provide_missing_evidence",
                    "requests_identity_evidence": True,
                },
            },
        ],
    },
)


def build_local_audition_casebook() -> list[dict]:
    """Return a fresh, canonically ordered local-audition casebook."""
    cases = deepcopy(_CASES)
    for case in cases:
        role = case["role"]
        if case["max_tokens"] > _ROLE_BUDGETS[role]:
            raise ValueError(f"Case {case['case_id']} exceeds the {role} token budget.")
    return list(cases)


__all__ = ["build_local_audition_casebook"]
