"""Speech service presets and readiness; model weights belong to the service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.tts_config import (
    DEFAULT_LOCAL_CLONE_MODEL,
    DEFAULT_LOCAL_TTS_MODEL,
    KOKORO_TTS_MODEL,
    LOCAL_CLONE_MODELS,
    TTSProviderConfig,
)
from app.providers.local_speech.capabilities import (
    capability_contract_for_model,
    detect_local_speech_capability,
    is_clone_model,
)
from app.storage.config_store import ConfigStore


@dataclass(frozen=True)
class CatalogEntry:
    model_name: str
    display_name: str
    hf_repo_id: str
    recommendation: str
    # Default among models of the same kind (preset voices vs. cloning, per the capability contract).
    default_for_mode: bool = False


CATALOG = (
    CatalogEntry(
        DEFAULT_LOCAL_TTS_MODEL,
        "Qwen3 TTS 0.6B CustomVoice (8-bit)",
        DEFAULT_LOCAL_TTS_MODEL,
        "Default Chinese preset voice. The speech service manages this model.",
        default_for_mode=True,
    ),
    CatalogEntry(
        LOCAL_CLONE_MODELS[0],
        "Qwen3 TTS 0.6B Base (8-bit)",
        LOCAL_CLONE_MODELS[0],
        "Default voice cloning model. Faster, lighter on memory.",
        default_for_mode=LOCAL_CLONE_MODELS[0] == DEFAULT_LOCAL_CLONE_MODEL,
    ),
    CatalogEntry(
        LOCAL_CLONE_MODELS[1],
        "Qwen3 TTS 1.7B Base (8-bit)",
        LOCAL_CLONE_MODELS[1],
        "Larger voice cloning model. Slower and uses more memory; compare it with 0.6B.",
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
    clone_models = {str(model) for model in capability.get("clone_models") or []}
    max_reference_ms = capability.get("max_reference_duration_ms")
    reasons = " ".join(str(reason) for reason in capability.get("reasons", []))
    rows = []
    for entry in CATALOG:
        cloning = is_clone_model(entry.hf_repo_id)
        served = entry.hf_repo_id in clone_models if cloning else service_model == entry.hf_repo_id
        rows.append(
            {
                "model_name": entry.model_name,
                "display_name": entry.display_name,
                "hf_repo_id": entry.hf_repo_id,
                "provider": "local_http",
                "default_for_mode": entry.default_for_mode,
                "recommendation": entry.recommendation,
                "active": config.provider == "local_http" and config.model == entry.hf_repo_id,
                "available": available,
                "ready": available and served,
                "unavailable_reason": reasons
                or ("Restart the speech service to enable voice cloning." if cloning and not served else ""),
                "capabilities": capability_contract_for_model(
                    entry.hf_repo_id,
                    max_reference_ms if isinstance(max_reference_ms, int) else None,
                ).to_dict(),
            }
        )
    return rows
