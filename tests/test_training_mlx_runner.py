import json
import subprocess
from pathlib import Path

from devflow.control_room.training_mlx_runner import (
    build_mlx_lora_reload_smoke_argv,
    build_mlx_load_smoke_argv,
    build_mlx_lora_smoke_argv,
    model_slug,
    prepare_mlx_training_data,
    run_load_smoke,
    run_lora_smoke,
)


def test_prepare_mlx_training_data_writes_text_jsonl_with_redaction(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write_training_fixture_repo(tmp_path)

    result = prepare_mlx_training_data(tmp_path, run_id="mlx-test", max_examples=2)

    train_path = tmp_path / ".devflow" / "training" / "mlx-test" / "data" / "train.jsonl"
    lines = train_path.read_text(encoding="utf-8").splitlines()

    assert result["example_count"] == 2
    assert len(lines) == 2
    row = json.loads(lines[0])
    assert list(row) == ["text"]
    assert "[REDACTED]" in row["text"]
    assert "sk-proj-abcdef1234567890SECRET" not in row["text"]
    assert "ghp_1234567890ABCDEFGHIJKLMNO" not in row["text"]
    assert result["redaction"]["status"] == "pass"


def test_mlx_argv_builders_match_expected_shape(tmp_path: Path) -> None:
    run_dir = tmp_path / ".devflow" / "training" / "mlx-test"
    model = "mlx-community/Qwen3.6-27B-MLX-4bit"

    assert build_mlx_load_smoke_argv(model) == [
        "uvx",
        "--python",
        "3.12",
        "--from",
        "mlx-lm[train]",
        "mlx_lm.generate",
        "--model",
        model,
        "--prompt",
        "Reply with exactly: mlx load ok",
        "--max-tokens",
        "8",
    ]
    assert build_mlx_lora_smoke_argv(model, run_dir=run_dir, iters=3) == [
        "uvx",
        "--python",
        "3.12",
        "--from",
        "mlx-lm[train]",
        "mlx_lm.lora",
        "--model",
        model,
        "--train",
        "--data",
        str(run_dir / "data"),
        "--iters",
        "3",
        "--batch-size",
        "1",
        "--num-layers",
        "2",
        "--max-seq-length",
        "512",
        "--grad-checkpoint",
        "--steps-per-report",
        "1",
        "--save-every",
        "1",
        "--adapter-path",
        str(run_dir / "models" / model_slug(model) / "adapters"),
    ]
    assert build_mlx_lora_reload_smoke_argv(model, run_dir=run_dir) == [
        "uvx",
        "--python",
        "3.12",
        "--from",
        "mlx-lm[train]",
        "mlx_lm.generate",
        "--model",
        model,
        "--prompt",
        "Reply with exactly: mlx lora reload ok",
        "--max-tokens",
        "8",
        "--adapter-path",
        str(run_dir / "models" / model_slug(model) / "adapters"),
    ]


def test_run_load_smoke_dry_run_writes_evidence_and_log(tmp_path: Path) -> None:
    payload = run_load_smoke(tmp_path, model="mlx-community/Qwen3.6-27B-MLX-4bit", run_id="mlx-test", dry_run=True)

    model_dir = tmp_path / ".devflow" / "training" / "mlx-test" / "models" / payload["model_slug"]
    evidence = json.loads((model_dir / "load-smoke.dry-run.json").read_text(encoding="utf-8"))
    log_text = (model_dir / "load-smoke.dry-run.log").read_text(encoding="utf-8")

    assert payload["status"] == "dry_run"
    assert payload["evidence_path"].endswith("load-smoke.dry-run.json")
    assert evidence["command"][0] == "uvx"
    assert evidence["dry_run"] is True
    assert "dry-run" in log_text


def test_run_load_smoke_dry_run_does_not_overwrite_real_evidence(tmp_path: Path) -> None:
    def fake_runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    real = run_load_smoke(
        tmp_path,
        model="lmstudio-community/Qwen3.6-27B-MLX-4bit",
        run_id="mlx-test",
        dry_run=False,
        runner=fake_runner,
    )
    run_load_smoke(
        tmp_path,
        model="lmstudio-community/Qwen3.6-27B-MLX-4bit",
        run_id="mlx-test",
        dry_run=True,
    )

    real_evidence = json.loads((tmp_path / real["evidence_path"]).read_text(encoding="utf-8"))
    assert real_evidence["status"] == "success"


def test_run_lora_smoke_records_failure_reason_from_injected_runner(tmp_path: Path) -> None:
    prepare_mlx_training_data(tmp_path, run_id="mlx-test", max_examples=1)

    def fake_runner(argv, **kwargs):
        assert kwargs == {"capture_output": True, "text": True, "check": False}
        return subprocess.CompletedProcess(argv, 2, stdout="", stderr="mlx failed to train")

    payload = run_lora_smoke(
        tmp_path,
        model="mlx-community/Qwen3.6-27B-MLX-4bit",
        run_id="mlx-test",
        dry_run=False,
        iters=2,
        runner=fake_runner,
    )

    model_dir = tmp_path / ".devflow" / "training" / "mlx-test" / "models" / payload["model_slug"]
    evidence = json.loads((model_dir / "lora-smoke.json").read_text(encoding="utf-8"))

    assert payload["status"] == "failed"
    assert payload["failure_reason"] == "mlx failed to train"
    assert evidence["adapter_path"].endswith("/adapters")
    assert evidence["exit_code"] == 2


def test_run_lora_smoke_records_reload_evidence_when_adapter_exists(tmp_path: Path) -> None:
    prepare_mlx_training_data(tmp_path, run_id="mlx-test", max_examples=1)
    model = "mlx-community/Qwen3.6-27B-MLX-4bit"
    run_dir = tmp_path / ".devflow" / "training" / "mlx-test"
    adapter_path = run_dir / "models" / model_slug(model) / "adapters"
    adapter_path.mkdir(parents=True, exist_ok=True)
    (adapter_path / "adapters.safetensors").write_text("adapter", encoding="utf-8")
    (adapter_path / "adapter_config.json").write_text("{}", encoding="utf-8")

    calls: list[list[str]] = []

    def fake_runner(argv, **kwargs):
        calls.append(list(argv))
        if "mlx_lm.lora" in argv:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="reload ok", stderr="")

    payload = run_lora_smoke(
        tmp_path,
        model=model,
        run_id="mlx-test",
        dry_run=False,
        iters=2,
        runner=fake_runner,
    )

    model_dir = run_dir / "models" / model_slug(model)
    evidence = json.loads((model_dir / "lora-smoke.json").read_text(encoding="utf-8"))
    reload_evidence = json.loads((model_dir / "lora-smoke-reload.json").read_text(encoding="utf-8"))

    assert payload["status"] == "success"
    assert payload["commands"] == [
        build_mlx_lora_smoke_argv(model, run_dir=tmp_path / ".devflow" / "training" / "mlx-test", iters=2),
        build_mlx_lora_reload_smoke_argv(model, run_dir=tmp_path / ".devflow" / "training" / "mlx-test"),
    ]
    assert payload["reload_status"] == "success"
    assert payload["reload_exit_code"] == 0
    assert payload["duration_seconds"] == evidence["duration_seconds"]
    assert evidence["reload_status"] == "success"
    assert reload_evidence["command"] == build_mlx_lora_reload_smoke_argv(
        model,
        run_dir=tmp_path / ".devflow" / "training" / "mlx-test",
    )
    assert evidence["commands"] == payload["commands"]
    assert len(calls) == 2


