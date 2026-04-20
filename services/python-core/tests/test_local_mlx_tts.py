from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Callable
from unittest.mock import patch

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_api.base import TTSGenerationRequest
from app.providers.tts_local_mlx.provider import LocalMLXTTSProvider
from app.providers.tts_local_mlx.runner import LocalMLXRunResult, MLXAudioQwenRunner
from app.providers.tts_local_mlx.runtime import detect_local_mlx_capability
from app.providers.tts_local_mlx.worker_client import (
    MLXWorkerCancelled,
    WorkerEvent,
)
from app.runtime.task_cancellation import TaskCancellationRequested


class LocalMLXRuntimeTests(unittest.TestCase):
    def test_capability_reports_available_when_runtime_and_model_path_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "model.safetensors").write_bytes(b"test")
            config = TTSProviderConfig(
                provider="local_mlx",
                model="mlx-voice",
                local_model_path=tmp_dir,
            )
            with patch("app.providers.tts_local_mlx.runtime.platform.system", return_value="Darwin"):
                with patch("app.providers.tts_local_mlx.runtime.importlib.util.find_spec", return_value=object()):
                    with patch(
                        "app.providers.tts_local_mlx.runtime._probe_mlx_runtime_bootstrap",
                        return_value=(True, ""),
                    ):
                        capability = detect_local_mlx_capability(config)

        self.assertTrue(capability.available)
        self.assertTrue(capability.mlx_installed)
        self.assertTrue(capability.mlx_audio_installed)
        self.assertTrue(capability.model_path_exists)
        self.assertEqual(capability.reasons, [])

    def test_capability_reports_missing_mlx_in_current_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = TTSProviderConfig(
                provider="local_mlx",
                model="mlx-voice",
                local_model_path=tmp_dir,
            )
            capability = detect_local_mlx_capability(config)

        self.assertEqual(capability.provider, "local_mlx")
        self.assertFalse(capability.available)
        self.assertIn("mlx", " ".join(capability.reasons).lower())

    def test_capability_reports_runtime_bootstrap_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            Path(tmp_dir, "model.safetensors").write_bytes(b"test")
            config = TTSProviderConfig(
                provider="local_mlx",
                model="mlx-voice",
                local_model_path=tmp_dir,
            )
            with patch("app.providers.tts_local_mlx.runtime.platform.system", return_value="Darwin"):
                with patch("app.providers.tts_local_mlx.runtime.importlib.util.find_spec", return_value=object()):
                    with patch(
                        "app.providers.tts_local_mlx.runtime._probe_mlx_runtime_bootstrap",
                        return_value=(False, "NSRangeException"),
                    ):
                        capability = detect_local_mlx_capability(config)

        self.assertFalse(capability.available)
        self.assertIn("runtime bootstrap failed", " ".join(capability.reasons).lower())

    def test_local_provider_requires_available_runtime(self) -> None:
        provider = LocalMLXTTSProvider(
            TTSProviderConfig(provider="local_mlx", model="mlx-voice", local_model_path="/tmp/missing")
        )
        with self.assertRaises(RuntimeError):
            provider.synthesize(
                TTSGenerationRequest(
                    session_id="session-1",
                    script_text="test",
                    voice="alloy",
                    audio_format="wav",
                )
            )

    def test_local_provider_can_render_when_capability_is_available(self) -> None:
        provider = LocalMLXTTSProvider(
            TTSProviderConfig(provider="local_mlx", model="mlx-voice", local_model_path="/tmp/model")
        )
        with patch(
            "app.providers.tts_local_mlx.provider.detect_local_mlx_capability",
            return_value=type(
                "Capability",
                (),
                {"available": True, "reasons": [], "fallback_provider": "mock_remote"},
            )(),
        ), patch.object(
            provider.runner,
            "synthesize",
            return_value=LocalMLXRunResult(
                audio_bytes=b"runner-bytes",
                file_extension="wav",
                model_name="mlx-voice",
                output_path="/tmp/render.wav",
            ),
        ):
            response = provider.synthesize(
                TTSGenerationRequest(
                    session_id="session-1",
                    script_text="A local render path for testing.",
                    voice="alloy",
                    audio_format="wav",
                )
            )

        self.assertEqual(response.provider_name, "local_mlx")
        self.assertEqual(response.file_extension, "wav")
        self.assertEqual(response.audio_bytes, b"runner-bytes")

    def test_runner_submits_chunks_to_worker_and_returns_audio(self) -> None:
        config = TTSProviderConfig(
            provider="local_mlx",
            model="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
        )

        class FakeWorkerClient:
            def __init__(self) -> None:
                self.last_kwargs: dict[str, object] = {}

            def synthesize(
                self,
                *,
                model: str,
                chunks,
                voice: str,
                audio_format: str,
                output_dir: Path,
                ref_audio,
                should_cancel,
                on_event: Callable[[WorkerEvent], None] | None,
            ) -> dict[str, object]:
                self.last_kwargs = {
                    "model": model,
                    "chunks": list(chunks),
                    "voice": voice,
                    "audio_format": audio_format,
                    "ref_audio": ref_audio,
                }
                if on_event is not None:
                    on_event(
                        WorkerEvent(
                            type="chunk_started",
                            payload={"index": 0, "total": 1, "job_id": "job"},
                        )
                    )
                    on_event(
                        WorkerEvent(
                            type="chunk_done",
                            payload={"index": 0, "total": 1, "job_id": "job", "duration_seconds": 0.5},
                        )
                    )
                audio_path = Path(output_dir) / f"final.{audio_format}"
                audio_path.write_bytes(b"worker-wav")
                return {
                    "audio_path": str(audio_path),
                    "file_extension": audio_format,
                    "chunks_total": 1,
                    "sample_rate": 24000,
                }

        fake = FakeWorkerClient()
        runner = MLXAudioQwenRunner(config, worker_client=fake)

        events: list[object] = []
        result = runner.synthesize(
            "Short runner test sentence.",
            audio_format="wav",
            on_progress=events.append,
        )

        self.assertEqual(result.audio_bytes, b"worker-wav")
        self.assertEqual(result.file_extension, "wav")
        self.assertEqual(result.model_name, config.model)
        self.assertEqual(fake.last_kwargs["audio_format"], "wav")
        self.assertEqual(len(events), 2)
        self.assertEqual(getattr(events[0], "phase"), "chunk_started")
        self.assertEqual(getattr(events[1], "phase"), "chunk_done")

    def test_runner_translates_worker_cancellation_into_task_cancellation(self) -> None:
        config = TTSProviderConfig(
            provider="local_mlx",
            model="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
        )

        class CancellingWorker:
            def synthesize(self, **_: object) -> dict[str, object]:
                raise MLXWorkerCancelled("worker cancelled")

        runner = MLXAudioQwenRunner(config, worker_client=CancellingWorker())

        with self.assertRaises(TaskCancellationRequested):
            runner.synthesize(
                "A long script body that will be cancelled.",
                audio_format="wav",
                should_cancel=lambda: True,
            )


if __name__ == "__main__":
    unittest.main()
