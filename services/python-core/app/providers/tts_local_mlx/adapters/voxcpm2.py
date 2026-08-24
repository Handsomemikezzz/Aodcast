from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.providers.tts_api.base import SpeechBreak
from app.providers.tts_local_mlx.adapters.base import (
    AdapterRequest,
    Chunker,
    MLXTTSAdapter,
    PreparedSynthesis,
)
from app.providers.tts_local_mlx.capabilities import CloneMode, normalize_clone_mode
from app.providers.tts_local_mlx.chunker import ScriptChunk, limit_script_chunks


_VOXCPM2_SOFT_MAX_CHARS = 120
_VOXCPM2_INFERENCE_TIMESTEPS = 7
_VOXCPM2_MIN_AUDIO_PATCHES = 64
_VOXCPM2_MAX_AUDIO_PATCHES = 600
_VOXCPM2_AUDIO_PATCHES_PER_CHAR = 4


class VoxCPM2Adapter(MLXTTSAdapter):
    def prepare_synthesis(
        self,
        text: str,
        breaks: Iterable[SpeechBreak],
        chunker: Chunker,
    ) -> PreparedSynthesis:
        def bounded_chunker(value: str) -> list[ScriptChunk]:
            return limit_script_chunks(
                chunker(value),
                soft_max_chars=_VOXCPM2_SOFT_MAX_CHARS,
            )

        return super().prepare_synthesis(text, breaks, bounded_chunker)

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

        # mlx-audio 0.4.6 retains all generated latent patches and decodes them
        # in one AudioVAE call. Bound both text chunks and the stop-prediction
        # fallback so a missed stop cannot grow to the upstream 2,000-patch
        # default. Seven CFM steps is the model card's recommended setting.
        max_tokens = max(
            _VOXCPM2_MIN_AUDIO_PATCHES,
            min(
                _VOXCPM2_MAX_AUDIO_PATCHES,
                len(text) * _VOXCPM2_AUDIO_PATCHES_PER_CHAR,
            ),
        )
        kwargs: dict[str, Any] = {
            "text": text,
            "max_tokens": max_tokens,
            "inference_timesteps": _VOXCPM2_INFERENCE_TIMESTEPS,
            "cfg_value": 2.0,
        }
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
