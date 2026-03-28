from __future__ import annotations

DEFAULT_QWEN3_TTS_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit"
SUPPORTED_MODEL_PREFIX = "mlx-community/Qwen3-TTS"


def is_supported_qwen3_model(model: str) -> bool:
    return model.strip().startswith(SUPPORTED_MODEL_PREFIX)
