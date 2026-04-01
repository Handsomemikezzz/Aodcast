from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from app.main import run


class BridgeCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_bridge(self, *args: str) -> tuple[int, dict[str, object]]:
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = run(["--cwd", str(self.cwd), "--bridge-json", *args])
        return code, json.loads(stream.getvalue())

    def test_create_list_and_show_session_use_bridge_envelope(self) -> None:
        code, created = self.run_bridge(
            "--create-session",
            "--topic",
            "Bridge topic",
            "--intent",
            "Bridge intent",
        )
        self.assertEqual(code, 0)
        self.assertTrue(created["ok"])
        self.assertEqual(created["data"]["request_state"]["operation"], "create_session")
        self.assertEqual(created["data"]["request_state"]["phase"], "succeeded")
        project = created["data"]["project"]

        code, listed = self.run_bridge("--list-projects")
        self.assertEqual(code, 0)
        self.assertEqual(len(listed["data"]["projects"]), 1)
        self.assertEqual(
            listed["data"]["projects"][0]["session"]["session_id"],
            project["session"]["session_id"],
        )

        code, shown = self.run_bridge("--show-session", project["session"]["session_id"])
        self.assertEqual(code, 0)
        self.assertEqual(
            shown["data"]["project"]["session"]["topic"],
            "Bridge topic",
        )

    def test_save_script_updates_state(self) -> None:
        _, created = self.run_bridge(
            "--create-session",
            "--topic",
            "Draft topic",
            "--intent",
            "Draft intent",
        )
        session_id = created["data"]["project"]["session"]["session_id"]

        code, saved = self.run_bridge(
            "--save-script",
            session_id,
            "--script-final-text",
            "Edited final script body.",
        )
        self.assertEqual(code, 0)
        self.assertEqual(saved["data"]["request_state"]["operation"], "save_script")
        self.assertEqual(
            saved["data"]["project"]["script"]["final"],
            "Edited final script body.",
        )
        self.assertEqual(
            saved["data"]["project"]["session"]["state"],
            "script_edited",
        )

    def test_bridge_errors_return_error_envelope(self) -> None:
        code, payload = self.run_bridge("--show-session", "missing-session")
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "python_core_error")
        self.assertEqual(payload["request_state"]["operation"], "show_session")
        self.assertEqual(payload["request_state"]["phase"], "failed")
        self.assertEqual(
            payload["error"]["details"]["request_state"]["operation"],
            "show_session",
        )

    def test_show_task_state_returns_none_when_missing(self) -> None:
        code, payload = self.run_bridge("--show-task-state", "missing-task-id")
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["task_id"], "missing-task-id")
        self.assertIsNone(payload["data"]["task_state"])

    def test_download_failure_persists_failed_task_state(self) -> None:
        # temp cwd has no download helper script, so this call fails deterministically.
        code, payload = self.run_bridge("--download-model", "qwen-tts-0.6B")
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])

        code, state_payload = self.run_bridge("--show-task-state", "download_model:qwen-tts-0.6B")
        self.assertEqual(code, 0)
        task_state = state_payload["data"]["task_state"]
        self.assertEqual(task_state["operation"], "download_model")
        self.assertEqual(task_state["phase"], "failed")


if __name__ == "__main__":
    unittest.main()
