from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from app.domain.artifact import ArtifactRecord
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord, SessionState
from app.main import run
from app.storage.project_store import ProjectStore
from app.config import AppConfig


class VoiceStudioCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, list[dict[str, object]]]:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = run(list(args))
        payloads = []
        for line in stdout.getvalue().splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            payloads.append(json.loads(line))
        return code, payloads

    def test_list_voice_presets_outputs_catalog_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            code, payloads = self.run_cli("--cwd", tmp_dir, "--list-voice-presets")

        self.assertEqual(code, 0)
        self.assertTrue(payloads)
        payload = payloads[-1]
        self.assertEqual(payload["request_state"]["operation"], "list_voice_presets")
        self.assertGreaterEqual(len(payload["voices"]), 5)
        self.assertGreaterEqual(len(payload["styles"]), 4)
        self.assertIsInstance(payload["standard_preview_text"], str)

    def test_render_voice_take_outputs_take_payload_for_latest_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AppConfig.from_cwd(Path(tmp_dir))
            store = ProjectStore(config.data_dir)
            store.bootstrap()
            session = SessionRecord(topic="CLI take", creation_intent="Render latest script")
            session.transition(SessionState.SCRIPT_EDITED)
            script = ScriptRecord(session_id=session.session_id, script_id="script-cli", draft="Draft", final="Final")
            store.save_project(SessionProject(session=session, script=script, artifact=ArtifactRecord(session_id=session.session_id)))

            with patch("app.providers.tts_api.mock_remote.synthesize_sine_wave_bytes", return_value=b"audio"):
                code, payloads = self.run_cli("--cwd", tmp_dir, "--render-voice-take", session.session_id)

        self.assertEqual(code, 0)
        self.assertTrue(payloads)
        payload = payloads[-1]
        self.assertEqual(payload["request_state"]["operation"], "render_voice_take")
        self.assertEqual(payload["take"]["script_id"], "script-cli")


if __name__ == "__main__":
    unittest.main()
