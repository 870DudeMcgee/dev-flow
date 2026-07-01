# Ornith Hermes-Local Runbook

Status: Hermes-first local model integration guidance. Ornith is read-only evidence in this slice; Dev-Flow does not register it as a direct `agent run`, patch-proposer, verifier, promotion, merge, or push runtime.

## Profiles

| Hermes profile | Provider | Model id | Port | First context |
|---|---|---|---:|---:|
| `hermes-ornith-35b` | `local-ornith-35b` | `ornith-1.0-35b-q4` | 8084 | 65536 |
| `hermes-ornith-9b` | `local-ornith-9b` | `ornith-1.0-9b-q4` | 8085 | 131072 |

Both profiles are Hermes packet-only from Dev-Flow's point of view. They may prepare or review bounded Dev-Flow packets through Hermes, but their output is evidence until Dev-Flow verification passes.

## Download

```bash
mkdir -p ~/.hermes/models/gguf/ornith-1.0-9b-q4
curl -L --fail --continue-at - \
  -o ~/.hermes/models/gguf/ornith-1.0-9b-q4/ornith-1.0-9b-Q4_K_M.gguf \
  https://huggingface.co/deepreinforce-ai/Ornith-1.0-9B-GGUF/resolve/main/ornith-1.0-9b-Q4_K_M.gguf
```

```bash
mkdir -p ~/.hermes/models/gguf/ornith-1.0-35b-q4
curl -L --fail --continue-at - \
  -o ~/.hermes/models/gguf/ornith-1.0-35b-q4/ornith-1.0-35b-Q4_K_M.gguf \
  https://huggingface.co/deepreinforce-ai/Ornith-1.0-35B-GGUF/resolve/main/ornith-1.0-35b-Q4_K_M.gguf
```

Q4_K_M is the first quant. Do not switch to Q5_K_M until Q4 has useful smoke evidence.

## Serve

Run only one heavy local model server at a time. Stop or replace the current Qwen/Gemma/Ornith server before starting `hermes-ornith-35b`.

Profile-local runner scripts are installed here:

```bash
~/.hermes/profiles/hermes-ornith-9b/local-runners/start-ornith9b.sh
~/.hermes/profiles/hermes-ornith-35b/local-runners/start-ornith35b.sh
```

The expanded commands are:

```bash
llama-server \
  -m ~/.hermes/models/gguf/ornith-1.0-9b-q4/ornith-1.0-9b-Q4_K_M.gguf \
  --alias ornith-1.0-9b-q4 \
  --host 127.0.0.1 \
  --port 8085 \
  --ctx-size 131072 \
  --gpu-layers 99 \
  --flash-attn on \
  --parallel 1 \
  --jinja \
  --reasoning auto \
  --temp 0.6 \
  --top-p 0.95 \
  --top-k 20 \
  --no-webui
```

```bash
llama-server \
  -m ~/.hermes/models/gguf/ornith-1.0-35b-q4/ornith-1.0-35b-Q4_K_M.gguf \
  --alias ornith-1.0-35b-q4 \
  --host 127.0.0.1 \
  --port 8084 \
  --ctx-size 65536 \
  --gpu-layers 99 \
  --flash-attn on \
  --parallel 1 \
  --jinja \
  --reasoning auto \
  --temp 0.6 \
  --top-p 0.95 \
  --top-k 20 \
  --no-webui
```

Do not pass llama.cpp `--tools`; built-in tools should stay disabled for this local evidence route.

## Smoke

```bash
curl http://127.0.0.1:8085/v1/models
hermes -p hermes-ornith-9b chat -q "Reply with exactly: ornith9b smoke ok"
```

```bash
curl http://127.0.0.1:8084/v1/models
hermes -p hermes-ornith-35b chat -q "Reply with exactly: ornith35b smoke ok"
```

Store bounded evidence from `<repo-root>`:

```bash
env PYTHONPATH=src:. .venv/bin/python scripts/hermes_profile_smoke.py \
  --skip-gpt \
  --skip-direct-local \
  --try-local-hermes \
  --local-hermes-profile hermes-ornith-9b \
  --run-id ornith9b-smoke
```

Repeat with `--local-hermes-profile hermes-ornith-35b --run-id ornith35b-smoke` only after the 35B server is active.

## Rollback

Stop the Ornith `llama-server` process, then restore the prior local route by starting the Qwen GGUF server or using the existing `hermes-qwen32-latest` profile. Ornith profile config backups live beside each profile as:

```text
~/.hermes/profiles/hermes-ornith-9b/config.yaml.before-ornith-*.bak
~/.hermes/profiles/hermes-ornith-35b/config.yaml.before-ornith-*.bak
```

Dev-Flow source does not depend on those profiles for execution; removing or disabling them only removes packet-only Hermes visibility.
