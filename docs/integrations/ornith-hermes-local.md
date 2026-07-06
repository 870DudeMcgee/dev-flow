# Ornith Hermes-Local Runbook

Status: historical Ornith setup runbook. Current fleet routing is
[docs/fleet-debrief.md](../fleet-debrief.md) and
[docs/fleet-routing-brief.md](../fleet-routing-brief.md): Ornith 35B on `8084`
as scout/builder and Qwen 27B on `8083` as judge. Ornith 9B, Qwopus, and
Qwen3-Coder-Next are retired from active DevFlow routing.

## Profiles

| Hermes profile | Provider | Model id | Port | First context |
|---|---|---|---:|---:|
| `hermes-ornith-35b` | `local-ornith-35b` | `ornith-1.0-35b-q4` | 8084 | 131072 |
| `hermes-ornith-9b` | `local-ornith-9b` | `ornith-1.0-9b-q4` | retired | 131072 |

Ornith 35B is the active scout/builder. Its output is evidence until Dev-Flow
verification passes. Ornith 9B material below is retained only as historical
setup context and must not be used as a fallback route.

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

Run only one heavy local model server at a time. Use
`~/.hermes/scripts/model-router start ornith-35b` and let the router replace
the current resident model. Do not manually start retired Ornith 9B.

Profile-local runner scripts are installed here:

```bash
~/.hermes/profiles/hermes-ornith-35b/local-runners/start-ornith35b.sh
```

The old Ornith 9B command is historical and intentionally omitted. The expanded
Ornith 35B command is:

```bash
llama-server \
  -m ~/.hermes/models/gguf/ornith-1.0-35b-q4/ornith-1.0-35b-Q4_K_M.gguf \
  --alias ornith-1.0-35b-q4 \
  --host 127.0.0.1 \
  --port 8084 \
  --ctx-size 131072 \
  --gpu-layers 99 \
  --flash-attn on \
  --parallel 3 \
  --jinja \
  --chat-template chatml \
  --reasoning auto \
  --temp 0.6 \
  --top-p 0.95 \
  --top-k 20 \
  --no-webui
```

Do not pass llama.cpp `--tools`; built-in tools should stay disabled for this local evidence route.

Use `--chat-template chatml` on Ornith 35B. On July 4, 2026, Codex
custom-agent and Hermes scout requests against Ornith 9B/35B failed with
llama.cpp `HTTP 400` errors:

```text
Unable to generate parser for this template.
Jinja Exception: System message must be at the beginning.
```

Direct single-user-message probes still worked, but any prompt stack containing
a later system message tripped the embedded `peg-native` template. Pinning the
server to ChatML matches the already-repaired Qwopus launcher and keeps local
subagent routing from failing before file access.

The local worker smoke harness also has a strict-output mode. As of the July 4
repair, the Hermes Ornith scout route is clean in strict mode, while the bare
Ornith routes are transport-ready but still return visible `<think>` text. Use
that as an output-discipline signal, not as evidence that ChatML regressed.

## Smoke

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
  --local-hermes-profile hermes-ornith-35b \
  --run-id ornith35b-smoke
```

## Rollback

Use the model-router to swap back to the builder or judge route. Historical
Ornith profile config backups live beside each profile as:

```text
~/.hermes/profiles/hermes-ornith-35b/config.yaml.before-ornith-*.bak
```

Dev-Flow source does not depend on those profiles for execution; removing or disabling them only removes packet-only Hermes visibility.
