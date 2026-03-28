#!/usr/bin/env zsh

set -euo pipefail

if ! command -v cargo >/dev/null 2>&1; then
  echo "cargo is required to run the Tauri desktop shell." >&2
  echo "Install the Rust toolchain first, then rerun this script." >&2
  exit 1
fi

cd "$(dirname "$0")/../../apps/desktop"
pnpm tauri:dev
