#!/usr/bin/env zsh

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
runtime_pid=""
started_runtime=0
force_restart=1
reuse_runtime=0
download_helper_script="$repo_root/scripts/model-download/download_tts_model.py"

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

# Download children use their own session; SIGKILL of the runtime can still leave
# them behind. Reap by script path as a belt-and-suspenders after stopping 8765.
reap_model_download_helpers() {
  local pids
  pids="$(pgrep -f "$download_helper_script" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true)"
  [[ -z "$pids" ]] && return

  echo "Stopping orphaned model downloads (pid: $pids) ..."
  kill ${=pids} >/dev/null 2>&1 || true
  for _ in {1..30}; do
    pids="$(pgrep -f "$download_helper_script" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true)"
    [[ -z "$pids" ]] && return
    sleep 0.1
  done

  pids="$(pgrep -f "$download_helper_script" 2>/dev/null | tr '\n' ' ' | sed 's/[[:space:]]*$//' || true)"
  if [[ -n "$pids" ]]; then
    echo "Model downloads still running; sending SIGKILL (pid: $pids) ..." >&2
    kill -9 ${=pids} >/dev/null 2>&1 || true
  fi
}

stop_port() {
  local port="$1"
  local label="$2"
  local pids="$(port_pids "$port" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  [[ -z "$pids" ]] && return

  echo "Stopping $label on port $port (pid: $pids) ..."
  # SIGTERM lets python-core's stop handler reclaim download process groups.
  kill ${=pids} >/dev/null 2>&1 || true
  for _ in {1..50}; do
    [[ -z "$(port_pids "$port")" ]] && break
    sleep 0.1
  done

  pids="$(port_pids "$port" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  if [[ -n "$pids" ]]; then
    echo "Port $port still busy; sending SIGKILL (pid: $pids) ..." >&2
    kill -9 ${=pids} >/dev/null 2>&1 || true
  fi

  if [[ "$port" == "8765" ]]; then
    reap_model_download_helpers
  fi
}

cleanup() {
  if [[ "$started_runtime" -eq 1 && -n "$runtime_pid" ]] && kill -0 "$runtime_pid" >/dev/null 2>&1; then
    kill "$runtime_pid" >/dev/null 2>&1 || true
    for _ in {1..30}; do
      kill -0 "$runtime_pid" >/dev/null 2>&1 || break
      sleep 0.1
    done
    if kill -0 "$runtime_pid" >/dev/null 2>&1; then
      kill -9 "$runtime_pid" >/dev/null 2>&1 || true
    fi
  fi
  reap_model_download_helpers
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
require_cmd pgrep

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
