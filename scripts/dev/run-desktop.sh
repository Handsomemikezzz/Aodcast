#!/usr/bin/env zsh
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$repo_root/scripts/dev/run-dev-all.sh" "$@"
