from __future__ import annotations

from app.providers.audio_utils import synthesize_sine_wave_bytes
from app.providers.tts_api.base import TTSGenerationRequest, TTSGenerationResponse


class MockRemoteTTSProvider:
    provider_name = "mock_remote"
    model_name = "mock-voice"

    def synthesize(self, request: TTSGenerationRequest) -> TTSGenerationResponse:
        speed = min(1.2, max(0.8, request.speed or 1.0))
        duration_seconds = min(max(int((len(request.script_text) // 120) / speed), 1), 4)
        return TTSGenerationResponse(
            audio_bytes=synthesize_sine_wave_bytes(duration_seconds),
            file_extension="wav",
            provider_name=self.provider_name,
            model_name=self.model_name,
        )
