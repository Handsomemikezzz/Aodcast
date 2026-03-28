from __future__ import annotations

import importlib.util
import platform
from dataclasses import dataclass
from pathlib import Path

from app.domain.tts_config import TTSProviderConfig


@dataclass(frozen=True, slots=True)
class LocalMLXCapability:
    provider: str
    runtime: str
    platform: str
    mlx_installed: bool
    model_path_configured: bool
    model_path_exists: bool
    available: bool
    reasons: list[str]
    model_path: str
    fallback_provider: str

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "runtime": self.runtime,
            "platform": self.platform,
            "mlx_installed": self.mlx_installed,
            "model_path_configured": self.model_path_configured,
            "model_path_exists": self.model_path_exists,
            "available": self.available,
            "reasons": self.reasons,
            "model_path": self.model_path,
            "fallback_provider": self.fallback_provider,
        }


def detect_local_mlx_capability(config: TTSProviderConfig) -> LocalMLXCapability:
    current_platform = platform.system().lower()
    reasons: list[str] = []
    mlx_installed = importlib.util.find_spec("mlx") is not None
    model_path = config.local_model_path.strip()
    model_path_configured = bool(model_path)
    model_path_exists = Path(model_path).exists() if model_path_configured else False

    if current_platform != "darwin":
        reasons.append("Local MLX TTS currently targets macOS only.")
    if not mlx_installed:
        reasons.append("Python module 'mlx' is not installed in the current environment.")
    if not model_path_configured:
        reasons.append("No local model path is configured for the MLX provider.")
    elif not model_path_exists:
        reasons.append(f"Configured local model path does not exist: {model_path}")

    available = not reasons
    return LocalMLXCapability(
        provider="local_mlx",
        runtime=config.local_runtime,
        platform=current_platform,
        mlx_installed=mlx_installed,
        model_path_configured=model_path_configured,
        model_path_exists=model_path_exists,
        available=available,
        reasons=reasons,
        model_path=model_path,
        fallback_provider="mock_remote",
    )
