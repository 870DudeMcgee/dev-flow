import json
from pathlib import Path

from devflow.control_room.training_mlx_matrix import write_trainability_matrix
from devflow.control_room.training_mlx_runner import model_slug


def test_write_trainability_matrix_uses_default_models_and_evidence(tmp_path: Path) -> None:
    run_dir = tmp_path / ".devflow" / "training" / "mlx-run"
    model = "lmstudio-community/Qwen3.6-27B-MLX-4bit"
    model_dir = run_dir / "models" / model_slug(model)
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "load-smoke.json").write_text(
        json.dumps(
            {
                "command": ["uvx", "mlx_lm.generate"],
                "duration_seconds": 1.25,
                "exit_code": 0,
                "status": "pass",
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "lora-smoke.json").write_text(
        json.dumps(
            {
                "commands": [["uvx", "mlx_lm.lora"]],
                "duration_seconds": 2,
                "exit_code": 0,
                "adapter_path": ".devflow/training/mlx-run/adapters/gemma",
            }
        ),
        encoding="utf-8",
    )

    result = write_trainability_matrix(tmp_path, "mlx-run")

    assert result["row_count"] == 6
    matrix_path = tmp_path / result["matrix_path"]
    payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert payload["model_test_order"] == [row["model"] for row in payload["rows"]]
    row = payload["rows"][0]
    assert row["model"] == model
    assert row["slug"] == model_slug(model)
    assert row["runtime_family"] == "mlx_lm"
    assert row["training_surface"] == "mlx_lm_text_trainable"
    assert row["load_smoke"] == "pass"
    assert row["lora_smoke"] == "pass"
    assert row["adapter_path"] == ".devflow/training/mlx-run/adapters/gemma"
    assert row["commands"] == [["uvx", "mlx_lm.generate"], ["uvx", "mlx_lm.lora"]]
    assert row["duration_seconds"] == 3.25
    assert row["exit_code"] == 0
    assert row["failure_reason"] is None
    assert row["evidence_paths"] == [
        f".devflow/training/mlx-run/models/{model_slug(model)}/load-smoke.json",
        f".devflow/training/mlx-run/models/{model_slug(model)}/lora-smoke.json",
    ]
    assert row["adapter_reload_smoke"] == "missing"


def test_write_trainability_matrix_parses_manifest_shapes_and_guardrails(tmp_path: Path) -> None:
    manifest_path = tmp_path / "models.json"
    manifest_path.write_text(
        json.dumps(
            {
                "models": [
                    "ollama/qwen2.5:latest",
                    {
                        "model": "mlx-community/Qwen2.5-VL-7B",
                        "input_modalities": ["text", "image"],
                    },
                    {"model": "mlx-community/gemma-4-e4b-it-4bit", "input_modalities": ["text"]},
                    {
                        "model": "mlx-community/gemma-4-e4b-it-4bit",
                        "input_modalities": ["text", "image"],
                        "training_surface": "mlx_lm_text_trainable",
                        "claim_basis": "explicit_override",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = write_trainability_matrix(tmp_path, "manifest-run", manifest_path=manifest_path)
    rows = result["rows"]

    assert rows[0]["runtime_family"] == "ollama"
    assert rows[0]["training_surface"] == "inference_only"
    assert rows[0]["lora_smoke"] == "not_applicable"
    assert rows[0]["claim_basis"] == "runtime_family_guardrail"

    assert rows[1]["training_surface"] == "mlx_vlm_load_smoke_only"
    assert rows[1]["lora_smoke"] == "not_applicable"
    assert rows[1]["claim_basis"] == "multimodal_guardrail"

    assert rows[2]["training_surface"] == "mlx_lm_text_trainable"
    assert rows[2]["claim_basis"] == "default_text_only_mlx_lm"

    assert rows[3]["training_surface"] == "mlx_vlm_load_smoke_only"
    assert rows[3]["lora_smoke"] == "not_applicable"
    assert rows[3]["claim_basis"] == "multimodal_guardrail"


def test_write_trainability_matrix_supports_manifest_order_reload_evidence_and_gguf_guardrails(tmp_path: Path) -> None:
    manifest_path = tmp_path / "models-order.json"
    models = [
        {"model": "lmstudio-community/Qwen3.6-27B-MLX-4bit"},
        {"model": "mlx-community/Qwen3.6-35B-A3B-OptiQ-4bit"},
        {"model": "Jackrong/Qwopus3.6-35B-A3B-v1-GGUF:Q4_K_M"},
        {"model": "gemma4-e4b:latest", "runtime_family": "mlx_lm", "input_modalities": ["text"]},
    ]
    manifest_path.write_text(json.dumps({"models": models}), encoding="utf-8")

    run_dir = tmp_path / ".devflow" / "training" / "ordered-run"
    qwen_model = "lmstudio-community/Qwen3.6-27B-MLX-4bit"
    model_dir = run_dir / "models" / model_slug(qwen_model)
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "lora-smoke.json").write_text(
        json.dumps(
            {
                "command": ["uvx", "mlx_lm.lora"],
                "duration_seconds": 2,
                "exit_code": 0,
                "adapter_path": ".devflow/training/ordered-run/adapters/qwen27",
            }
        ),
        encoding="utf-8",
    )
    (model_dir / "lora-smoke-reload.json").write_text(
        json.dumps(
            {
                "command": ["uvx", "mlx_lm.generate", "--adapter-path", "reload"],
                "duration_seconds": 1,
                "exit_code": 0,
                "status": "success",
            }
        ),
        encoding="utf-8",
    )

    result = write_trainability_matrix(tmp_path, "ordered-run", manifest_path=manifest_path)

    assert [row["model"] for row in result["rows"]] == [item["model"] for item in models]
    first = result["rows"][0]
    assert first["lora_smoke"] == "pass"
    assert first["adapter_reload_smoke"] == "pass"
    assert first["commands"] == [
        ["uvx", "mlx_lm.lora"],
        ["uvx", "mlx_lm.generate", "--adapter-path", "reload"],
    ]
    assert first["duration_seconds"] == 3
    assert first["evidence_paths"] == [
        f".devflow/training/ordered-run/models/{model_slug(qwen_model)}/lora-smoke.json",
        f".devflow/training/ordered-run/models/{model_slug(qwen_model)}/lora-smoke-reload.json",
    ]

    qwopus = result["rows"][2]
    assert qwopus["runtime_family"] == "gguf"
    assert qwopus["training_surface"] == "inference_only"
    assert qwopus["lora_smoke"] == "not_applicable"
    assert qwopus["adapter_reload_smoke"] == "not_applicable"

    gemma4 = result["rows"][3]
    assert gemma4["runtime_family"] == "mlx_lm"
    assert gemma4["training_surface"] == "mlx_lm_text_trainable"


def test_write_trainability_matrix_supports_list_manifest_and_missing_evidence(tmp_path: Path) -> None:
    manifest_path = tmp_path / "models-list.json"
    manifest_path.write_text(
        json.dumps(
            [
                "lmstudio-community/Qwen3.6-27B-MLX-4bit",
                {"model": "lmstudio-community/Qwen3.6-27B-MLX-4bit"},
            ]
        ),
        encoding="utf-8",
    )

    result = write_trainability_matrix(tmp_path, "missing-run", manifest_path=manifest_path)

    assert [row["model"] for row in result["rows"]] == [
        "lmstudio-community/Qwen3.6-27B-MLX-4bit",
        "lmstudio-community/Qwen3.6-27B-MLX-4bit",
    ]
    assert result["rows"][0]["load_smoke"] == "missing"
    assert result["rows"][0]["lora_smoke"] == "missing"
    assert result["rows"][0]["evidence_paths"] == []

    result_md = (tmp_path / result["result_path"]).read_text(encoding="utf-8")
    assert "only proves bounded model load and minimal trainability checks" in result_md
    assert "does not prove training quality, convergence, benchmark quality, or production readiness" in result_md
    assert (
        "| lmstudio-community/Qwen3.6-27B-MLX-4bit | mlx_lm_text_trainable | "
        "missing | missing | missing | missing |  | missing |"
    ) in result_md


def test_write_trainability_matrix_uses_failure_metadata_when_present(tmp_path: Path) -> None:
    run_dir = tmp_path / ".devflow" / "training" / "fail-run"
    model_dir = run_dir / "models" / model_slug("lmstudio-community/Qwen3.6-27B-MLX-4bit")
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "load-smoke.json").write_text(
        json.dumps({"command": "python load.py", "duration_seconds": 4, "exit_code": 1, "failure_reason": "oom"}),
        encoding="utf-8",
    )

    result = write_trainability_matrix(
        tmp_path,
        "fail-run",
        models=["lmstudio-community/Qwen3.6-27B-MLX-4bit"],
    )

    row = result["rows"][0]
    assert row["load_smoke"] == "fail"
    assert row["lora_smoke"] == "missing"
    assert row["duration_seconds"] == 4
    assert row["exit_code"] == 1
    assert row["failure_reason"] == "oom"

    result_md = (tmp_path / result["result_path"]).read_text(encoding="utf-8")
    assert "| Model | Surface | Load | LoRA | Reload | Exit | Failure | Evidence |" in result_md
    assert "| lmstudio-community/Qwen3.6-27B-MLX-4bit | mlx_lm_text_trainable | fail | missing | missing | 1 | oom |" in result_md
