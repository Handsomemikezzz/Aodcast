from __future__ import annotations

from typing import Any

from app.providers.tts_local_mlx.adapters.base import AdapterRequest, MLXTTSAdapter
from app.providers.tts_local_mlx.capabilities import CloneMode, normalize_clone_mode


class VoxCPM2Adapter(MLXTTSAdapter):
    def generation_kwargs(
        self,
        text: str,
        request: AdapterRequest,
    ) -> dict[str, Any]:
        mode = normalize_clone_mode(request.clone_mode)
        has_reference = bool(request.reference_audio_path.strip())
        has_context = bool(request.context_audio_path.strip())
        has_style = bool(request.style_prompt.strip())
        if mode == CloneMode.AUTO and has_reference:
            if has_style:
                mode = CloneMode.CONTROLLABLE
            elif request.reference_text.strip():
                mode = CloneMode.ULTIMATE
            else:
                mode = CloneMode.SPEAKER

        kwargs: dict[str, Any] = {"text": text}
        if has_style:
            kwargs["instruct"] = request.style_prompt.strip()
        if has_context:
            if has_reference:
                kwargs["ref_audio"] = request.reference_audio_path.strip()
            kwargs.update(
                prompt_audio=request.context_audio_path.strip(),
                prompt_text=request.context_text.strip(),
            )
            return kwargs
        if not has_reference:
            return kwargs

        audio_path = request.reference_audio_path.strip()
        if mode in {
            CloneMode.AUTO,
            CloneMode.SPEAKER,
            CloneMode.CONTROLLABLE,
        }:
            kwargs["ref_audio"] = audio_path
        elif mode == CloneMode.ULTIMATE:
            kwargs.update(
                ref_audio=audio_path,
                prompt_audio=audio_path,
                prompt_text=request.reference_text.strip(),
            )
        elif mode == CloneMode.CONTINUATION:
            kwargs.update(
                prompt_audio=audio_path,
                prompt_text=request.reference_text.strip(),
            )
        return kwargs
