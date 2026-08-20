from __future__ import annotations

from app.providers.tts_local_mlx.adapters.base import MLXTTSAdapter
from app.providers.tts_local_mlx.adapters.moss import MossTTSAdapter
from app.providers.tts_local_mlx.adapters.qwen3 import Qwen3TTSAdapter
from app.providers.tts_local_mlx.adapters.voxcpm2 import VoxCPM2Adapter
from app.providers.tts_local_mlx.model_spec import ModelFamily, ModelSpec


def adapter_for_model(spec: ModelSpec) -> MLXTTSAdapter:
    if spec.family == ModelFamily.QWEN3:
        return Qwen3TTSAdapter(spec)
    if spec.family == ModelFamily.VOXCPM2:
        return VoxCPM2Adapter(spec)
    if spec.family == ModelFamily.MOSS:
        return MossTTSAdapter(spec)
    raise AssertionError(f"Unhandled MLX model family: {spec.family}")


__all__ = ["adapter_for_model", "MLXTTSAdapter"]
