from __future__ import annotations

import tempfile
import threading
import unittest
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


if __name__ == "__main__":
    unittest.main()
