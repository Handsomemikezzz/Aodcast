from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path
from typing import Callable
from unittest.mock import patch

try:
    import numpy as np
except ImportError:
    raise unittest.SkipTest("numpy is not installed; skipping local MLX tests")

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_api.base import TTSGenerationRequest
from app.providers.tts_local_mlx.mlx_worker import MlxTtsWorker
from app.providers.tts_local_mlx.provider import LocalMLXTTSProvider
from app.providers.tts_local_mlx.runner import LocalMLXRunResult, MLXAudioRunner
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
            Path(tmp_dir, "config.json").write_text(
                json.dumps({"model_type": "qwen3_tts", "tts_model_type": "base"}),
                encoding="utf-8",
            )
            config = TTSProviderConfig(
                provider="local_mlx",
                model="mlx-voice",
                local_model_path=tmp_dir,
            )
            with patch("app.providers.tts_local_mlx.runtime.platform.system", return_value="Darwin"), patch(
                "app.providers.tts_local_mlx.runtime.platform.machine", return_value="arm64"
            ):
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
            Path(tmp_dir, "config.json").write_text(
                json.dumps({"model_type": "qwen3_tts", "tts_model_type": "base"}),
                encoding="utf-8",
            )
            config = TTSProviderConfig(
                provider="local_mlx",
                model="mlx-voice",
                local_model_path=tmp_dir,
            )
            with patch("app.providers.tts_local_mlx.runtime.platform.system", return_value="Darwin"), patch(
                "app.providers.tts_local_mlx.runtime.platform.machine", return_value="arm64"
            ):
                with patch("app.providers.tts_local_mlx.runtime.importlib.util.find_spec", return_value=object()):
                    with patch(
                        "app.providers.tts_local_mlx.runtime._probe_mlx_runtime_bootstrap",
                        return_value=(False, "NSRangeException"),
                    ):
                        capability = detect_local_mlx_capability(config)

        self.assertFalse(capability.available)
        self.assertIn("runtime compute bootstrap failed", " ".join(capability.reasons).lower())

    def test_worker_reads_segment_pcm_at_model_sample_rate_without_stereo_resampling(self) -> None:
        worker = MlxTtsWorker("stub-model")
        worker._sample_rate = 24_000
        samples = np.zeros(2_400, dtype=np.int16)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "segment.wav"
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(24_000)
                handle.writeframes(samples.tobytes())

            decoded = worker._read_pcm(path, np=np)

        self.assertEqual(decoded.shape, (2_400,))
        self.assertEqual(decoded.dtype, np.int16)

    def test_worker_preserves_stereo_pcm_shape(self) -> None:
        worker = MlxTtsWorker("stub-model")
        worker._sample_rate = 48_000
        worker._channels = 2
        samples = np.zeros((4_800, 2), dtype=np.int16)

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "stereo.wav"
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(2)
                handle.setsampwidth(2)
                handle.setframerate(48_000)
                handle.writeframes(samples.tobytes())

            decoded = worker._read_pcm(path, np=np)

        self.assertEqual(decoded.shape, (4_800, 2))
        self.assertEqual(decoded.dtype, np.int16)

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
        self.assertEqual(response.adapter_version, "speech-plan-v1")
        self.assertEqual(response.file_extension, "wav")
        self.assertEqual(response.audio_bytes, b"runner-bytes")

    def test_local_provider_forwards_voice_style_speed_language_and_reference_text_to_runner(self) -> None:
        provider = LocalMLXTTSProvider(
            TTSProviderConfig(provider="local_mlx", model="mlx-voice", local_model_path="/tmp/model")
        )
        captured: dict[str, object] = {}

        def capture_runner(text: str, **kwargs: object) -> LocalMLXRunResult:
            captured["text"] = text
            captured.update(kwargs)
            return LocalMLXRunResult(
                audio_bytes=b"runner-bytes",
                file_extension="wav",
                model_name="mlx-voice",
                output_path="/tmp/render.wav",
            )

        with patch(
            "app.providers.tts_local_mlx.provider.detect_local_mlx_capability",
            return_value=type(
                "Capability",
                (),
                {"available": True, "reasons": [], "fallback_provider": "mock_remote"},
            )(),
        ), patch.object(provider.runner, "synthesize", side_effect=capture_runner):
            provider.synthesize(
                TTSGenerationRequest(
                    session_id="session-1",
                    script_text="一段中文试音。",
                    voice="Vivian",
                    audio_format="wav",
                    speed=0.8,
                    style_id="story",
                    style_prompt="Use a slower, immersive storytelling tone.",
                    language="zh",
                    reference_audio_path="/tmp/locked-preview.wav",
                    reference_text="锁定这一句试音。",
                )
            )

        self.assertEqual(captured["text"], "一段中文试音。")
        self.assertEqual(captured["voice"], "Vivian")
        self.assertEqual(captured["speed"], 0.8)
        self.assertEqual(captured["style_prompt"], "Use a slower, immersive storytelling tone.")
        self.assertEqual(captured["language"], "zh")
        self.assertEqual(captured["reference_audio_path"], "/tmp/locked-preview.wav")
        self.assertEqual(captured["reference_text"], "锁定这一句试音。")

    def test_runner_submits_chunks_to_worker_and_returns_audio(self) -> None:
        config = TTSProviderConfig(
            provider="local_mlx",
            model="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
            local_ref_audio_path="/tmp/ref.wav",
        )

        class FakeWorkerClient:
            def __init__(self) -> None:
                self.last_kwargs: dict[str, object] = {}

            def synthesize(
                self,
                *,
                model: str,
                segments,
                options,
                leading_silence_ms: int,
                output_dir: Path,
                should_cancel,
                on_event: Callable[[WorkerEvent], None] | None,
            ) -> dict[str, object]:
                self.last_kwargs = {
                    "model": model,
                    "segments": list(segments),
                    "options": dict(options),
                    "leading_silence_ms": leading_silence_ms,
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
                audio_path = Path(output_dir) / "final.wav"
                audio_path.write_bytes(b"worker-wav")
                return {
                    "audio_path": str(audio_path),
                    "file_extension": "wav",
                    "chunks_total": 1,
                    "sample_rate": 24000,
                    "channels": 1,
                }

        fake = FakeWorkerClient()
        runner = MLXAudioRunner(config, worker_client=fake)

        events: list[object] = []
        result = runner.synthesize(
            "Short runner test sentence.",
            audio_format="wav",
            on_progress=events.append,
        )

        self.assertEqual(result.audio_bytes, b"worker-wav")
        self.assertEqual(result.file_extension, "wav")
        self.assertEqual(result.model_name, config.model)
        options = fake.last_kwargs["options"]
        self.assertEqual(options["speed"], 1.0)
        self.assertEqual(options["style_prompt"], "")
        self.assertEqual(options["language"], "zh")
        self.assertEqual(options["reference_audio_path"], config.local_ref_audio_path)
        self.assertEqual(options["reference_text"], "")
        self.assertEqual(len(events), 2)
        self.assertEqual(getattr(events[0], "phase"), "chunk_started")
        self.assertEqual(getattr(events[1], "phase"), "chunk_done")

    def test_runner_reports_the_actual_local_model_target_for_manifest_freezing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_dir = Path(tmp_dir) / "custom-vox"
            model_dir.mkdir()
            (model_dir / "config.json").write_text(
                json.dumps({"model_type": "voxcpm2"}),
                encoding="utf-8",
            )
            (model_dir / "model.safetensors").write_bytes(b"weights")
            config = TTSProviderConfig(
                provider="local_mlx",
                model="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
                local_model_path=str(model_dir),
            )

            class FakeWorkerClient:
                def __init__(self) -> None:
                    self.model = ""

                def synthesize(self, **kwargs: object) -> dict[str, object]:
                    self.model = str(kwargs["model"])
                    output_dir = Path(kwargs["output_dir"])
                    audio_path = output_dir / "final.wav"
                    audio_path.write_bytes(b"worker-wav")
                    return {
                        "audio_path": str(audio_path),
                        "sample_rate": 48_000,
                        "channels": 1,
                    }

            fake = FakeWorkerClient()
            result = MLXAudioRunner(config, worker_client=fake).synthesize(
                "本地自定义模型路径。",
                audio_format="wav",
            )

            self.assertEqual(fake.model, str(model_dir))
            self.assertEqual(result.model_name, str(model_dir))

    def test_runner_prefers_request_reference_audio_over_config_reference(self) -> None:
        config = TTSProviderConfig(
            provider="local_mlx",
            model="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
            local_ref_audio_path="/tmp/global-reference.wav",
        )

        class FakeWorkerClient:
            def __init__(self) -> None:
                self.last_kwargs: dict[str, object] = {}

            def synthesize(self, **kwargs: object) -> dict[str, object]:
                self.last_kwargs = dict(kwargs)
                output_dir = Path(kwargs["output_dir"])
                audio_path = output_dir / "final.wav"
                audio_path.write_bytes(b"worker-wav")
                return {
                    "audio_path": str(audio_path),
                    "file_extension": "wav",
                    "chunks_total": 1,
                    "sample_rate": 24000,
                    "channels": 1,
                }

        fake = FakeWorkerClient()
        runner = MLXAudioRunner(config, worker_client=fake)

        runner.synthesize(
            "Short runner test sentence.",
            audio_format="wav",
            reference_audio_path="/tmp/locked-preview.wav",
            reference_text="Locked preview text.",
        )

        options = fake.last_kwargs["options"]
        self.assertEqual(options["reference_audio_path"], "/tmp/locked-preview.wav")
        self.assertEqual(options["reference_text"], "Locked preview text.")

    def test_runner_translates_worker_cancellation_into_task_cancellation(self) -> None:
        config = TTSProviderConfig(
            provider="local_mlx",
            model="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
        )

        class CancellingWorker:
            def synthesize(self, **_: object) -> dict[str, object]:
                raise MLXWorkerCancelled("worker cancelled")

        runner = MLXAudioRunner(config, worker_client=CancellingWorker())

        with self.assertRaises(TaskCancellationRequested):
            runner.synthesize(
                "A long script body that will be cancelled.",
                audio_format="wav",
                should_cancel=lambda: True,
            )


if __name__ == "__main__":
    unittest.main()
