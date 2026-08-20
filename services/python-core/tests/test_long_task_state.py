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

    def build_manager(
        self,
        task_id: str = "render_audio:test",
        *,
        run_token: str = "",
    ) -> LongTaskStateManager:
        def build_state(**kwargs):
            state = dict(kwargs)
            if run_token:
                state["run_token"] = run_token
            return state

        return LongTaskStateManager(
            request_state_store=self.store,
            task_id=task_id,
            operation="render_audio",
            build_request_state=build_state,
        )

    def test_manager_updates_running_progress(self) -> None:
        manager = self.build_manager()
        manager.start(progress_percent=5.0, message="start")
        manager.update_running(12.0, "tick", max_percent=20.0)

        state = self.store.load("render_audio:test")
        self.assertIsNotNone(state)
        self.assertEqual(state["phase"], "running")
        self.assertEqual(state["progress_percent"], 12.0)

    def test_committed_operation_wins_a_late_cancellation(self) -> None:
        task_id = "render_audio:test-cancel"
        manager = self.build_manager(task_id, run_token="run-current")
        manager.start(progress_percent=5.0, message="start")
        self.store.request_cancel(task_id, run_token="run-current")
        self.store.save_if_current_phase(
            task_id,
            {
                "operation": "render_audio",
                "phase": "cancelling",
                "progress_percent": 42.0,
                "message": "cancel",
                "run_token": "run-current",
            },
            allowed_phases={"running"},
            expected_run_token="run-current",
        )

        saved = manager.save_succeeded(message="done")

        self.assertTrue(saved)
        state = self.store.load(task_id)
        self.assertIsNotNone(state)
        self.assertEqual(state["phase"], "succeeded")
        self.assertFalse(
            self.store.is_cancel_requested(task_id, run_token="run-current")
        )

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

    def test_stale_manager_cannot_overwrite_or_clear_new_run_state(self) -> None:
        task_id = "render_audio:shared"
        old = self.build_manager(task_id, run_token="run-old")
        new = self.build_manager(task_id, run_token="run-new")
        old.start(progress_percent=5.0, message="old start")
        self.store.request_cancel(task_id, run_token="run-old")

        new.start(progress_percent=7.0, message="new start")
        self.assertFalse(self.store.is_cancel_requested(task_id, run_token="run-new"))
        self.assertFalse(old.set_progress(80.0, "late old progress"))
        self.assertFalse(old.save_failed(message="late old failure"))
        self.assertFalse(old.save_succeeded(message="late old success"))

        state = self.store.load(task_id)
        self.assertIsNotNone(state)
        self.assertEqual(state["run_token"], "run-new")
        self.assertEqual(state["phase"], "running")
        self.assertEqual(state["message"], "new start")

        self.store.request_cancel(task_id, run_token="run-new")
        self.assertFalse(
            old.save_cancelled(progress_percent=80.0, message="late old cancel")
        )
        self.assertTrue(self.store.is_cancel_requested(task_id, run_token="run-new"))

        self.assertTrue(
            new.save_cancelled(progress_percent=7.0, message="new cancelled")
        )
        state = self.store.load(task_id)
        self.assertIsNotNone(state)
        self.assertEqual(state["run_token"], "run-new")
        self.assertEqual(state["phase"], "cancelled")
        self.assertFalse(self.store.is_cancel_requested(task_id, run_token="run-new"))


if __name__ == "__main__":
    unittest.main()
