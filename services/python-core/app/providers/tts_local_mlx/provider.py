from __future__ import annotations

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_api.base import TTSGenerationRequest, TTSGenerationResponse
from app.providers.tts_local_mlx.runner import MLXAudioQwenRunner
from app.providers.tts_local_mlx.runtime import detect_local_mlx_capability


class LocalMLXTTSProvider:
    provider_name = "local_mlx"

    def __init__(self, config: TTSProviderConfig) -> None:
        self.config = config
        self.runner = MLXAudioQwenRunner(config)

    def synthesize(self, request: TTSGenerationRequest) -> TTSGenerationResponse:
        capability = detect_local_mlx_capability(self.config)
        if not capability.available:
            joined = " ".join(capability.reasons)
            raise RuntimeError(
                f"Local MLX TTS is unavailable. {joined}"
            )

        result = self.runner.synthesize(
            request.script_text,
            audio_format=self.config.audio_format or request.audio_format,
            should_cancel=request.should_cancel,
            on_progress=request.on_progress,
        )
        return TTSGenerationResponse(
            audio_bytes=result.audio_bytes,
            file_extension=result.file_extension,
            provider_name=self.provider_name,
            model_name=result.model_name,
        )
