from __future__ import annotations

from typing import Any

from app.providers.tts_local_mlx.adapters.base import (
    AdapterRequest,
    MLXTTSAdapter,
    canonical_language,
)
from app.providers.tts_local_mlx.capabilities import CloneMode, normalize_clone_mode
from app.providers.tts_local_mlx.model_spec import ModelVariant


class Qwen3TTSAdapter(MLXTTSAdapter):
    def generation_kwargs(
        self,
        text: str,
        request: AdapterRequest,
    ) -> dict[str, Any]:
        mode = normalize_clone_mode(request.clone_mode)
        kwargs: dict[str, Any] = {
            "text": text,
            "lang_code": canonical_language(request.language),
            "split_pattern": "",
        }

        if self.spec.variant == ModelVariant.QWEN_BASE:
            conditioning_audio = (
                request.reference_audio_path.strip()
                or request.context_audio_path.strip()
            )
            conditioning_text = (
                request.reference_text.strip()
                if request.reference_audio_path.strip()
                else request.context_text.strip()
            )
            if conditioning_audio:
                kwargs["ref_audio"] = conditioning_audio
                if mode != CloneMode.SPEAKER and conditioning_text:
                    kwargs["ref_text"] = conditioning_text
            elif request.voice.strip():
                kwargs["voice"] = request.voice.strip()
            return kwargs

        if (
            self.spec.variant == ModelVariant.QWEN_CUSTOM_VOICE
            and request.voice.strip()
        ):
            kwargs["voice"] = request.voice.strip()
        if request.style_prompt.strip():
            kwargs["instruct"] = request.style_prompt.strip()
        return kwargs
