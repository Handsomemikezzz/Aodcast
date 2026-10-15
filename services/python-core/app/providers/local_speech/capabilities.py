from __future__ import annotations

from dataclasses import asdict, dataclass

from app.domain.tts_config import TTSProviderConfig
from app.providers.local_speech.client import LocalSpeechClient, LocalSpeechError


@dataclass(frozen=True)
class LocalSpeechCapability:
    available: bool
    current_model: str
    endpoint: str
    reasons: tuple[str, ...] = ()
    provider: str = "local_http"
    runtime: str = "http"
    model_source: str = "http_service"

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "reasons": list(self.reasons)}


def detect_local_speech_capability(config: TTSProviderConfig) -> LocalSpeechCapability:
    client = LocalSpeechClient(config.base_url)
    try:
        health = client.health()
        model = str(health["models"]["tts"]["id"])
        return LocalSpeechCapability(True, model, client.base_url)
    except (LocalSpeechError, ValueError, KeyError, TypeError) as exc:
        return LocalSpeechCapability(False, config.model, client.base_url, (str(exc),))


@dataclass(frozen=True)
class SpeechServiceModelContract:
    model: str

    def to_dict(self) -> dict[str, object]:
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
        return {
            "schema_version": 1,
            "provider": "local_http",
            "model": self.model,
            "runtime": "http",
            "adapter_version": "local-http-v1",
            "platforms": ["http_client"],
            "languages": ["zh", "en"],
            "reference_audio_formats": [],
            "output_audio_formats": ["wav"],
            "capabilities": levels,
            "limits": {
                "max_reference_duration_ms": None,
                "max_segment_characters": 20000,
            },
        }


def capability_contract_for_model(model: str) -> SpeechServiceModelContract:
    return SpeechServiceModelContract(model)
