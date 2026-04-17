#!/usr/bin/env zsh

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
runtime_pid=""
started_runtime=0

cleanup() {
  if [[ "$started_runtime" -eq 1 && -n "${runtime_pid}" ]]; then
    if kill -0 "${runtime_pid}" >/dev/null 2>&1; then
      kill "${runtime_pid}" >/dev/null 2>&1 || true
    fi
  fi
}

trap cleanup EXIT INT TERM

if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo is required to run the Tauri desktop shell." >&2
  echo "Install the Rust toolchain first, then rerun this script." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required but not found." >&2
  exit 1
fi

echo "Checking backend runtime at 127.0.0.1:8765 ..."
if curl -sf "http://127.0.0.1:8765/healthz" >/dev/null 2>&1; then
  echo "Runtime already running; reusing existing process."
else
  echo "Starting backend runtime ..."
  "$repo_root/scripts/dev/run-python-core.sh" --serve-http --host 127.0.0.1 --port 8765 >/dev/null 2>&1 &
  runtime_pid="$!"
  started_runtime=1

  ready=0
  for _ in {1..40}; do
    if curl -sf "http://127.0.0.1:8765/healthz" >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 0.25
  done

  if [[ "$ready" -ne 1 ]]; then
    echo "Failed to start backend runtime on 127.0.0.1:8765." >&2
    exit 1
  fi
fi

echo "Launching desktop app + web dev server ..."
echo "Web URL: http://localhost:1420"
cd "$repo_root/apps/desktop"
pnpm tauri:dev
