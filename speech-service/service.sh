#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.aodcast.speech-service"
DOMAIN="gui/$(id -u)"
TARGET="$DOMAIN/$LABEL"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/Aodcast/speech-service"
PYTHON="$ROOT/.venv/bin/python"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"

require_macos() {
  if [[ "$(uname -s)" != Darwin || "$(uname -m)" != arm64 ]]; then
    echo "Requires an Apple Silicon Mac and a native arm64 terminal." >&2
    exit 1
  fi
}

is_loaded() {
  launchctl print "$TARGET" >/dev/null 2>&1
}

ensure_environment() {
  if [[ ! -x "$PYTHON" ]] || ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))'; then
    command -v uv >/dev/null || { echo "Install uv first." >&2; exit 1; }
    (cd "$ROOT" && uv sync --python 3.12 --frozen --no-dev)
  fi
}

load_binding() {
  # Match the service's dotenv precedence without executing .env as shell code.
  local binding
  binding="$("$PYTHON" - "$ROOT" <<'PY'
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(sys.argv[1], ".env"), override=False)
host, port = os.getenv("HOST", "127.0.0.1"), int(os.getenv("PORT", "8090"))
if not host or any(c.isspace() for c in host) or not 1 <= port <= 65535:
    raise SystemExit("Invalid HOST or PORT in speech-service/.env")
print(host, port, os.getenv("TTS_MODEL", ""))
PY
)"
  read -r BIND_HOST BIND_PORT MODEL <<< "$binding"
  HEALTH_HOST="$BIND_HOST"
  case "$HEALTH_HOST" in
    0.0.0.0) HEALTH_HOST=127.0.0.1 ;;
    ::) HEALTH_HOST=::1 ;;
  esac
  [[ "$HEALTH_HOST" != *:* ]] || HEALTH_HOST="[$HEALTH_HOST]"
  HEALTH_URL="http://$HEALTH_HOST:$BIND_PORT/health"
}

check_health() {
  "$PYTHON" - "$HEALTH_URL" "$1" <<'PY'
import json
import sys
import time
from urllib.request import ProxyHandler, build_opener

url, wait = sys.argv[1], float(sys.argv[2])
deadline = time.monotonic() + wait
opener = build_opener(ProxyHandler({}))
while True:
    try:
        with opener.open(url, timeout=1) as response:
            data = json.load(response)
        assert data.get("status") == "ok"
        for kind in ("tts", "asr"):
            model = data["models"][kind]
            assert isinstance(model["id"], str) and model["id"]
            assert isinstance(model["loaded"], bool)
        break
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        if time.monotonic() >= deadline:
            raise SystemExit(1)
        time.sleep(0.5)
PY
}

render_plist() {
  mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"
  "$PYTHON" - "$ROOT" "$PLIST" "$LOG_DIR" "$PATH" "$BIND_HOST" "$BIND_PORT" <<'PY'
import os
import plistlib
import sys
from pathlib import Path
from xml.sax.saxutils import escape

root, target, logs, path, host, port = sys.argv[1:]
source = Path(root, "launchd/com.aodcast.speech-service.plist.template").read_text()
values = {"ROOT": root, "PYTHON": str(Path(root, ".venv/bin/python")), "PATH": path,
          "HOST": host, "PORT": port,
          "LOG": str(Path(logs, "server.log")), "ERROR_LOG": str(Path(logs, "error.log"))}
for key, value in values.items():
    source = source.replace("@@" + key + "@@", escape(value))
data = plistlib.loads(source.encode())
target = Path(target)
if target.exists():
    existing = plistlib.loads(target.read_bytes())
    if existing.get("WorkingDirectory") != root:
        raise SystemExit(f"Refusing to overwrite a service installed from {existing.get('WorkingDirectory')}")
temporary = target.with_suffix(".plist.tmp")
temporary.write_bytes(plistlib.dumps(data))
temporary.chmod(0o600)
os.replace(temporary, target)
PY
  plutil -lint "$PLIST"
}

start_service() {
  ensure_environment
  load_binding
  if [[ "$MODEL" == "mlx-community/Kokoro-82M-bf16" ]]; then
    command -v uv >/dev/null || { echo "Install uv to enable the Kokoro extra." >&2; exit 1; }
    (cd "$ROOT" && uv sync --python 3.12 --frozen --no-dev --extra kokoro)
  fi
  command -v ffmpeg >/dev/null || { echo "Run: brew install ffmpeg" >&2; exit 1; }
  if is_loaded; then
    if check_health 0; then
      echo "Speech service already healthy: $HEALTH_URL (models load lazily)."
      return
    fi
    launchctl enable "$TARGET"
    launchctl kickstart "$TARGET"
  else
    render_plist
    launchctl enable "$TARGET"
    launchctl bootstrap "$DOMAIN" "$PLIST"
  fi
  echo "Waiting for speech service: $HEALTH_URL ..."
  if ! check_health 60; then
    echo "Speech service did not become healthy within 60s. Run $0 restart after changing HOST/PORT." >&2
    echo "Logs: $LOG_DIR" >&2
    tail -n 30 "$LOG_DIR/server.log" "$LOG_DIR/error.log" >&2 || true
    return 1
  fi
  echo "Speech service ready: $HEALTH_URL (models load lazily)."
}

stop_service() {
  local service_pid=""
  if is_loaded; then
    service_pid="$(launchctl print "$TARGET" | awk '/^[[:space:]]*pid = / {print $3; exit}')"
    launchctl bootout "$TARGET"
  fi
  # Prevent the saved LaunchAgent from starting again on the next login.
  launchctl disable "$TARGET"
  if [[ -n "$service_pid" ]]; then
    local seconds=0
    while kill -0 "$service_pid" 2>/dev/null; do
      if (( seconds >= 125 )); then
        echo "Process $service_pid is still exiting; refusing to start a second inference process." >&2
        exit 1
      fi
      sleep 1
      seconds=$((seconds + 1))
    done
  fi
  echo "Stopped and disabled: $LABEL"
}

require_macos
case "${1:-}" in
  start) start_service ;;
  stop) stop_service ;;
  restart) stop_service; start_service ;;
  status)
    if is_loaded; then
      launchctl print "$TARGET" | sed -n '/state =/p; /pid =/p; /last exit code =/p'
      [[ -x "$PYTHON" ]] || { echo "Missing environment: $PYTHON" >&2; exit 1; }
      load_binding
      check_health 0 || { echo "Registered but unhealthy: $HEALTH_URL" >&2; exit 1; }
      echo "Healthy: $HEALTH_URL"
    else
      echo "Stopped: $LABEL"
      exit 1
    fi
    ;;
  logs)
    mkdir -p "$LOG_DIR"
    touch "$LOG_DIR/server.log" "$LOG_DIR/error.log"
    tail -n 100 -F "$LOG_DIR/server.log" "$LOG_DIR/error.log"
    ;;
  *) echo "Usage: $0 {start|stop|restart|status|logs}"; exit 2 ;;
esac
