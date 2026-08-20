from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.providers.tts_api.base import SpeechBreak
from app.providers.tts_local_mlx.adapters.base import (
    AdapterRequest,
    Chunker,
    MLXTTSAdapter,
    PreparedSegment,
    PreparedSynthesis,
    moss_language,
    normalize_breaks,
)
from app.providers.tts_local_mlx.capabilities import CloneMode, normalize_clone_mode


_RAW_PAUSE_MARKER = re.compile(r"\[pause\s+[^\]]+\]", re.IGNORECASE)


class MossTTSAdapter(MLXTTSAdapter):
    def prepare_synthesis(
        self,
        text: str,
        breaks: Iterable[SpeechBreak],
        chunker: Chunker,
    ) -> PreparedSynthesis:
        if _RAW_PAUSE_MARKER.search(text):
            raise ValueError(
                "Raw MOSS pause markers are not allowed in script text; use structured breaks."
            )
        normalized = normalize_breaks(text, breaks)
        provider_text = inject_pause_markers(text, normalized)
        return PreparedSynthesis(
            segments=tuple(PreparedSegment(chunk.text) for chunk in chunker(provider_text))
        )

    def generation_kwargs(
        self,
        text: str,
        request: AdapterRequest,
    ) -> dict[str, Any]:
        mode = normalize_clone_mode(request.clone_mode)
        kwargs: dict[str, Any] = {"text": text, "mode": "generation"}
        language = moss_language(request.language)
        if language:
            kwargs["language"] = language
        if request.reference_audio_path.strip():
            kwargs["ref_audio"] = request.reference_audio_path.strip()
        if mode == CloneMode.CONTINUATION:
            kwargs["mode"] = "continuation"
            kwargs["ref_text"] = request.reference_text.strip()
        return kwargs


def inject_pause_markers(
    text: str,
    breaks: tuple[SpeechBreak, ...],
) -> str:
    provider_text = text
    for item in reversed(breaks):
        seconds = item.duration_ms / 1000.0
        formatted = f"{seconds:.3f}".rstrip("0").rstrip(".")
        if "." not in formatted:
            formatted += ".0"
        marker = f"[pause {formatted}s]"
        provider_text = provider_text[: item.offset] + marker + provider_text[item.offset :]
    return provider_text
