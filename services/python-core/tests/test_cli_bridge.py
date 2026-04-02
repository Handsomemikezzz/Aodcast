from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.main import run
from app.runtime.request_state_store import RequestStateStore


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

    @staticmethod
    def iso_days_ago(days: int) -> str:
        return (datetime.now(UTC) - timedelta(days=days)).isoformat()

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

    def test_rename_session_and_search_query(self) -> None:
        _, created = self.run_bridge(
            "--create-session",
            "--topic",
            "Original topic",
            "--intent",
            "Renaming",
        )
        session_id = created["data"]["project"]["session"]["session_id"]

        code, renamed = self.run_bridge(
            "--rename-session",
            session_id,
            "--session-topic",
            "Renamed session title",
        )
        self.assertEqual(code, 0)
        self.assertEqual(renamed["data"]["project"]["session"]["topic"], "Renamed session title")

        code, listed = self.run_bridge("--list-projects", "--search", "renamed")
        self.assertEqual(code, 0)
        self.assertEqual(len(listed["data"]["projects"]), 1)
        self.assertEqual(
            listed["data"]["projects"][0]["session"]["session_id"],
            session_id,
        )

    def test_soft_deleted_sessions_hidden_unless_include_deleted(self) -> None:
        _, created = self.run_bridge(
            "--create-session",
            "--topic",
            "To delete",
            "--intent",
            "Cleanup",
        )
        session_id = created["data"]["project"]["session"]["session_id"]

        code, deleted = self.run_bridge("--delete-session", session_id)
        self.assertEqual(code, 0)
        self.assertTrue(deleted["data"]["project"]["session"]["deleted_at"])

        code, listed_default = self.run_bridge("--list-projects")
        self.assertEqual(code, 0)
        self.assertEqual(len(listed_default["data"]["projects"]), 0)

        code, listed_with_deleted = self.run_bridge("--list-projects", "--include-deleted")
        self.assertEqual(code, 0)
        self.assertEqual(len(listed_with_deleted["data"]["projects"]), 1)
        self.assertEqual(
            listed_with_deleted["data"]["projects"][0]["session"]["session_id"],
            session_id,
        )

    def test_script_revisions_and_rollback(self) -> None:
        _, created = self.run_bridge(
            "--create-session",
            "--topic",
            "Revision topic",
            "--intent",
            "Revision intent",
        )
        session_id = created["data"]["project"]["session"]["session_id"]

        code, _ = self.run_bridge(
            "--save-script",
            session_id,
            "--script-final-text",
            "Version one",
        )
        self.assertEqual(code, 0)
        code, _ = self.run_bridge(
            "--save-script",
            session_id,
            "--script-final-text",
            "Version two",
        )
        self.assertEqual(code, 0)

        code, listed = self.run_bridge("--list-script-revisions", session_id)
        self.assertEqual(code, 0)
        revisions = listed["data"]["revisions"]
        self.assertGreaterEqual(len(revisions), 1)
        revision = next((item for item in revisions if item["content"] == "Version one"), None)
        self.assertIsNotNone(revision)

        code, rolled_back = self.run_bridge(
            "--rollback-script-revision",
            session_id,
            "--revision-id",
            revision["revision_id"],
        )
        self.assertEqual(code, 0)
        self.assertEqual(rolled_back["data"]["project"]["script"]["final"], "Version one")

    def test_delete_and_restore_script(self) -> None:
        _, created = self.run_bridge(
            "--create-session",
            "--topic",
            "Script delete",
            "--intent",
            "Script delete intent",
        )
        session_id = created["data"]["project"]["session"]["session_id"]
        code, _ = self.run_bridge(
            "--save-script",
            session_id,
            "--script-final-text",
            "Keep me",
        )
        self.assertEqual(code, 0)

        code, deleted = self.run_bridge("--delete-script", session_id)
        self.assertEqual(code, 0)
        self.assertTrue(deleted["data"]["project"]["script"]["deleted_at"])
        self.assertEqual(deleted["data"]["project"]["script"]["final"], "")

        code, restored = self.run_bridge("--restore-script", session_id)
        self.assertEqual(code, 0)
        self.assertEqual(restored["data"]["project"]["script"]["final"], "Keep me")

    def test_restore_session_rejects_expired_deletion(self) -> None:
        _, created = self.run_bridge(
            "--create-session",
            "--topic",
            "Expired session",
            "--intent",
            "Expired restore window",
        )
        session_id = created["data"]["project"]["session"]["session_id"]

        code, deleted = self.run_bridge("--delete-session", session_id)
        self.assertEqual(code, 0)

        project_path = self.cwd / ".local-data" / "sessions" / session_id / "session.json"
        session_payload = json.loads(project_path.read_text(encoding="utf-8"))
        session_payload["deleted_at"] = self.iso_days_ago(31)
        project_path.write_text(json.dumps(session_payload, indent=2) + "\n", encoding="utf-8")

        code, payload = self.run_bridge("--restore-session", session_id)
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertIn("restore window", payload["error"]["message"])

    def test_restore_script_rejects_expired_deletion(self) -> None:
        _, created = self.run_bridge(
            "--create-session",
            "--topic",
            "Expired script",
            "--intent",
            "Expired script restore",
        )
        session_id = created["data"]["project"]["session"]["session_id"]
        code, _ = self.run_bridge(
            "--save-script",
            session_id,
            "--script-final-text",
            "Restore me if you can.",
        )
        self.assertEqual(code, 0)
        code, deleted = self.run_bridge("--delete-script", session_id)
        self.assertEqual(code, 0)

        project_path = self.cwd / ".local-data" / "sessions" / session_id / "script.json"
        script_payload = json.loads(project_path.read_text(encoding="utf-8"))
        script_payload["deleted_at"] = self.iso_days_ago(31)
        project_path.write_text(json.dumps(script_payload, indent=2) + "\n", encoding="utf-8")

        code, payload = self.run_bridge("--restore-script", session_id)
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertIn("restore window", payload["error"]["message"])

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

    def test_cancel_task_marks_running_task_as_cancelling(self) -> None:
        state_store = RequestStateStore(self.cwd / ".local-data")
        state_store.bootstrap()
        state_store.save(
            "render_audio:test-session",
            {
                "operation": "render_audio",
                "phase": "running",
                "progress_percent": 42.0,
                "message": "Rendering...",
            },
        )

        code, payload = self.run_bridge("--cancel-task", "render_audio:test-session")
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["task_id"], "render_audio:test-session")
        self.assertEqual(payload["data"]["task_state"]["phase"], "cancelling")

        code, state_payload = self.run_bridge("--show-task-state", "render_audio:test-session")
        self.assertEqual(code, 0)
        self.assertEqual(state_payload["data"]["task_state"]["phase"], "cancelling")

    def test_cancel_task_keeps_terminal_task_state(self) -> None:
        state_store = RequestStateStore(self.cwd / ".local-data")
        state_store.bootstrap()
        state_store.save(
            "download_model:test-model",
            {
                "operation": "download_model",
                "phase": "succeeded",
                "progress_percent": 100.0,
                "message": "Ready",
            },
        )

        code, payload = self.run_bridge("--cancel-task", "download_model:test-model")
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["task_state"]["phase"], "succeeded")


if __name__ == "__main__":
    unittest.main()
