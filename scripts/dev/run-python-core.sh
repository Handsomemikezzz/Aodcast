#!/usr/bin/env zsh

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
python_bin="$repo_root/services/python-core/.venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  python_bin="python3"
fi

cd "$repo_root/services/python-core"
"$python_bin" -m app.main --cwd "$repo_root" "$@"
