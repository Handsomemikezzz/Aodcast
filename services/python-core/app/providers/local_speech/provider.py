from __future__ import annotations

import io
import wave

from app.domain.tts_config import KOKORO_TTS_MODEL, TTSProviderConfig
from app.providers.local_speech.capabilities import is_clone_model
from app.providers.local_speech.client import LocalSpeechClient
from app.providers.tts_api.base import TTSGenerationRequest, TTSGenerationResponse


class LocalSpeechTTSProvider:
    provider_name = "local_http"

    def __init__(self, config: TTSProviderConfig) -> None:
        self.config = config
        self.client = LocalSpeechClient(config.base_url)

    def synthesize(self, request: TTSGenerationRequest) -> TTSGenerationResponse:
        if request.context_audio_path or request.context_text:
            raise ValueError(
                "The local speech service cannot condition on preceding audio; "
                "each segment is cloned from the selected Speaker Reference only."
            )
        if request.speed != 1.0 or request.style_prompt or request.breaks:
            raise ValueError("The local speech service does not support speed, style instructions, or exact pauses; use natural punctuation.")
        if self.config.audio_format != "wav" or request.audio_format != "wav":
            raise ValueError("The local speech service supports WAV output only.")
        cloning = is_clone_model(self.config.model)
        has_reference = bool(request.reference_audio_path or request.reference_text)
        if cloning and (not has_reference or request.clone_mode == "none"):
            raise ValueError(
                f"{self.config.model} clones a voice and has no preset voices. "
                "Select a Speaker Reference first."
            )
        if not cloning and (has_reference or request.clone_mode not in ("auto", "none")):
            raise ValueError(
                "The selected local model uses preset voices only; choose a Qwen3 Base model to clone a Speaker Reference."
            )
        if cloning:
            model_name = self.config.model
            audio = self.client.clone(
                request.script_text,
                request.reference_audio_path,
                request.reference_text,
                model=model_name,
                language=request.language,
                should_cancel=request.should_cancel,
            )
            adapter_version = "local-http-clone-v1"
        else:
            model_name = str(self.client.health()["models"]["tts"]["id"])
            audio = self.client.synthesize(
                request.script_text,
                self._voice(request.voice or self.config.voice, request.language, model_name),
                model=model_name,
                should_cancel=request.should_cancel,
            )
            adapter_version = "local-http-v1"
        with wave.open(io.BytesIO(audio), "rb") as wav:
            return TTSGenerationResponse(
                audio_bytes=audio,
                file_extension="wav",
                provider_name=self.provider_name,
                model_name=model_name,
                adapter_version=adapter_version,
                sample_rate_hz=wav.getframerate(),
                channels=wav.getnchannels(),
            )

    def _voice(self, voice: str, language: str, model_name: str) -> str:
        if model_name == KOKORO_TTS_MODEL:
            voices = {
                "warm_narrator": "zf_xiaobei",
                "news_anchor": "zf_xiaoxiao",
                "casual_chat": "zf_xiaoni",
                "deep_story": "zm_yunxi",
                "bright_energy": "zf_xiaoyi",
            }
        elif language.lower().startswith("en"):
            voices = {
                "warm_narrator": "Ryan",
                "news_anchor": "Ryan",
                "casual_chat": "Aiden",
                "deep_story": "Ryan",
                "bright_energy": "Aiden",
            }
        else:
            voices = {
                "warm_narrator": "Vivian",
                "news_anchor": "Serena",
                "casual_chat": "Dylan",
                "deep_story": "Uncle_Fu",
                "bright_energy": "Eric",
            }
        return voices.get(voice, voice)
