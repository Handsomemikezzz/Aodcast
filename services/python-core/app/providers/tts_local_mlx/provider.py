from __future__ import annotations

from app.domain.tts_config import TTSProviderConfig
from app.providers.audio_utils import synthesize_sine_wave_bytes
from app.providers.tts_api.base import TTSGenerationRequest, TTSGenerationResponse
from app.providers.tts_local_mlx.runtime import detect_local_mlx_capability


class LocalMLXTTSProvider:
    provider_name = "local_mlx"

    def __init__(self, config: TTSProviderConfig) -> None:
        self.config = config

    def synthesize(self, request: TTSGenerationRequest) -> TTSGenerationResponse:
        capability = detect_local_mlx_capability(self.config)
        if not capability.available:
            joined = " ".join(capability.reasons)
            raise RuntimeError(
                f"Local MLX TTS is unavailable. {joined} Fallback provider: {capability.fallback_provider}."
            )

        duration_seconds = min(max(len(request.script_text) // 140, 1), 4)
        return TTSGenerationResponse(
            audio_bytes=synthesize_sine_wave_bytes(duration_seconds, frequency=523.25),
            file_extension=self.config.audio_format or request.audio_format,
            provider_name=self.provider_name,
            model_name=self.config.model,
        )
