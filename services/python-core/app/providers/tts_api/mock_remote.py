from __future__ import annotations

from app.providers.audio_utils import synthesize_sine_wave_bytes
from app.providers.tts_api.base import TTSGenerationRequest, TTSGenerationResponse


class MockRemoteTTSProvider:
    provider_name = "mock_remote"
    model_name = "mock-voice"

    def synthesize(self, request: TTSGenerationRequest) -> TTSGenerationResponse:
        duration_seconds = min(max(len(request.script_text) // 120, 1), 4)
        return TTSGenerationResponse(
            audio_bytes=synthesize_sine_wave_bytes(duration_seconds),
            file_extension="wav",
            provider_name=self.provider_name,
            model_name=self.model_name,
        )
