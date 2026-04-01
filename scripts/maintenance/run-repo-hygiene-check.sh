#!/usr/bin/env zsh

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
python_bin="$repo_root/services/python-core/.venv/bin/python"

if [[ ! -x "$python_bin" ]]; then
  python_bin="python3"
fi

echo "== git status =="
git -C "$repo_root" status --short

echo
echo "== placeholder scan =="
if rg -n --glob '!scripts/maintenance/run-repo-hygiene-check.sh' "TODO|TBD|FIXME" "$repo_root/AGENTS.md" "$repo_root/README.md" "$repo_root/docs" "$repo_root/apps" "$repo_root/services" "$repo_root/scripts" "$repo_root/packages" "$repo_root/examples"; then
  true
else
  echo "No TODO/TBD/FIXME markers found."
fi

echo
echo "== generated directories =="
find "$repo_root/apps" "$repo_root/services" \
  \( -path '*/node_modules' -o -path '*/.venv' \) -prune -o \
  -type d \( -name dist -o -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache \) -print | \
  sed "s|$repo_root/||"

echo
echo "== local MLX capability =="
"$repo_root/scripts/dev/run-python-core.sh" --show-local-tts-capability

echo
echo "== python tests =="
(
  cd "$repo_root/services/python-core"
  "$python_bin" -m unittest discover -s tests -v
)

echo
echo "== desktop typecheck =="
(
  cd "$repo_root/apps/desktop"
  pnpm check
)

echo
echo "== desktop web build =="
(
  cd "$repo_root/apps/desktop"
  pnpm build:web
)
