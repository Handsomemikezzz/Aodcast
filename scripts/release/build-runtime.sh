#!/usr/bin/env zsh
# Freeze the orchestration runtime (services/python-core) with PyInstaller (onedir)
# into apps/desktop/src-tauri/resources/aodcast-runtime, which the release Tauri
# config ships as a bundle resource. PyInstaller is a build-time tool only.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
core="$repo_root/services/python-core"
out="$repo_root/apps/desktop/src-tauri/resources"
work="$repo_root/services/python-core/build/pyinstaller"

rm -rf "$out/aodcast-runtime" "$work"
mkdir -p "$out"

cd "$core"
uv run --python 3.13 --with pyinstaller pyinstaller \
  --noconfirm --clean --onedir \
  --name aodcast-runtime \
  --paths "$core" \
  --collect-submodules app \
  --collect-all miniaudio \
  --hidden-import _cffi_backend \
  --add-data "$core/app/assets:app/assets" \
  --distpath "$out" \
  --workpath "$work" \
  --specpath "$work" \
  app/main.py

echo "Runtime: $out/aodcast-runtime/aodcast-runtime"
