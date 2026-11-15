#!/usr/bin/env zsh

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"

die() {
  echo "$1" >&2
  exit 1
}

port_pids() {
  lsof -ti "tcp:$1" 2>/dev/null || true
}

# Tauri starts Vite immediately; clear a stale dev server so the new one binds cleanly.
stop_stale_dev_server() {
  local pids="$(port_pids 1420 | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
  [[ -z "$pids" ]] && return

  echo "Stopping stale dev server on port 1420 (pid: $pids) ..."
  kill ${=pids} >/dev/null 2>&1 || true
  for _ in {1..50}; do
    [[ -z "$(port_pids 1420)" ]] && return
    sleep 0.1
  done
  kill -9 $(port_pids 1420) >/dev/null 2>&1 || true
}

command -v cargo >/dev/null 2>&1 || die "cargo is required but not found."
command -v lsof >/dev/null 2>&1 || die "lsof is required but not found."

"$repo_root/scripts/dev/ensure-speech-service.sh"
stop_stale_dev_server

# The Tauri shell spawns its own orchestration runtime on a free localhost port.
echo "Launching desktop app + web dev server ..."
echo "Web URL: http://localhost:1420"
cd "$repo_root/apps/desktop"
pnpm tauri:dev
