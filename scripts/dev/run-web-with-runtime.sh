#!/usr/bin/env zsh

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
runtime_pid=""

cleanup() {
  if [[ -n "${runtime_pid}" ]]; then
    if kill -0 "${runtime_pid}" >/dev/null 2>&1; then
      kill "${runtime_pid}" >/dev/null 2>&1 || true
    fi
  fi
}

trap cleanup EXIT INT TERM

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required but not found." >&2
  exit 1
fi

echo "Starting local HTTP runtime (127.0.0.1:8765)..."
"$repo_root/scripts/dev/run-python-core.sh" --serve-http --host 127.0.0.1 --port 8765 >/dev/null 2>&1 &
runtime_pid="$!"

ready=0
for _ in {1..40}; do
  if curl -sf "http://127.0.0.1:8765/healthz" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.25
done

if [[ "$ready" -ne 1 ]]; then
  echo "Failed to start HTTP runtime on 127.0.0.1:8765." >&2
  exit 1
fi

echo "Runtime ready. Launching web shell at http://localhost:1420 ..."
cd "$repo_root/apps/desktop"
pnpm dev:web
