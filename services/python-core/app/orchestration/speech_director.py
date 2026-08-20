from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.domain.common import normalize_text_for_hash, sha256_text
from app.domain.project import SessionProject
from app.domain.speech_plan import (
    EmphasisSpan,
    PronunciationSpan,
    SpeechBreak,
    SpeechDelivery,
    SpeechPlan,
    SpeechSegment,
    TextSpan,
)
from app.orchestration.prompts.speech_director import (
    SPEECH_DIRECTOR_PROMPT_VERSION,
    build_speech_director_prompt_plan,
)
from app.providers.llm.base import SpeechPlanGenerationRequest
from app.providers.llm.factory import build_llm_provider
from app.storage.config_store import ConfigStore


_SENTENCE_ENDS = frozenset("。！？!?；;")
_CLOSING_PUNCTUATION = frozenset("\"'”’」』】）)]")
_MIN_SEGMENT_CHARS = 18
_MAX_SEGMENT_CHARS = 280


@dataclass(frozen=True, slots=True)
class RawSpeechSegment:
    text: str
    start: int
    end: int
    paragraph_end: bool


class SpeechDirectorService:
    def __init__(self, config_store: ConfigStore) -> None:
        self.config_store = config_store

    def create_plan(self, project: SessionProject, *, force: bool = False) -> SpeechPlan:
        if project.script is None:
            raise ValueError("Cannot direct speech without a script.")
        script_text = project.script.final.strip() or project.script.draft.strip()
        if not script_text:
            raise ValueError("Cannot direct speech for an empty script.")
        if not force and project.speech_plan is not None and project.speech_plan.is_current_for(script_text):
            return project.speech_plan

        canonical_text = normalize_text_for_hash(script_text)
        raw_segments = split_script_for_speech(canonical_text)
        if not raw_segments:
            raise ValueError("Speech Director could not find any spoken segments.")
        prompt_segments = [
            {
                "position": position,
                "text": item.text,
                "default_pause_after_ms": default_pause_after_ms(item),
            }
            for position, item in enumerate(raw_segments)
        ]
        prompt_plan = build_speech_director_prompt_plan(prompt_segments)
        llm_config = self.config_store.load_llm_config()
        provider = build_llm_provider(llm_config)
        response = provider.generate_speech_plan(
            SpeechPlanGenerationRequest(
                session_id=project.session.session_id,
                script_id=project.script.script_id,
                script_text=canonical_text,
                segments=prompt_segments,
                prompt_plan=prompt_plan,
            )
        )
        directives = {
            int(item.get("position")): item
            for item in response.directives
            if _is_int_like(item.get("position"))
        }
        segments = tuple(
            build_speech_segment(
                project.script.script_id,
                position,
                raw,
                directives.get(position, {}),
            )
            for position, raw in enumerate(raw_segments)
        )
        previous_version = project.speech_plan.version if project.speech_plan is not None else 0
        plan = SpeechPlan(
            plan_id=uuid4().hex,
            version=previous_version + 1,
            session_id=project.session.session_id,
            script_id=project.script.script_id,
            script_hash=sha256_text(canonical_text),
            language=detect_script_language(canonical_text),
            segments=segments,
            director_provider=response.provider_name,
            director_model=response.model_name,
            prompt_version=SPEECH_DIRECTOR_PROMPT_VERSION,
        )
        plan.validate()
        return plan


def split_script_for_speech(script_text: str) -> list[RawSpeechSegment]:
    text = normalize_text_for_hash(script_text)
    if not text:
        return []
    paragraphs: list[tuple[int, int]] = []
    cursor = 0
    for match in re.finditer(r"\n[ \t]*\n", text):
        _append_trimmed_span(text, cursor, match.start(), paragraphs)
        cursor = match.end()
    _append_trimmed_span(text, cursor, len(text), paragraphs)

    output: list[RawSpeechSegment] = []
    for paragraph_start, paragraph_end in paragraphs:
        spans = _sentence_spans(text, paragraph_start, paragraph_end)
        spans = _merge_short_spans(text, spans)
        spans = _split_long_spans(text, spans)
        for index, (start, end) in enumerate(spans):
            output.append(
                RawSpeechSegment(
                    text=text[start:end].strip(),
                    start=start,
                    end=end,
                    paragraph_end=index == len(spans) - 1,
                )
            )
    return output


def _append_trimmed_span(text: str, start: int, end: int, output: list[tuple[int, int]]) -> None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if end > start:
        output.append((start, end))


