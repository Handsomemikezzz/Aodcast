from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_api.base import TTSGenerationRequest
from app.providers.tts_local_mlx.provider import LocalMLXTTSProvider
from app.providers.tts_local_mlx.runtime import detect_local_mlx_capability


class LocalMLXRuntimeTests(unittest.TestCase):
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
        self.assertTrue(len(response.audio_bytes) > 0)


if __name__ == "__main__":
    unittest.main()
