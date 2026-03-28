from __future__ import annotations

import io
import math
import wave


def synthesize_sine_wave_bytes(
    duration_seconds: int,
    *,
    sample_rate: int = 22050,
    amplitude: int = 12000,
    frequency: float = 440.0,
) -> bytes:
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

    return buffer.getvalue()
