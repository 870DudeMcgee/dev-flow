#!/usr/bin/env bash
set -euo pipefail

# Parse profile from environment or CLI argument
PROFILE="${LOCAL_AI_PROFILE:-}"
while [[ $# -gt 0 ]]; do
  case $1 in
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    *)
      shift
      ;;
  esac
done

DETECTED=false
if [[ -z "$PROFILE" ]]; then
  DETECTED=true
  if command -v sysctl >/dev/null 2>&1; then
    MEM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
    if [[ $MEM_BYTES -gt 34359738368 ]]; then
      PROFILE="studio"
    elif [[ $MEM_BYTES -gt 8589934592 ]]; then
      PROFILE="mini"
    else
      PROFILE="baseline"
    fi
  else
    PROFILE="baseline"
  fi
fi

# Resolve profile to model name
MODEL="qwen2.5-coder:1.5b"
if [[ "$PROFILE" == "studio" ]]; then
  MODEL="qwen2.5-coder:32b-instruct"
elif [[ "$PROFILE" == "mini" ]]; then
  MODEL="qwen2.5-coder:14b"
elif [[ "$PROFILE" == "mini-fast" ]]; then
  MODEL="qwen2.5-coder:7b-instruct"
elif [[ "$PROFILE" == "baseline" ]]; then
  MODEL="qwen2.5-coder:1.5b"
else
  MODEL="$PROFILE"
  PROFILE="custom"
fi

echo "== Local Models Doctor == "
if [[ "$DETECTED" == "true" ]]; then
  echo "Active Profile: $PROFILE (auto-detected)"
else
  echo "Active Profile: $PROFILE"
fi
echo "Target Model: $MODEL"
echo


if command -v ollama >/dev/null 2>&1; then
  echo "[ok] ollama CLI found in PATH: $(command -v ollama)"
else
  if [[ -x "$HOME/.local/bin/ollama" ]]; then
    echo "[ok] ollama CLI found at $HOME/.local/bin/ollama"
    export PATH="$HOME/.local/bin:$PATH"
  else
    echo "[warn] ollama CLI not found"
  fi
fi

echo "-- API check (native/runtime on 127.0.0.1:11434)"
if curl -sS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  echo "[ok] Ollama API reachable"
  curl -sS http://127.0.0.1:11434/api/version
else
  echo "[warn] Ollama API not reachable"
fi

echo
echo "-- Docker fallback check"
if command -v docker >/dev/null 2>&1; then
  docker version --format 'Docker server: {{.Server.Version}}' || true
  if docker images --format '{{.Repository}}:{{.Tag}}' | grep -q '^ollama/ollama:latest$'; then
    echo "[ok] docker image ollama/ollama:latest already present"
  else
    echo "[info] docker image ollama/ollama:latest not present"
  fi
else
  echo "[warn] docker not installed"
fi

echo
echo "-- Recommended commands"
echo "1) Native app launch: open \"$HOME/Applications/Ollama.app\""
echo "2) Native API test: curl -sS http://127.0.0.1:11434/api/version"
echo "3) Pull model (native): ollama pull $MODEL"
echo "4) Docker run: docker run -d --name ollama-local -p 11434:11434 -v \"$HOME/.ollama:/root/.ollama\" ollama/ollama:latest"
echo "5) Pull model (container): docker exec -it ollama-local ollama pull $MODEL"
echo "6) Generate test: curl -sS http://127.0.0.1:11434/api/generate -d '{\"model\":\"$MODEL\",\"prompt\":\"print hello in python\",\"stream\":false}'"
