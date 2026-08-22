from __future__ import annotations

import signal
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.api.bridge_envelope import build_request_state
from app.api.http_runtime import RuntimeContext, install_runtime_stop_handlers
from app.config import AppConfig
from app.orchestration.audio_rendering import AudioRenderingService
from app.orchestration.interview_service import InterviewOrchestrator
from app.orchestration.script_generation import ScriptGenerationService
from app.runtime.request_state_store import RequestStateStore
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


class RuntimeDownloadShutdownTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self.temp_dir.name)
        config = AppConfig.from_cwd(self.cwd)
        store = ProjectStore(config.data_dir)
        config_store = ConfigStore(config.config_dir)
        artifact_store = ArtifactStore(config.data_dir)
        request_state_store = RequestStateStore(config.data_dir)
        store.bootstrap()
        config_store.bootstrap()
        artifact_store.bootstrap()
        request_state_store.bootstrap()
        self.context = RuntimeContext(
            cwd=self.cwd,
            config=config,
            store=store,
            config_store=config_store,
            artifact_store=artifact_store,
            request_state_store=request_state_store,
            orchestrator=InterviewOrchestrator(store, config_store),
            script_generation=ScriptGenerationService(store, config_store),
            audio_rendering=AudioRenderingService(store, config_store, artifact_store),
            runtime_token="test-token",
            bootstrap_nonce=None,
            bootstrap_created_at=0.0,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_shutdown_download_processes_stops_children_and_fails_running_state(self) -> None:
        task_id = "download_model:voxcpm2-8bit"
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 4242
        self.context.register_download_process(task_id, proc)
        self.context.request_state_store.save(
            task_id,
            build_request_state(
                operation="download_model",
                phase="running",
                progress_percent=40.0,
                message="Downloading...",
            ),
        )

        with patch("app.api.http_runtime.stop_download_process") as stop_download:
            self.context.shutdown_download_processes()

        stop_download.assert_called_once_with(proc)
        self.assertEqual(self.context.active_download_processes, {})
        state = self.context.request_state_store.load(task_id)
        assert state is not None
        self.assertEqual(state["phase"], "failed")
        self.assertIn("runtime stopped", str(state["message"]))

    def test_sigterm_handler_invokes_on_stop(self) -> None:
        called: list[int] = []

        def on_stop() -> None:
            called.append(1)

        restore = install_runtime_stop_handlers(on_stop=on_stop)
        try:
            signal.raise_signal(signal.SIGTERM)
            self.assertEqual(called, [1])
            # Second signal must be idempotent while the first stop is in flight.
            signal.raise_signal(signal.SIGTERM)
            self.assertEqual(called, [1])
        finally:
            restore()


if __name__ == "__main__":
    unittest.main()
