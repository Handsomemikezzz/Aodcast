from __future__ import annotations

import tempfile
import threading
import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.runtime.request_state_store import RequestStateStore


class RequestStateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / ".local-data"
        self.store = RequestStateStore(self.data_dir)
        self.store.bootstrap()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_save_if_current_phase_prevents_regression(self) -> None:
        task_id = "render_audio:test"
        self.store.save(
            task_id,
            {
                "operation": "render_audio",
                "phase": "running",
                "progress_percent": 20.0,
                "message": "running",
            },
        )
        self.store.save(
            task_id,
            {
                "operation": "render_audio",
                "phase": "cancelling",
                "progress_percent": 20.0,
                "message": "cancelling",
            },
        )

        updated = self.store.save_if_current_phase(
            task_id,
            {
                "operation": "render_audio",
                "phase": "running",
                "progress_percent": 21.0,
                "message": "running-again",
            },
            allowed_phases={"running"},
        )

        self.assertFalse(updated)
        state = self.store.load(task_id)
        self.assertIsNotNone(state)
        self.assertEqual(state["phase"], "cancelling")

    def test_concurrent_save_does_not_raise_tempfile_races(self) -> None:
        task_id = "download_model:test"
        failures: list[Exception] = []

        def worker(worker_id: int) -> None:
            try:
                for step in range(80):
                    self.store.save(
                        task_id,
                        {
                            "operation": "download_model",
                            "phase": "running",
                            "progress_percent": float((worker_id + step) % 100),
                            "message": f"worker-{worker_id}",
                        },
                    )
            except Exception as exc:  # pragma: no cover
                failures.append(exc)

        threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual([], failures)
        self.assertIsNotNone(self.store.load(task_id))

    def test_safe_task_file_name_keeps_similarly_normalized_tasks_separate(self) -> None:
        task_id_one = "render_audio:" + ("a" * 260) + "-one"
        task_id_two = "render_audio:" + ("a" * 260) + "-two"

        self.store.save(
            task_id_one,
            {
                "operation": "render_audio",
                "phase": "running",
                "progress_percent": 10.0,
                "message": "first",
            },
        )
        self.store.save(
            task_id_two,
            {
                "operation": "render_audio",
                "phase": "running",
                "progress_percent": 20.0,
                "message": "second",
            },
        )

        path_one = self.store._path(task_id_one)
        path_two = self.store._path(task_id_two)
        self.assertNotEqual(path_one, path_two)
        self.assertEqual(self.store.load(task_id_one)["message"], "first")
        self.assertEqual(self.store.load(task_id_two)["message"], "second")

    def test_cleanup_terminal_states_removes_only_old_prefixed_terminal_tasks(self) -> None:
        old_preview = "render_voice_preview:old"
        fresh_preview = "render_voice_preview:fresh"
        running_preview = "render_voice_preview:running"
        other_task = "render_audio:old"
        for task_id, phase in [
            (old_preview, "succeeded"),
            (fresh_preview, "succeeded"),
            (running_preview, "running"),
            (other_task, "succeeded"),
        ]:
            self.store.save(
                task_id,
                {
                    "operation": task_id.split(":", 1)[0],
                    "phase": phase,
                    "progress_percent": 100.0 if phase == "succeeded" else 20.0,
                    "message": phase,
                },
            )

        old_timestamp = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        for task_id in [old_preview, running_preview, other_task]:
            path = self.store._path(task_id)
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["updated_at"] = old_timestamp
            path.write_text(json.dumps(payload), encoding="utf-8")
        self.store.request_cancel(old_preview)

        removed = self.store.cleanup_terminal_states(
            prefix="render_voice_preview:",
            max_age_seconds=60 * 60,
        )

        self.assertEqual(removed, 1)
        self.assertIsNone(self.store.load(old_preview))
        self.assertFalse(self.store._cancel_path(old_preview).exists())
        self.assertIsNotNone(self.store.load(fresh_preview))
        self.assertIsNotNone(self.store.load(running_preview))
        self.assertIsNotNone(self.store.load(other_task))


if __name__ == "__main__":
    unittest.main()
