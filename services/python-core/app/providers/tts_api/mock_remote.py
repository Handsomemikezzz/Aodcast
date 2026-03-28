from __future__ import annotations

import io
import math
import wave

from app.providers.tts_api.base import TTSGenerationRequest, TTSGenerationResponse


class MockRemoteTTSProvider:
    provider_name = "mock_remote"
    model_name = "mock-voice"

    def synthesize(self, request: TTSGenerationRequest) -> TTSGenerationResponse:
        duration_seconds = min(max(len(request.script_text) // 120, 1), 4)
        sample_rate = 22050
        amplitude = 12000
        frequency = 440.0

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)

            total_frames = duration_seconds * sample_rate
            for index in range(total_frames):
                value = int(
                    amplitude * math.sin((2.0 * math.pi * frequency * index) / sample_rate)
                )
                wav_file.writeframesraw(value.to_bytes(2, byteorder="little", signed=True))

        return TTSGenerationResponse(
            audio_bytes=buffer.getvalue(),
            file_extension="wav",
            provider_name=self.provider_name,
            model_name=self.model_name,
        )
