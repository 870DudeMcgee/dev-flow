import json
from pathlib import Path

from typer.testing import CliRunner

from devflow.cli import app
from devflow.control_room.training_dataset import prepare_gemma4_training_dataset


runner = CliRunner()


def test_prepare_gemma4_training_dataset_redacts_and_excludes_unsafe_sources(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_training_fixture_repo(tmp_path)

    result = prepare_gemma4_training_dataset(tmp_path, run_id="gemma-test", max_examples=20)

    run_dir = tmp_path / ".devflow" / "training" / "gemma-test"
    dataset_path = run_dir / "dataset.jsonl"
    manifest_path = run_dir / "manifest.json"
    dry_run_path = run_dir / "remote-training-dry-run.json"

    assert result["example_count"] > 0
    assert dataset_path.exists()
    assert manifest_path.exists()
    assert dry_run_path.exists()

    dataset_text = dataset_path.read_text(encoding="utf-8")
    assert "sk-proj-abcdef1234567890SECRET" not in dataset_text
    assert "ghp_1234567890ABCDEFGHIJKLMNO" not in dataset_text
    assert "super-secret-value" not in dataset_text
    assert "RAW PROMPT SHOULD NOT APPEAR" not in dataset_text
    assert "workspace-only secret" not in dataset_text
    assert "graphify evidence should stay out" not in dataset_text
    assert "Task summary with [REDACTED] and [REDACTED]." in dataset_text

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["example_count"] == result["example_count"]
    assert manifest["source_counts"]["brainstorm_transcript"] >= 1
    assert manifest["source_counts"]["doc_excerpt"] >= 1
    assert manifest["source_counts"]["report_excerpt"] >= 1
    assert manifest["status"] == "dry_run_ready"
    assert manifest["redaction"]["status"] == "pass"
    assert manifest["redaction"]["post_redaction_secret_findings"] == []
    assert manifest["redaction"]["redaction_markers"] >= 3
    assert "fewer than 500 examples collected; smoke-only dataset" in manifest["warnings"]

    dry_run = json.loads(dry_run_path.read_text(encoding="utf-8"))
    assert dry_run["publish_disabled"] is True
    assert dry_run["push_disabled"] is True
    assert dry_run["provider_calls_disabled"] is True
    assert dry_run["training_execution_disabled"] is True
    assert dry_run["model_candidates"] == [
        "Jackrong/Ornith3.6-35B-A3B-v1-GGUF",
        "lmstudio-community/Ornith3.6-35B-A3B-MLX-4bit",
    ]
    assert dry_run["redaction"]["status"] == "pass"
    assert dry_run["lora"]["rank"] == 16
    assert dry_run["lora"]["max_seq_length"] == 2048
    assert dry_run["lora"]["gradient_accumulation_steps"] == 4
    assert dry_run["lora"]["full_fine_tune"] is False


def test_prepare_gemma4_training_dataset_honors_max_examples(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_training_fixture_repo(tmp_path)

    result = prepare_gemma4_training_dataset(tmp_path, run_id="gemma-limited", max_examples=2)

    dataset_lines = (
        tmp_path / ".devflow" / "training" / "gemma-limited" / "dataset.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert result["example_count"] == 2
    assert len(dataset_lines) == 2


def test_training_prepare_gemma4_e4b_cli_json_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_training_fixture_repo(tmp_path)

    result = runner.invoke(
        app,
        ["training", "prepare-gemma4-e4b", "--run-id", "cli-run", "--max-examples", "3", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["run_id"] == "cli-run"
    assert payload["example_count"] == 3
    assert payload["output_paths"]["dataset_jsonl"] == ".devflow/training/cli-run/dataset.jsonl"
    assert (tmp_path / payload["output_paths"]["dataset_jsonl"]).exists()


def _write_training_fixture_repo(root: Path) -> None:
    (root / "AGENTS.md").write_text("# Agent rules\nKeep work grounded.\n", encoding="utf-8")
    (root / "README.md").write_text("# DevFlow\nLocal operating layer.\n", encoding="utf-8")

    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "DEVFLOW_SOURCE_OF_TRUTH.md").write_text("# Source of Truth\nVisible next safe actions.\n", encoding="utf-8")
    (docs_dir / "README.md").write_text("# Docs\nUse the source of truth.\n", encoding="utf-8")
    (docs_dir / "local-worker-policy.md").write_text("# Local Worker Policy\nBounded lanes only.\n", encoding="utf-8")
    (docs_dir / "verification-ledger.md").write_text("# Verification\nReuse bounded checks.\n", encoding="utf-8")
    integrations = docs_dir / "integrations"
    integrations.mkdir(parents=True, exist_ok=True)
    (integrations / "hermes-local-parallelism.md").write_text("# Hermes\nBounded local parallelism.\n", encoding="utf-8")

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
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (task_dir / "events.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"event": "task_created", "task_id": "task-0001", "detail": "start"}),
                json.dumps({"event": "note", "secret_key": "super-secret-value"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    brainstorm_dir = root / ".devflow" / "brainstorms" / "session-1"
    brainstorm_dir.mkdir(parents=True, exist_ok=True)
    (brainstorm_dir / "transcript.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"kind": "message", "role": "user", "content": "How should Dev-Flow show next safe actions?"}),
                json.dumps({"kind": "message", "role": "assistant", "content": "Keep them visible and grounded in evidence."}),
                json.dumps({"kind": "message", "role": "user", "content": "What about secrets?"}),
                json.dumps({"kind": "message", "role": "assistant", "content": "Redact secret_key=super-secret-value before writing artifacts."}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (brainstorm_dir / "spec.raw.json").write_text('{"prompt":"RAW PROMPT SHOULD NOT APPEAR"}', encoding="utf-8")

    dogfood_dir = root / ".devflow" / "dogfood" / "runs" / "run-1"
    dogfood_dir.mkdir(parents=True, exist_ok=True)
    (dogfood_dir / "report.md").write_text("# Report\nNo provider calls or pushes.\n", encoding="utf-8")

    workspaces_dir = root / ".devflow" / "workspaces" / "task-0001"
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    (workspaces_dir / "secret.txt").write_text("workspace-only secret", encoding="utf-8")

    graphify_dir = root / "graphify-out"
    graphify_dir.mkdir(parents=True, exist_ok=True)
    (graphify_dir / "GRAPH_REPORT.md").write_text("graphify evidence should stay out", encoding="utf-8")
