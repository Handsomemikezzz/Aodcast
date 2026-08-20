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
            if request.reference_audio_path.strip():
                kwargs["ref_audio"] = request.reference_audio_path.strip()
                if mode != CloneMode.SPEAKER and request.reference_text.strip():
                    kwargs["ref_text"] = request.reference_text.strip()
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
