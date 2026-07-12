from copy import deepcopy

from devflow.loop.local_audition_runner import run_local_audition


RECEIPT_KEYS = {
    "case_id",
    "role",
    "requested_model",
    "actual_model",
    "status",
    "content",
    "usage",
    "finish_reason",
    "error_type",
    "error",
    "sequence",
}


def _cases() -> list[dict]:
    return [
        {"case_id": "one", "role": "planner", "checks": [{"name": "plan"}]},
        {"case_id": "two", "role": "builder", "checks": [{"name": "build"}]},
    ]


def test_runner_is_serial_explicit_and_preserves_identity() -> None:
    calls = []

    def invoke(model, case):
        calls.append((model, case["case_id"]))
        return {
            "actual_model": model,
            "content": f"answer-{case['case_id']}",
            "usage": {"total_tokens": len(calls)},
            "finish_reason": "stop",
        }

    receipts = run_local_audition(
        _cases(),
        {"planner": "model-p", "builder": "model-b"},
        invoke,
    )

    assert calls == [("model-p", "one"), ("model-b", "two")]
    assert [receipt["sequence"] for receipt in receipts] == [1, 2]
    assert [receipt["requested_model"] for receipt in receipts] == ["model-p", "model-b"]
    assert [receipt["actual_model"] for receipt in receipts] == ["model-p", "model-b"]
    assert all(receipt["status"] == "completed" for receipt in receipts)
    assert all(set(receipt) == RECEIPT_KEYS for receipt in receipts)


def test_missing_assignment_does_not_invoke_or_substitute() -> None:
    invoked = False

    def invoke(model, case):
        nonlocal invoked
        invoked = True
        return {}

    receipt = run_local_audition(_cases()[:1], {}, invoke)[0]

    assert invoked is False
    assert receipt["status"] == "failed"
    assert receipt["requested_model"] == ""
    assert receipt["error_type"] == "MissingAssignment"


def test_runner_fails_closed_for_exception_malformed_blank_and_missing_identity() -> None:
    cases = [
        {"case_id": "exception", "role": "builder"},
        {"case_id": "malformed", "role": "builder"},
        {"case_id": "blank", "role": "builder"},
        {"case_id": "identity", "role": "builder"},
    ]

    def invoke(model, case):
        if case["case_id"] == "exception":
            raise RuntimeError("transport unavailable")
        if case["case_id"] == "malformed":
            return "not a mapping"
        if case["case_id"] == "blank":
            return {
                "actual_model": "local-builder",
                "content": "  ",
                "usage": {},
                "finish_reason": "stop",
            }
        return {"actual_model": "", "content": "code", "usage": {}, "finish_reason": "stop"}

    receipts = run_local_audition(cases, {"builder": "local-builder"}, invoke)

    assert [receipt["status"] for receipt in receipts] == ["failed"] * 4
    assert [receipt["error_type"] for receipt in receipts] == [
        "RuntimeError",
        "MalformedResult",
        "BlankCompletion",
        "MissingModelIdentity",
    ]
    assert [receipt["sequence"] for receipt in receipts] == [1, 2, 3, 4]


def test_runner_does_not_mutate_inputs_and_returns_fresh_evidence() -> None:
    cases = _cases()
    assignments = {"planner": "local-planner", "builder": "local-builder"}
    before_cases = deepcopy(cases)
    before_assignments = deepcopy(assignments)

    def invoke(model, case):
        case["checks"].append({"name": "worker-mutation"})
        return {
            "actual_model": model,
            "content": "x" * 70_000,
            "usage": {"nested": {"count": 1}},
            "finish_reason": "length",
        }

    first = run_local_audition(cases, assignments, invoke)
    second = run_local_audition(cases, assignments, invoke)
    first[0]["usage"]["nested"]["count"] = 99

    assert cases == before_cases
    assert assignments == before_assignments
    assert len(first[0]["content"]) == 64_000
    assert second[0]["usage"]["nested"]["count"] == 1
    assert second[0]["finish_reason"] == "length"


def test_runner_rejects_served_identity_mismatch_and_capped_completion() -> None:
    cases = [
        {"case_id": "identity", "role": "planner"},
        {"case_id": "capped", "role": "planner"},
    ]

    def invoke(model, case):
        return {
            "actual_model": "other-model" if case["case_id"] == "identity" else model,
            "content": "usable-looking output",
            "usage": {},
            "finish_reason": "stop" if case["case_id"] == "identity" else "length",
        }

    receipts = run_local_audition(cases, {"planner": "expected-model"}, invoke)

    assert [receipt["status"] for receipt in receipts] == ["failed", "failed"]
    assert [receipt["error_type"] for receipt in receipts] == [
        "ModelIdentityMismatch",
        "CappedCompletion",
    ]
