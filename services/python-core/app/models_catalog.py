"""Speech service presets and readiness; model weights belong to the service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.tts_config import DEFAULT_LOCAL_TTS_MODEL, KOKORO_TTS_MODEL, TTSProviderConfig
from app.providers.local_speech.capabilities import (
    capability_contract_for_model,
    detect_local_speech_capability,
)
from app.storage.config_store import ConfigStore


@dataclass(frozen=True)
class CatalogEntry:
    model_name: str
    display_name: str
    hf_repo_id: str
    recommendation: str


CATALOG = (
    CatalogEntry(
        DEFAULT_LOCAL_TTS_MODEL,
        "Qwen3 TTS 0.6B CustomVoice (8-bit)",
        DEFAULT_LOCAL_TTS_MODEL,
        "Default Chinese preset voice. The speech service manages this model.",
    ),
    CatalogEntry(
        KOKORO_TTS_MODEL,
        "Kokoro 82M",
        KOKORO_TTS_MODEL,
        "Lightweight alternative; select it in the speech service configuration.",
    ),
)


def resolve_voice_model_id(model_id: str) -> str:
    cleaned = model_id.strip()
    if any(entry.hf_repo_id == cleaned for entry in CATALOG):
        return cleaned
    raise ValueError(f"Unknown speech service TTS model '{model_id}'.")


def build_models_status(config_store: ConfigStore, cwd: Path) -> list[dict[str, object]]:
    config = config_store.load_tts_config()
    service_config = config if config.provider == "local_http" else TTSProviderConfig()
    capability = detect_local_speech_capability(service_config).to_dict()
    available = bool(capability.get("available"))
    service_model = str(capability.get("current_model") or "")
    reasons = " ".join(str(reason) for reason in capability.get("reasons", []))
    return [
        {
            "model_name": entry.model_name,
            "display_name": entry.display_name,
            "hf_repo_id": entry.hf_repo_id,
            "provider": "local_http",
            "recommendation": entry.recommendation,
            "active": config.provider == "local_http" and config.model == entry.hf_repo_id,
            "available": available,
            "ready": available and service_model == entry.hf_repo_id,
            "unavailable_reason": reasons,
            "capabilities": capability_contract_for_model(entry.hf_repo_id).to_dict(),
        }
        for entry in CATALOG
    ]
