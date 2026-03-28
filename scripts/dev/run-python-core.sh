#!/usr/bin/env zsh

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"

cd "$repo_root/services/python-core"
python3 -m app.main --cwd "$repo_root" "$@"