def _sentence_spans(text: str, start: int, end: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    sentence_start = start
    index = start
    while index < end:
        character = text[index]
        boundary = character in _SENTENCE_ENDS
        if character == "…":
            while index + 1 < end and text[index + 1] == "…":
                index += 1
            boundary = True
        if boundary:
            boundary_end = index + 1
            while boundary_end < end and text[boundary_end] in _CLOSING_PUNCTUATION:
                boundary_end += 1
            _append_trimmed_span(text, sentence_start, boundary_end, spans)
            sentence_start = boundary_end
            index = boundary_end
            continue
        index += 1
    _append_trimmed_span(text, sentence_start, end, spans)
    return spans


def _merge_short_spans(text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if len(spans) <= 1:
        return spans
    merged: list[tuple[int, int]] = []
    for span in spans:
        length = len(text[span[0] : span[1]].strip())
        if merged and length < _MIN_SEGMENT_CHARS:
            previous = merged.pop()
            merged.append((previous[0], span[1]))
        else:
            merged.append(span)
    if len(merged) > 1 and len(text[merged[0][0] : merged[0][1]].strip()) < _MIN_SEGMENT_CHARS:
        first, second = merged[0], merged[1]
        merged[:2] = [(first[0], second[1])]
    return merged


def _split_long_spans(text: str, spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    output: list[tuple[int, int]] = []
    preferred_breaks = frozenset("，,、：: \n")
    for start, end in spans:
        cursor = start
        while end - cursor > _MAX_SEGMENT_CHARS:
            limit = cursor + _MAX_SEGMENT_CHARS
            split = limit
            for index in range(limit - 1, cursor + _MIN_SEGMENT_CHARS, -1):
                if text[index] in preferred_breaks:
                    split = index + 1
                    break
            _append_trimmed_span(text, cursor, split, output)
            cursor = split
        _append_trimmed_span(text, cursor, end, output)
    return output


def default_pause_after_ms(segment: RawSpeechSegment) -> int:
    if segment.paragraph_end:
        return 560
    if segment.text.endswith(("？", "?", "！", "!")):
        return 340
    if segment.text.endswith(("；", ";")):
        return 240
    return 300


def build_speech_segment(
    script_id: str,
    position: int,
    raw: RawSpeechSegment,
    directive: dict[str, Any],
) -> SpeechSegment:
    segment_id = uuid5(NAMESPACE_URL, f"aodcast:{script_id}:{position}:{sha256_text(raw.text)}").hex
    pause_after_ms = _clamp_int(
        directive.get("pause_after_ms"),
        default=default_pause_after_ms(raw),
        minimum=0,
        maximum=2_000,
    )
    breaks: list[SpeechBreak] = []
    for item in _objects(directive.get("breaks"))[:2]:
        after_text = str(item.get("after_text") or "")
        offset = _find_span(raw.text, after_text, prefer_after=True)
        if offset is None or offset >= len(raw.text):
            continue
        breaks.append(
            SpeechBreak(
                offset=offset,
                duration_ms=_clamp_int(item.get("duration_ms"), default=180, minimum=60, maximum=2_000),
            )
        )
    emphasis: list[EmphasisSpan] = []
    for item in _objects(directive.get("emphasis"))[:3]:
        target = str(item.get("text") or "")
        span = _find_range(raw.text, target)
        level = str(item.get("level") or "medium")
        if span is not None and level in {"light", "medium", "strong"}:
            emphasis.append(EmphasisSpan(start=span[0], end=span[1], level=level))
    pronunciation_candidates: list[PronunciationSpan] = []
    for item in _objects(directive.get("pronunciations"))[:3]:
        target = str(item.get("text") or "")
        spoken_as = str(item.get("spoken_as") or "").strip()
        span = _find_range(raw.text, target)
        if span is not None and spoken_as:
            pronunciation_candidates.append(PronunciationSpan(start=span[0], end=span[1], spoken_as=spoken_as))
    pronunciations: list[PronunciationSpan] = []
    for candidate in sorted(
        pronunciation_candidates,
        key=lambda item: (item.start, -(item.end - item.start)),
    ):
        if any(candidate.start < existing.end and existing.start < candidate.end for existing in pronunciations):
            continue
        pronunciations.append(candidate)
    return SpeechSegment(
        segment_id=segment_id,
        position=position,
        text=raw.text,
        source_span=TextSpan(raw.start, raw.end),
        delivery=SpeechDelivery(
            intent=str(directive.get("intent") or ("opening" if position == 0 else "explanation"))[:40],
            emotion=str(directive.get("emotion") or "calm")[:40],
            energy=_clamp_float(directive.get("energy"), default=0.4, minimum=0.0, maximum=1.0),
            pace=_clamp_float(directive.get("pace"), default=1.0, minimum=0.5, maximum=2.0),
        ),
        breaks=tuple(sorted({(item.offset, item.duration_ms): item for item in breaks}.values(), key=lambda item: item.offset)),
        emphasis=tuple(emphasis),
        pronunciations=tuple(pronunciations),
        pause_after_ms=pause_after_ms,
    )


def detect_script_language(text: str) -> str:
    cjk = sum(1 for char in text if "\u3400" <= char <= "\u9fff")
    latin = sum(1 for char in text if char.isascii() and char.isalpha())
    if cjk and latin > cjk * 0.4:
        return "mixed"
    return "zh" if cjk else "en"


def _objects(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _find_range(text: str, target: str) -> tuple[int, int] | None:
    if not target:
        return None
    start = text.find(target)
    if start < 0 or text.find(target, start + 1) >= 0:
        return None
    return (start, start + len(target))


def _find_span(text: str, target: str, *, prefer_after: bool) -> int | None:
    found = _find_range(text, target)
    if found is None:
        return None
    return found[1] if prefer_after else found[0]


def _is_int_like(value: Any) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(maximum, max(minimum, number))


def _clamp_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(maximum, max(minimum, number))
