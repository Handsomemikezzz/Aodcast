from __future__ import annotations

import json

from app.orchestration.prompts.registry import CachePolicy, PromptSection, assemble_plan


SPEECH_DIRECTOR_PROMPT_VERSION = "speech-director-v1"


def build_speech_director_prompt_plan(segments: list[dict[str, object]]):
    system = PromptSection(
        section_id="speech_director.contract",
        cache_policy=CachePolicy.STABLE,
        required=True,
        content=(
            "You are the speech director for a clean, natural Chinese solo podcast. "
            "The target is a skilled human host: semantically appropriate pauses, restrained emotion, varied rhythm, "
            "and clear emphasis without theatrical acting, filler words, stutters, or invented wording. "
            "You must not rewrite, add, remove, or reorder any supplied text. Return JSON only.\n\n"
            "Return {\"segments\":[...]} with exactly one item per input position. Each item must contain: "
            "position (integer), intent (short string), emotion (short string), energy (0..1), pace (0.5..2), "
            "pause_after_ms (0..2000), breaks, emphasis, pronunciations. "
            "breaks items are {\"after_text\":\"exact substring\",\"duration_ms\":integer}; use at most two and only "
            "when punctuation alone is insufficient. emphasis items are {\"text\":\"exact substring\","
            "\"level\":\"light|medium|strong\"}; use sparingly. pronunciations items are "
            "{\"text\":\"exact substring\",\"spoken_as\":\"...\"} and should only resolve genuinely ambiguous names, "
            "numbers, abbreviations, or polyphonic Chinese characters."
        ),
    )
    user = PromptSection(
        section_id="speech_director.segments",
        cache_policy=CachePolicy.PRIVATE_DYNAMIC,
        required=True,
        content=(
            "Plan delivery for these immutable script segments. Preserve every segment exactly as supplied.\n"
            + json.dumps({"segments": segments}, ensure_ascii=False)
        ),
    )
    return assemble_plan(
        operation_profile="speech_director",
        prompt_version=SPEECH_DIRECTOR_PROMPT_VERSION,
        system_sections=[system],
        user_sections=[user],
        gates={"segment_count": len(segments)},
    )
