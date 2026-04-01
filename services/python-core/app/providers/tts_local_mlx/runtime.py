from __future__ import annotations

import importlib.util
import platform
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.domain.tts_config import TTSProviderConfig
from app.providers.tts_local_mlx.presets import (
    DEFAULT_QWEN3_TTS_MODEL,
    is_supported_qwen3_model,
)


@dataclass(frozen=True, slots=True)
class LocalMLXCapability:
    provider: str
    runtime: str
    platform: str
    mlx_installed: bool
    mlx_audio_installed: bool
    model_path_configured: bool
    model_path_exists: bool
    available: bool
    reasons: list[str]
    model_path: str
    model_source: str
    resolved_model: str
    fallback_provider: str

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "runtime": self.runtime,
            "platform": self.platform,
            "mlx_installed": self.mlx_installed,
            "mlx_audio_installed": self.mlx_audio_installed,
            "model_path_configured": self.model_path_configured,
            "model_path_exists": self.model_path_exists,
            "available": self.available,
            "reasons": self.reasons,
            "model_path": self.model_path,
            "model_source": self.model_source,
            "resolved_model": self.resolved_model,
            "fallback_provider": self.fallback_provider,
        }


def local_model_directory_is_valid(model_path: Path) -> bool:
    if not model_path.exists() or not model_path.is_dir():
        return False
    return any(model_path.glob("*.safetensors"))


def resolve_local_model_target(config: TTSProviderConfig) -> tuple[str, str]:
    local_model_path = config.local_model_path.strip()
    if local_model_path:
        return local_model_path, "local_path"

    model = config.model.strip()
    if not model or model == "mock-voice":
        return DEFAULT_QWEN3_TTS_MODEL, "huggingface_repo"
    return model, "huggingface_repo"


def _compact_process_error(stderr: str, stdout: str, *, limit: int = 220) -> str:
    summary = (stderr.strip() or stdout.strip()).replace("\n", " ")
    if len(summary) <= limit:
        return summary
    return summary[:limit].rstrip() + "..."


@lru_cache(maxsize=1)
def _probe_mlx_runtime_bootstrap(python_executable: str) -> tuple[bool, str]:
    command = [
        python_executable,
        "-c",
        "import mlx.core as mx; print('mlx_runtime_ok')",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except Exception as exc:
        return False, str(exc)

    if result.returncode != 0:
        return False, _compact_process_error(result.stderr, result.stdout)
    return True, ""


def detect_local_mlx_capability(config: TTSProviderConfig) -> LocalMLXCapability:
    current_platform = platform.system().lower()
    reasons: list[str] = []
    mlx_installed = importlib.util.find_spec("mlx") is not None
    mlx_audio_installed = importlib.util.find_spec("mlx_audio") is not None
    model_target, model_source = resolve_local_model_target(config)
    model_path_configured = model_source == "local_path"
    model_path_exists = Path(model_target).exists() if model_path_configured else False

    if current_platform != "darwin":
        reasons.append("Local MLX TTS currently targets macOS only.")
    if not mlx_installed:
        reasons.append("Python module 'mlx' is not installed in the current environment.")
    if not mlx_audio_installed:
        reasons.append("Python module 'mlx_audio' is not installed in the current environment.")
    if current_platform == "darwin" and mlx_installed:
        probe_ok, probe_error = _probe_mlx_runtime_bootstrap(sys.executable)
        if not probe_ok:
            detail = f" Details: {probe_error}" if probe_error else ""
            reasons.append(
                "Python module 'mlx' is installed but runtime bootstrap failed before generation."
                + detail
            )
    if model_path_configured and not model_path_exists:
        reasons.append(f"Configured local model path does not exist: {model_target}")
    elif model_path_configured and not local_model_directory_is_valid(Path(model_target)):
        reasons.append(
            "Configured local model path does not look like an MLX model directory. Expected at least one .safetensors file."
        )
    if model_source == "huggingface_repo" and not is_supported_qwen3_model(model_target):
        reasons.append(
            "Configured local MLX model must be a supported mlx-community/Qwen3-TTS repo id."
        )

    available = not reasons
    return LocalMLXCapability(
        provider="local_mlx",
        runtime=config.local_runtime,
        platform=current_platform,
        mlx_installed=mlx_installed,
        mlx_audio_installed=mlx_audio_installed,
        model_path_configured=model_path_configured,
        model_path_exists=model_path_exists,
        available=available,
        reasons=reasons,
        model_path=config.local_model_path.strip(),
        model_source=model_source,
        resolved_model=model_target,
        fallback_provider="mock_remote",
    )
