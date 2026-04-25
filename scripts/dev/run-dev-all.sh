#!/usr/bin/env zsh

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
runtime_pid=""
started_runtime=0
force_restart=1
reuse_runtime=0

usage() {
  echo "Usage: ./scripts/dev/run-dev-all.sh [--restart-runtime|--reuse-runtime]" >&2
}

die() {
  echo "$1" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "$1 is required but not found."
}

runtime_ready() {
  curl -sf "http://127.0.0.1:8765/healthz" >/dev/null 2>&1
}

port_pids() {
  lsof -ti "tcp:$1" 2>/dev/null || true
}

stop_port() {
  local port="$1"
  local label="$2"
  local pids="$(port_pids "$port" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  [[ -z "$pids" ]] && return

  echo "Stopping $label on port $port (pid: $pids) ..."
  kill ${=pids} >/dev/null 2>&1 || true
  for _ in {1..50}; do
    [[ -z "$(port_pids "$port")" ]] && return
    sleep 0.1
  done

  pids="$(port_pids "$port" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  if [[ -n "$pids" ]]; then
    echo "Port $port still busy; sending SIGKILL (pid: $pids) ..." >&2
    kill -9 ${=pids} >/dev/null 2>&1 || true
  fi
}

cleanup() {
  if [[ "$started_runtime" -eq 1 && -n "$runtime_pid" ]] && kill -0 "$runtime_pid" >/dev/null 2>&1; then
    kill "$runtime_pid" >/dev/null 2>&1 || true
  fi
}

for arg in "$@"; do
  case "$arg" in
    --restart-runtime) force_restart=1; reuse_runtime=0 ;;
    --reuse-runtime) force_restart=0; reuse_runtime=1 ;;
    *) usage; die "Unknown argument: $arg" ;;
  esac
done

trap cleanup EXIT INT TERM
require_cmd cargo
require_cmd curl
require_cmd lsof

echo "Checking backend runtime at 127.0.0.1:8765 ..."
[[ "$force_restart" -eq 1 ]] && stop_port 8765 "backend runtime"

if [[ "$reuse_runtime" -eq 1 ]] && runtime_ready; then
  echo "Runtime already running; reusing existing process."
else
  echo "Starting backend runtime ..."
  "$repo_root/scripts/dev/run-python-core.sh" --serve-http --host 127.0.0.1 --port 8765 >/dev/null 2>&1 &
  runtime_pid="$!"
  started_runtime=1

  ready=0
  for _ in {1..40}; do
    if runtime_ready; then
      ready=1
      break
    fi
    sleep 0.25
  done
  [[ "$ready" -eq 1 ]] || die "Failed to start backend runtime on 127.0.0.1:8765."
fi

# Tauri starts Vite immediately; clear stale dev servers so the new one binds cleanly.
stop_port 1420 "stale dev server"

echo "Launching desktop app + web dev server ..."
echo "Web URL: http://localhost:1420"
cd "$repo_root/apps/desktop"
pnpm tauri:dev
