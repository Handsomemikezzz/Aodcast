from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_api.base import TTSGenerationRequest
from app.providers.tts_local_mlx.provider import LocalMLXTTSProvider
from app.providers.tts_local_mlx.runner import LocalMLXRunResult, MLXAudioQwenRunner
from app.providers.tts_local_mlx.runtime import detect_local_mlx_capability


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

    def test_runner_uses_mlx_audio_cli_and_reads_output(self) -> None:
        config = TTSProviderConfig(
            provider="local_mlx",
            model="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
        )
        runner = MLXAudioQwenRunner(config)

        def fake_run(command: list[str], **_: object):
            prefix = Path(command[command.index("--file_prefix") + 1])
            output_path = prefix.with_suffix(".wav")
            output_path.write_bytes(b"wav-bytes")
            return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()

        with patch("app.providers.tts_local_mlx.runner.subprocess.run", side_effect=fake_run):
            result = runner.synthesize("Runner test", audio_format="wav")

        self.assertEqual(result.audio_bytes, b"wav-bytes")
        self.assertEqual(result.file_extension, "wav")
        self.assertEqual(result.model_name, config.model)


if __name__ == "__main__":
    unittest.main()