def test_run_lora_smoke_fails_when_expected_adapter_files_are_absent(tmp_path: Path) -> None:
    prepare_mlx_training_data(tmp_path, run_id="mlx-test", max_examples=1)
    model = "mlx-community/Qwen3.6-27B-MLX-4bit"

    payload = run_lora_smoke(
        tmp_path,
        model=model,
        run_id="mlx-test",
        dry_run=False,
        iters=1,
        runner=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout="ok", stderr=""),
    )

    evidence_path = tmp_path / ".devflow" / "training" / "mlx-test" / "models" / model_slug(model) / "lora-smoke.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert payload["status"] == "failed"
    assert evidence["status"] == "failed"
    assert evidence["failure_reason"] == payload["failure_reason"]
    assert "missing expected adapter files" in payload["failure_reason"]


def test_run_lora_smoke_fails_when_adapter_dir_has_only_unrelated_files(tmp_path: Path) -> None:
    prepare_mlx_training_data(tmp_path, run_id="mlx-test", max_examples=1)
    model = "mlx-community/Qwen3.6-27B-MLX-4bit"
    adapter_path = tmp_path / ".devflow" / "training" / "mlx-test" / "models" / model_slug(model) / "adapters"
    adapter_path.mkdir(parents=True, exist_ok=True)
    (adapter_path / "train.log").write_text("not an adapter", encoding="utf-8")

    payload = run_lora_smoke(
        tmp_path,
        model=model,
        run_id="mlx-test",
        dry_run=False,
        iters=1,
        runner=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout="ok", stderr=""),
    )

    assert payload["status"] == "failed"
    assert "adapters.safetensors" in payload["failure_reason"]


