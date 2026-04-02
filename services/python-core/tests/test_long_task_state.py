from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from app.runtime.long_task_state import LongTaskStateManager
from app.runtime.request_state_store import RequestStateStore


class LongTaskStateManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / ".local-data"
        self.store = RequestStateStore(self.data_dir)
        self.store.bootstrap()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def build_manager(self, task_id: str = "render_audio:test") -> LongTaskStateManager:
        return LongTaskStateManager(
            request_state_store=self.store,
            task_id=task_id,
            operation="render_audio",
            build_request_state=lambda **kwargs: dict(kwargs),
        )

    def test_manager_updates_running_progress(self) -> None:
        manager = self.build_manager()
        manager.start(progress_percent=5.0, message="start")
        manager.update_running(12.0, "tick", max_percent=20.0)

        state = self.store.load("render_audio:test")
        self.assertIsNotNone(state)
        self.assertEqual(state["phase"], "running")
        self.assertEqual(state["progress_percent"], 12.0)

    def test_manager_blocks_success_over_cancelling_state(self) -> None:
        task_id = "render_audio:test-cancel"
        manager = self.build_manager(task_id)
        manager.start(progress_percent=5.0, message="start")
        self.store.save(
            task_id,
            {
                "operation": "render_audio",
                "phase": "cancelling",
                "progress_percent": 42.0,
                "message": "cancel",
            },
        )

        saved = manager.save_succeeded(message="done")

        self.assertFalse(saved)
        state = self.store.load(task_id)
        self.assertIsNotNone(state)
        self.assertEqual(state["phase"], "cancelling")

    def test_heartbeat_respects_start_percent_floor(self) -> None:
        manager = self.build_manager("render_audio:test-heartbeat")
        manager.start(progress_percent=5.0, message="start")
        stop, thread = manager.start_heartbeat(
            start_percent=10.0,
            max_percent=20.0,
            step_percent=2.0,
            interval_seconds=0.01,
            message="tick",
        )
        time.sleep(0.04)
        manager.stop_heartbeat(stop, thread, timeout_seconds=1.0)

        state = self.store.load("render_audio:test-heartbeat")
        self.assertIsNotNone(state)
        progress = float(state["progress_percent"])
        self.assertGreaterEqual(progress, 12.0)


if __name__ == "__main__":
    unittest.main()
