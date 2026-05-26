#!/usr/bin/env bash
set -euo pipefail

echo "== Local Models Doctor =="

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
echo "3) Docker pull: docker pull ollama/ollama:latest"
echo "4) Docker run: docker run -d --name ollama-local -p 11434:11434 -v \"$HOME/.ollama:/root/.ollama\" ollama/ollama:latest"
echo "5) Pull model (container): docker exec ollama-local ollama pull qwen2.5-coder:1.5b"
echo "6) Generate test: curl -sS http://127.0.0.1:11434/api/generate -d '{\"model\":\"qwen2.5-coder:1.5b\",\"prompt\":\"print hello in python\",\"stream\":false}'"
