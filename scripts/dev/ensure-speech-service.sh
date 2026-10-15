#!/bin/bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
echo "Starting bundled speech service before the runtime and shell ..."
"$repo_root/speech-service/service.sh" start
# This shared launchd service intentionally stays available after the UI exits.
