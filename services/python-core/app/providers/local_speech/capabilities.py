"""HTTP-only adapters for the independently managed local speech service."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.domain.tts_config import LOCAL_CLONE_MODELS, TTSProviderConfig
from app.providers.local_speech.client import LocalSpeechClient, LocalSpeechError


@dataclass(frozen=True)
class LocalSpeechCapability:
    available: bool
    current_model: str
    endpoint: str
    reasons: tuple[str, ...] = ()
    clone_models: tuple[str, ...] = ()
    min_reference_duration_ms: int | None = None
    max_reference_duration_ms: int | None = None
    provider: str = "local_http"
    runtime: str = "http"
    model_source: str = "http_service"

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "reasons": list(self.reasons), "clone_models": list(self.clone_models)}


def detect_local_speech_capability(config: TTSProviderConfig) -> LocalSpeechCapability:
    client = LocalSpeechClient(config.base_url)
    try:
        health = client.health()
        model = str(health["models"]["tts"]["id"])
        clone_models = tuple(str(item["id"]) for item in health["models"].get("clone", []))
        limits = health.get("clone_reference") or {}
        return LocalSpeechCapability(
            True,
            model,
            client.base_url,
            clone_models=clone_models,
            min_reference_duration_ms=_milliseconds(limits.get("min_seconds")),
            max_reference_duration_ms=_milliseconds(limits.get("max_seconds")),
        )
    except (LocalSpeechError, ValueError, KeyError, TypeError) as exc:
        return LocalSpeechCapability(False, config.model, client.base_url, (str(exc),))


def _milliseconds(seconds: object) -> int | None:
    return round(float(seconds) * 1000) if isinstance(seconds, (int, float)) else None


def is_clone_model(model: str) -> bool:
    return model in LOCAL_CLONE_MODELS


@dataclass(frozen=True)
class SpeechServiceModelContract:
    model: str
    max_reference_duration_ms: int | None = None

    def to_dict(self) -> dict[str, object]:
        cloning = is_clone_model(self.model)
        levels = {
            name: "unsupported"
            for name in (
                "speaker_cloning",
                "style_instruction",
                "emotion",
                "energy",
                "pace",
                "emphasis",
                "explicit_breaks",
                "pronunciation",
                "text_context",
                "audio_context",
                "voice_conversion",
            )
        }
        levels["deterministic_seed"] = "native"
        levels["explicit_breaks"] = "approximated"
        if cloning:
            # Zero-shot ICL: the same reference conditions every segment; no audio continuity.
            levels["speaker_cloning"] = "native"
        return {
            "schema_version": 1,
            "provider": "local_http",
            "model": self.model,
            "runtime": "http",
            "adapter_version": "local-http-clone-v1" if cloning else "local-http-v1",
            "platforms": ["http_client"],
            "languages": ["zh", "en"],
            "reference_audio_formats": ["wav"] if cloning else [],
            "output_audio_formats": ["wav"],
            "capabilities": levels,
            "limits": {
                "max_reference_duration_ms": self.max_reference_duration_ms if cloning else None,
                "max_segment_characters": 20000,
            },
        }


def capability_contract_for_model(
    model: str, max_reference_duration_ms: int | None = None
) -> SpeechServiceModelContract:
    return SpeechServiceModelContract(model, max_reference_duration_ms)
