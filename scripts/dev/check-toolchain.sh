#!/usr/bin/env zsh

set -euo pipefail

echo "node: $(command -v node >/dev/null && node --version || echo missing)"
echo "pnpm: $(command -v pnpm >/dev/null && pnpm --version || echo missing)"
echo "python3: $(command -v python3 >/dev/null && python3 --version || echo missing)"
echo "uv: $(command -v uv >/dev/null && uv --version || echo missing)"
echo "cargo: $(command -v cargo >/dev/null && cargo --version || echo missing)"
if [[ -x "$(cd "$(dirname "$0")/../.." && pwd)/services/python-core/.venv/bin/python" ]]; then
  echo "python-core venv: present"
else
  echo "python-core venv: missing"
fi
