#!/usr/bin/env zsh
# Build the installable macOS arm64 DMG: frozen runtime -> Tauri bundle -> ad-hoc codesign.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
desktop="$repo_root/apps/desktop"
bundle_dir="$desktop/src-tauri/target/release/bundle"

"$repo_root/scripts/release/build-runtime.sh"

cd "$desktop"
pnpm install --frozen-lockfile
pnpm tauri:build --config src-tauri/tauri.release.conf.json --bundles app,dmg

# No Developer ID: tauri.release.conf.json ad-hoc signs ("-") the app before it goes into the DMG.
app="$bundle_dir/macos/Aodcast.app"
codesign --verify --deep --strict "$app"

dmg="$(ls -t "$bundle_dir"/dmg/Aodcast_*.dmg | head -n 1)"
echo "DMG: $dmg"
