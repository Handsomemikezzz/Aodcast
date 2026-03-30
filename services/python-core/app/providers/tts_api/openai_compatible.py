from __future__ import annotations

import json
from dataclasses import dataclass
from urllib import request as urllib_request

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_api.base import TTSGenerationRequest, TTSGenerationResponse


@dataclass(frozen=True, slots=True)
class OpenAICompatibleTTSProvider:
    config: TTSProviderConfig

    def synthesize(self, request: TTSGenerationRequest) -> TTSGenerationResponse:
        if not self.config.base_url:
            raise ValueError("OpenAI-compatible TTS provider requires a base_url.")
        if not self.config.model:
            raise ValueError("OpenAI-compatible TTS provider requires a model.")
        if not self.config.api_key:
            raise ValueError("OpenAI-compatible TTS provider requires an api_key.")

        payload = {
            "model": self.config.model,
            "voice": self.config.voice or request.voice,
            "input": request.script_text,
            "format": self.config.audio_format or request.audio_format,
        }
        req = urllib_request.Request(
            url=self.config.base_url.rstrip("/") + "/audio/speech",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=30) as response:
            audio_bytes = response.read()

        return TTSGenerationResponse(
            audio_bytes=audio_bytes,
            file_extension=self.config.audio_format or request.audio_format,
            provider_name=self.config.provider,
            model_name=self.config.model,
        )
