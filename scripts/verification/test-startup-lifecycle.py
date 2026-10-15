#!/usr/bin/env python3
"""Exercise launcher ordering and health identity without launchd or GPU processes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nset -eu\n" + body)
    path.chmod(0o755)


class StartupLifecycleTests(unittest.TestCase):
    def test_direct_tauri_dev_starts_speech_before_web(self):
        command = json.loads(REPO.joinpath("apps/desktop/src-tauri/tauri.conf.json").read_text())["build"]["beforeDevCommand"]
        with tempfile.TemporaryDirectory(prefix="aodcast-tauri-startup-") as directory:
            root = Path(directory)
            (root / "apps/desktop").mkdir(parents=True)
            target = root / "scripts/dev/ensure-speech-service.sh"
            target.parent.mkdir(parents=True)
            shutil.copy2(REPO / "scripts/dev/ensure-speech-service.sh", target)
            executable(root / "speech-service/service.sh", 'echo "speech:$1" >> "$EVENTS"\n')
            executable(root / "bin/pnpm", 'echo "shell:$*" >> "$EVENTS"\n')
            events = root / "events"
            env = dict(os.environ, PATH=f"{root / 'bin'}:{os.environ['PATH']}", EVENTS=str(events))
            result = subprocess.run(command, shell=True, cwd=root / "apps/desktop", env=env,
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(events.read_text().splitlines(), ["speech:start", "shell:dev:web"])

    def launcher(self, name: str, speech_exit: int) -> list[str]:
        with tempfile.TemporaryDirectory(prefix="aodcast-startup-") as directory:
            root = Path(directory)
            (root / "scripts/dev").mkdir(parents=True)
            (root / "apps/desktop").mkdir(parents=True)
            for source in REPO.joinpath("scripts/dev").glob("*.sh"):
                shutil.copy2(source, root / "scripts/dev" / source.name)
            executable(
                root / "speech-service/service.sh",
                f'echo "speech:$1" >> "$EVENTS"\nexit {speech_exit}\n',
            )
            executable(
                root / "scripts/dev/run-python-core.sh",
                'echo runtime-start >> "$EVENTS"\ntouch "$RUNTIME_MARKER"\nexec sleep 30\n',
            )
            executable(root / "bin/cargo", "exit 0\n")
            executable(root / "bin/lsof", "exit 1\n")
            executable(
                root / "bin/curl",
                'test -f "$RUNTIME_MARKER" || exit 1\necho runtime-ready >> "$EVENTS"\n',
            )
            executable(root / "bin/pnpm", 'echo "shell:$*" >> "$EVENTS"\n')
            events = root / "events"
            env = dict(
                os.environ,
                PATH=f"{root / 'bin'}:{os.environ['PATH']}",
                EVENTS=str(events),
                RUNTIME_MARKER=str(root / "runtime"),
            )
            result = subprocess.run(
                [str(root / "scripts/dev" / name)],
                cwd="/",
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0 if not speech_exit else speech_exit,
                result.stdout + result.stderr,
            )
            return events.read_text().splitlines()

    def test_desktop_starts_speech_then_runtime_then_ui(self):
        for name in ("run-dev-all.sh", "run-desktop.sh"):
            with self.subTest(launcher=name):
                self.assertEqual(
                    self.launcher(name, 0),
                    [
                        "speech:start",
                        "runtime-start",
                        "runtime-ready",
                        "shell:tauri:dev",
                    ],
                )

    def test_web_starts_speech_then_runtime_then_ui(self):
        self.assertEqual(
            self.launcher("run-web-with-runtime.sh", 0),
            ["speech:start", "runtime-start", "runtime-ready", "shell:dev:web"],
        )

    def test_speech_failure_prevents_runtime_and_ui(self):
        for name in ("run-dev-all.sh", "run-web-with-runtime.sh", "run-desktop.sh"):
            with self.subTest(launcher=name):
                self.assertEqual(self.launcher(name, 7), ["speech:start"])


class SpeechHealthTests(unittest.TestCase):
    def probe(self, payload: dict) -> subprocess.CompletedProcess:
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode())

            def log_message(self, *args):
                pass

        # Execute the script's actual probe; avoid starting MLX or a LaunchAgent.
        script = REPO.joinpath("speech-service/service.sh").read_text()
        probe = (
            script.split("check_health() {", 1)[1]
            .split("<<'PY'\n", 1)[1]
            .split("\nPY\n", 1)[0]
        )
        with ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                return subprocess.run(
                    [
                        sys.executable,
                        "-",
                        f"http://127.0.0.1:{server.server_port}/health",
                        "0",
                    ],
                    input=probe,
                    text=True,
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
            finally:
                server.shutdown()
                thread.join(timeout=2)

    def test_lazy_models_are_ready(self):
        result = self.probe(
            {
                "status": "ok",
                "models": {
                    "tts": {"id": "tts", "loaded": False},
                    "asr": {"id": "asr", "loaded": False},
                },
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unrelated_or_malformed_health_is_rejected(self):
        for payload in (
            {"status": "ok"},
            {"status": "ok", "models": {}},
            {"status": "ok", "models": {"tts": {"id": "tts", "loaded": "false"}}},
        ):
            with self.subTest(payload=payload):
                self.assertNotEqual(self.probe(payload).returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
