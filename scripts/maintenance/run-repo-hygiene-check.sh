#!/usr/bin/env zsh

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
python_bin="$repo_root/services/python-core/.venv/bin/python"
speech_python="$repo_root/speech-service/.venv/bin/python"
skip_speech_checks=false

if [[ "${1:-}" == "--skip-speech-checks" && $# -eq 1 ]]; then
  skip_speech_checks=true
elif [[ $# -ne 0 ]]; then
  echo "Usage: $0 [--skip-speech-checks]" >&2
  exit 2
fi

if [[ ! -x "$python_bin" ]]; then
  python_bin="python3"
fi

echo "== git status =="
git -C "$repo_root" status --short

echo
echo "== placeholder scan =="
if rg -n \
  --glob '!scripts/maintenance/run-repo-hygiene-check.sh' \
  --glob '!apps/desktop/dist/**' \
  --glob '!apps/desktop/node_modules/**' \
  --glob '!apps/desktop/src-tauri/target/**' \
  --glob '!services/python-core/.venv/**' \
  --glob '!speech-service/.venv/**' \
  --glob '!**/.local-data/**' \
  --glob '!**/.cache/**' \
  --glob '!**/.pytest_cache/**' \
  --glob '!**/.ruff_cache/**' \
  --glob '!**/__pycache__/**' \
  "TODO|TBD|FIXME" \
  "$repo_root/AGENTS.md" "$repo_root/README.md" "$repo_root/apps" "$repo_root/services" "$repo_root/speech-service" "$repo_root/scripts" "$repo_root/packages" "$repo_root/examples"; then
  true
else
  echo "No TODO/TBD/FIXME markers found."
fi

echo
echo "== generated directories =="
find "$repo_root/apps" "$repo_root/services" "$repo_root/speech-service" \
  \( -name node_modules -o -name .venv -o -name .local-data -o -name .cache -o -name target \) -prune -o \
  -type d \( -name dist -o -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache \) -print | \
  sed "s|$repo_root/||"

echo
echo "== local speech HTTP capability =="
"$repo_root/scripts/dev/run-python-core.sh" --show-local-tts-capability

echo
echo "== python tests =="
(
  cd "$repo_root/services/python-core"
  "$python_bin" -m unittest discover -s tests -v
)

echo
echo "== speech service tests and lint =="
if $skip_speech_checks; then
  echo "Skipped here; CI verifies speech-service in its separate Python 3.12 job."
else
  if [[ ! -x "$speech_python" ]]; then
    echo "Speech test environment missing. Run: cd '$repo_root/speech-service' && uv sync --frozen --group dev" >&2
    exit 1
  fi
  (
    cd "$repo_root/speech-service"
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$speech_python" -m pytest -q
    "$speech_python" -m ruff check .
  )
fi

echo
echo "== desktop typecheck =="
(
  cd "$repo_root/apps/desktop"
  pnpm check
)

echo
echo "== desktop tests =="
(
  cd "$repo_root/apps/desktop"
  pnpm test
)

echo
echo "== desktop web build =="
(
  cd "$repo_root/apps/desktop"
  pnpm build:web
)
