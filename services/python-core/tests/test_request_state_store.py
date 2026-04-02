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


if __name__ == "__main__":
    unittest.main()

