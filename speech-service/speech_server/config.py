import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)

QWEN_TTS = "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit"
KOKORO = "mlx-community/Kokoro-82M-bf16"
QWEN_ASR = "mlx-community/Qwen3-ASR-0.6B-8bit"
# Base models clone a voice from reference audio + transcript; the first is the default.
CLONE_MODELS = (
    "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
    "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit",
)


def number(name: str, default: float, minimum: float, maximum: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class Settings:
    tts_model: str = os.getenv("TTS_MODEL", QWEN_TTS)
    asr_model: str = os.getenv("ASR_MODEL", QWEN_ASR)
    voice: str = os.getenv(
        "TTS_VOICE", "zf_xiaobei" if os.getenv("TTS_MODEL") == KOKORO else "Vivian"
    )
    language: str = os.getenv(
        "TTS_LANGUAGE", "z" if os.getenv("TTS_MODEL") == KOKORO else "Chinese"
    )
    seed: int = int(os.getenv("TTS_SEED", "42"))
    tts_max_tokens: int = int(number("TTS_MAX_TOKENS", 1024, 128, 2048))
    asr_max_tokens: int = int(number("ASR_MAX_TOKENS", 1024, 128, 2048))
    idle_seconds: float = number("IDLE_UNLOAD_SECONDS", 3600, 1, 86400)
    single_resident: bool = os.getenv("SINGLE_MODEL_RESIDENT", "true").lower() == "true"
    memory_gb: float = number("MLX_MEMORY_LIMIT_GB", 8, 1, 12)
    cache_mb: float = number("MLX_CACHE_LIMIT_MB", 256, 0, 2048)
    min_available_gb: float = number("MIN_AVAILABLE_MEMORY_GB", 2, 0, 12)
    max_chars: int = int(number("MAX_TEXT_CHARS", 20000, 120, 100000))
    max_upload_bytes: int = int(number("MAX_UPLOAD_MB", 100, 1, 500) * 1024**2)
    max_audio_seconds: float = number("MAX_AUDIO_SECONDS", 3600, 1, 14400)
    asr_chunk_seconds: float = number("ASR_CHUNK_SECONDS", 25, 1, 30)
    max_pending: int = int(number("MAX_PENDING_REQUESTS", 4, 1, 16))
    queue_timeout: float = number("QUEUE_TIMEOUT_SECONDS", 300, 1, 3600)
    ffmpeg_timeout: float = number("FFMPEG_TIMEOUT_SECONDS", 120, 1, 600)
    pause_ms: float = number("PARAGRAPH_PAUSE_MS", 300, 0, 2000)
    crossfade_ms: float = number("CROSSFADE_MS", 10, 1, 30)
    # The reference is prepended to every slice, so its length bounds prefill and decode cost.
    clone_min_seconds: float = number("CLONE_MIN_REFERENCE_SECONDS", 3, 1, 30)
    clone_max_seconds: float = number("CLONE_MAX_REFERENCE_SECONDS", 30, 3, 60)

    def __post_init__(self):
        if self.tts_model not in (QWEN_TTS, KOKORO) or self.asr_model != QWEN_ASR:
            raise ValueError("Only the documented Qwen3 and Kokoro model IDs are supported")
        if self.clone_min_seconds > self.clone_max_seconds:
            raise ValueError("CLONE_MIN_REFERENCE_SECONDS must not exceed the maximum")
        if not 0 <= self.seed < 2**32:
            raise ValueError("TTS_SEED must be an unsigned 32-bit integer")