def test_run_load_smoke_records_timeout_as_failure(tmp_path: Path) -> None:
    def fake_runner(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"partial")

    payload = run_load_smoke(
        tmp_path,
        model="lmstudio-community/Qwen3.6-27B-MLX-4bit",
        run_id="mlx-timeout",
        dry_run=False,
        runner=fake_runner,
        timeout_seconds=1,
    )

    log_path = tmp_path / payload["log_path"]
    assert payload["status"] == "failed"
    assert payload["failure_reason"] == "timed out after 1 seconds"
    assert log_path.read_text(encoding="utf-8") == "partial"


def _write_training_fixture_repo(root: Path) -> None:
    (root / "AGENTS.md").write_text("# Agent rules\nKeep work grounded.\n", encoding="utf-8")
    (root / "README.md").write_text("# DevFlow\nLocal operating layer.\n", encoding="utf-8")

    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "DEVFLOW_SOURCE_OF_TRUTH.md").write_text("# Source of Truth\nVisible next safe actions.\n", encoding="utf-8")
    (docs_dir / "README.md").write_text("# Docs\nUse the source of truth.\n", encoding="utf-8")
    (docs_dir / "local-worker-policy.md").write_text("# Local Worker Policy\nBounded lanes only.\n", encoding="utf-8")
    (docs_dir / "verification-ledger.md").write_text("# Verification\nReuse bounded checks.\n", encoding="utf-8")

    task_dir = root / ".devflow" / "tasks" / "task-0001"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "summary.json").write_text(
        json.dumps(
            {
                "task_id": "task-0001",
                "title": "Dataset prep",
                "status": "verified",
                "summary": "Task summary with sk-proj-abcdef1234567890SECRET and ghp_1234567890ABCDEFGHIJKLMNO.",
                "merge_ready": False,
            }
        ),
        encoding="utf-8",
    )
    (task_dir / "events.jsonl").write_text(
        json.dumps({"event": "note", "secret_key": "super-secret-value"}) + "\n",
        encoding="utf-8",
    )

    brainstorm_dir = root / ".devflow" / "brainstorms" / "session-1"
    brainstorm_dir.mkdir(parents=True, exist_ok=True)
    (brainstorm_dir / "transcript.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"kind": "message", "role": "user", "content": "What should Dev-Flow show next?"}),
                json.dumps({"kind": "message", "role": "assistant", "content": "Visible next safe actions."}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    dogfood_dir = root / ".devflow" / "dogfood" / "runs" / "run-1"
    dogfood_dir.mkdir(parents=True, exist_ok=True)
    (dogfood_dir / "report.md").write_text("# Report\nNo provider calls or pushes.\n", encoding="utf-8")
