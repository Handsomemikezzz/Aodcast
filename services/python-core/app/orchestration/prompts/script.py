"""Script generation prompt profile (Phase 2).

Delivers:
- ``EpisodeBrief``       — deterministic intermediate built from tagged transcript turns.
- ``ScriptStyleProfile`` — lightweight derived style (tone/structure/length/language).
- ``build_episode_brief``      — deterministic construction, no extra LLM call.
- ``build_script_style_profile`` — derives style from session + transcript signals.
- ``build_script_prompt_plan`` — assembles the ``script_generation`` PromptPlan.

Backward-compatibility:
  ``SCRIPT_GENERATION_SYSTEM_PROMPT`` and ``build_script_generation_user_prompt``
  remain exported so the legacy provider path continues to work until all callers
  migrate to the PromptPlan path.

Design references: §7 of the dynamic prompt design document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.orchestration.prompts.registry import (
    PROMPT_VERSION,
    CachePolicy,
    PromptPlan,
    PromptSection,
    assemble_plan,
)

if TYPE_CHECKING:
    from app.domain.session import SessionRecord
    from app.domain.transcript import TranscriptRecord


# ---------------------------------------------------------------------------
# Domain objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EpisodeBrief:
    """Deterministic intermediate object built from tagged transcript turns.

    Primary signal is ``interview_focus`` metadata on user turns.
    Keyword/readiness heuristics serve as fallback for legacy untagged turns.
    """

    topic: str
    creation_intent: str
    language: str
    topic_trigger: str
    core_viewpoint: str
    supporting_examples: tuple[str, ...]
    tensions_or_tradeoffs: tuple[str, ...]
    desired_takeaway: str
    evidence_turn_ids: tuple[str, ...]
    recent_user_turns: tuple[str, ...]
    omitted_agent_turn_count: int
    used_full_transcript: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "creation_intent": self.creation_intent,
            "language": self.language,
            "topic_trigger": self.topic_trigger,
            "core_viewpoint": self.core_viewpoint,
            "supporting_examples": list(self.supporting_examples),
            "tensions_or_tradeoffs": list(self.tensions_or_tradeoffs),
            "desired_takeaway": self.desired_takeaway,
            "evidence_turn_ids": list(self.evidence_turn_ids),
            "recent_user_turns": [t[:120] for t in self.recent_user_turns],
            "omitted_agent_turn_count": self.omitted_agent_turn_count,
            "used_full_transcript": self.used_full_transcript,
        }


@dataclass(frozen=True, slots=True)
class ScriptStyleProfile:
    """Lightweight style descriptor derived from session and transcript signals.

    ``source`` records how the profile was derived so it can be logged with
    generation metadata and future UI can explain the decision.
    """

    language: str        # "zh" | "en" | "mixed"
    tone: str            # "reflective" | "commentary" | "practical" | "narrative"
    structure: str       # "narrative_argument" | "tutorial" | "retrospective"
    target_length: str   # "short" | "medium" | "long"
    reasoning_mode: str  # "synthesis" | "description" | "argument"
    source: str          # "transcript_analysis"

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "tone": self.tone,
            "structure": self.structure,
            "target_length": self.target_length,
            "reasoning_mode": self.reasoning_mode,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Stable system prompt sections (shared across all script_generation calls)
# ---------------------------------------------------------------------------

_SECTION_CORE_TASK = PromptSection(
    section_id="script.core_task",
    content=(
        "You write solo podcast narration that will be sent directly to text-to-speech. "
        "Every character you output will be spoken aloud. "
        "Transform the provided interview material into a strong, engaging spoken essay."
    ),
    cache_policy=CachePolicy.STABLE,
    required=True,
)

_SECTION_OUTPUT_CONTRACT = PromptSection(
    section_id="script.output_contract",
    content=(
        "Forbidden (never include any of these):\n"
        "- Preambles or meta text (e.g. 'Here is the script', '根据对话撰写').\n"
        "- Markdown formatting: no headings, bullet points, horizontal rules, or titles.\n"
        "- Speaker labels (e.g. Host:, 主播:, **主播:**).\n"
        "- Stage directions, SFX, music cues, or production notes.\n"
        "- Section labels (e.g. Opening, Body, Closing, 开场, 正文, 结尾).\n"
        "- Emojis or decorative symbols.\n\n"
        "Return only the spoken narration text. "
        "Do NOT invent user facts not supported by the provided material."
    ),
    cache_policy=CachePolicy.STABLE,
    required=True,
)

_SECTION_REASONING_SHAPE = PromptSection(
    section_id="script.reasoning_shape",
    content=(
        "Reasoning shape (use internally, do NOT label these in output):\n"
        "1. What triggered this topic — the opening hook.\n"
        "2. What does the user believe, and why does that belief matter.\n"
        "3. What concrete example or detail makes it real.\n"
        "4. What tension, conflict, or tradeoff gives this topic depth.\n"
        "5. What should the listener ultimately take away."
    ),
    cache_policy=CachePolicy.STABLE,
    required=True,
)

# ---------------------------------------------------------------------------
# Tone section templates — session_stable (one loaded per script call)
# ---------------------------------------------------------------------------

_TONE_SECTIONS: dict[str, PromptSection] = {
    "reflective": PromptSection(
        section_id="script.tone.reflective",
        content=(
            "Tone guidance: Thoughtful, calm, and reflective. "
            "Write continuous spoken prose organized as natural paragraphs separated by a blank line. "
            "Build a logical progression from trigger → viewpoint → example → tension → takeaway. "
            "Match the language of the source material."
        ),
        cache_policy=CachePolicy.SESSION_STABLE,
    ),
    "commentary": PromptSection(
        section_id="script.tone.commentary",
        content=(
            "Tone guidance: Sharp, direct, and opinionated. "
            "Lead with the contrarian or provocative angle, then back it up with evidence. "
            "Keep sentences tight; avoid hedging language. "
            "Match the language of the source material."
        ),
        cache_policy=CachePolicy.SESSION_STABLE,
    ),
    "practical": PromptSection(
        section_id="script.tone.practical",
        content=(
            "Tone guidance: Clear, instructional, and concrete. "
            "Move logically from problem → approach → example → outcome → key takeaway. "
            "Prefer specific over vague; use the user's own terms and examples. "
            "Match the language of the source material."
        ),
        cache_policy=CachePolicy.SESSION_STABLE,
    ),
    "narrative": PromptSection(
        section_id="script.tone.narrative",
        content=(
            "Tone guidance: Story-forward and vivid. "
            "Open with a scene or moment, then weave the viewpoint through the narrative. "
            "Prioritize sensory and emotional grounding. "
            "Match the language of the source material."
        ),
        cache_policy=CachePolicy.SESSION_STABLE,
    ),
}


# ---------------------------------------------------------------------------
# Public assembly functions
# ---------------------------------------------------------------------------

def build_episode_brief(
    topic: str,
    creation_intent: str,
    transcript: "TranscriptRecord",
    *,
    full_transcript_char_budget: int = 3000,
) -> EpisodeBrief:
    """Build an EpisodeBrief deterministically from tagged transcript turns.

    Primary signal: ``turn.metadata["interview_focus"]`` set during the interview.
    Fallback: keyword heuristics from the existing readiness module, used only
    when a user turn has no metadata (legacy transcript).

    Selection logic:
    - Short transcripts (≤ char_budget user-turn chars): ``used_full_transcript=True``
    - Long transcripts: group by focus tag; pick most representative content per dim.
    """
    from app.domain.transcript import Speaker
    from app.orchestration.readiness import (
        _contains_conclusion,  # type: ignore[attr-defined]
        _contains_example_or_detail,  # type: ignore[attr-defined]
        _contains_viewpoint,  # type: ignore[attr-defined]
    )

    user_turns = [t for t in transcript.turns if t.speaker == Speaker.USER]
    agent_turns = [t for t in transcript.turns if t.speaker == Speaker.AGENT]
    total_user_chars = sum(len(t.content) for t in user_turns)

    # Detect language from topic + user turns
    all_text = topic + "".join(t.content for t in user_turns)
    cjk_count = sum(1 for c in all_text if "\u3400" <= c <= "\u9fff" or "\uf900" <= c <= "\ufaff")
    latin_words = len(all_text.split())
    if cjk_count > latin_words * 0.5:
        language = "zh"
    elif cjk_count > 0:
        language = "mixed"
    else:
        language = "en"

    use_full = total_user_chars <= full_transcript_char_budget or len(transcript.turns) <= 16

    # Group user turns by interview_focus metadata
    focus_groups: dict[str, list] = {
        "topic_context": [],
        "core_viewpoint": [],
        "example_or_detail": [],
        "conclusion": [],
        "unknown": [],
    }
    evidence_ids: list[str] = []

    for turn in user_turns:
        focus = turn.metadata.get("interview_focus") or ""
        content = turn.content.strip()
        if not content:
            continue

        if focus in focus_groups:
            focus_groups[focus].append(turn)
            evidence_ids.append(turn.turn_id)
        else:
            # Legacy untagged turn — classify by keyword heuristics as fallback
            lc = content.lower()
            if _contains_viewpoint(lc) and not focus_groups["core_viewpoint"]:
                focus_groups["core_viewpoint"].append(turn)
                evidence_ids.append(turn.turn_id)
            elif _contains_example_or_detail(lc) and not focus_groups["example_or_detail"]:
                focus_groups["example_or_detail"].append(turn)
                evidence_ids.append(turn.turn_id)
            elif _contains_conclusion(lc) and not focus_groups["conclusion"]:
                focus_groups["conclusion"].append(turn)
                evidence_ids.append(turn.turn_id)
            else:
                if not focus_groups["topic_context"]:
                    focus_groups["topic_context"].append(turn)
                    evidence_ids.append(turn.turn_id)
                else:
                    focus_groups["unknown"].append(turn)

    def _first_content(group: list) -> str:
        return group[0].content.strip() if group else ""

    def _all_contents(group: list) -> tuple[str, ...]:
        return tuple(t.content.strip() for t in group if t.content.strip())

    # Tensions: scan example/viewpoint turns for tension vocabulary
    tensions: list[str] = []
    tension_keywords = (
        "but", "however", "tension", "tradeoff", "paradox",
        "conflict", "contradiction", "on the other hand", "despite",
        "但是", "然而", "矛盾", "张力", "反而", "尽管",
    )
    for t in (focus_groups["example_or_detail"] + focus_groups["core_viewpoint"]):
        if any(kw in t.content.lower() for kw in tension_keywords):
            tensions.append(t.content.strip())
            break  # one entry is enough for the brief

    # Recent user turns (last 3) for freshness
    recent = tuple(t.content.strip() for t in user_turns[-3:])

    return EpisodeBrief(
        topic=topic,
        creation_intent=creation_intent,
        language=language,
        topic_trigger=_first_content(focus_groups["topic_context"]),
        core_viewpoint=_first_content(focus_groups["core_viewpoint"]),
        supporting_examples=_all_contents(focus_groups["example_or_detail"]),
        tensions_or_tradeoffs=tuple(tensions),
        desired_takeaway=_first_content(focus_groups["conclusion"]),
        evidence_turn_ids=tuple(dict.fromkeys(evidence_ids)),  # deduplicate, preserve order
        recent_user_turns=recent,
        omitted_agent_turn_count=len(agent_turns),
        used_full_transcript=use_full,
    )


def build_script_style_profile(
    session: "SessionRecord",
    transcript: "TranscriptRecord",
) -> ScriptStyleProfile:
    """Derive a ScriptStyleProfile from session signals and transcript language.

    Intent signals → tone (§7.3):
    - tutorial/how-to/方法/步骤 → "practical"
    - story/personal/经历/narrative → "narrative"
    - opinion/argument/contrarian/观点/批评 → "commentary"
    - default → "reflective"
    """
    from app.domain.transcript import Speaker

    user_turns = [t for t in transcript.turns if t.speaker == Speaker.USER]
    all_user_text = " ".join(t.content for t in user_turns).lower()
    all_text = (session.topic + " " + session.creation_intent + " " + all_user_text).lower()

    # Language detection
    cjk_count = sum(1 for c in all_text if "\u3400" <= c <= "\u9fff" or "\uf900" <= c <= "\ufaff")
    latin_words = len(all_text.split())
    if cjk_count > latin_words * 0.5:
        language = "zh"
    elif cjk_count > 0:
        language = "mixed"
    else:
        language = "en"

    # Tone detection
    practical_signals = ("tutorial", "how to", "how-to", "guide", "step", "method",
                         "教程", "方法", "步骤", "指南", "如何")
    narrative_signals = ("story", "personal", "experience", "journey", "moment",
                         "经历", "故事", "回忆", "历程", "感受")
    commentary_signals = ("opinion", "argue", "argument", "contrarian", "disagree", "problem",
                          "观点", "批评", "反对", "问题", "反思")

    if any(s in all_text for s in practical_signals):
        tone = "practical"
        structure = "tutorial"
    elif any(s in all_text for s in narrative_signals):
        tone = "narrative"
        structure = "retrospective"
    elif any(s in all_text for s in commentary_signals):
        tone = "commentary"
        structure = "narrative_argument"
    else:
        tone = "reflective"
        structure = "narrative_argument"

    # Length: short (< 3 user turns), medium (3-7), long (8+)
    if len(user_turns) < 3:
        target_length = "short"
    elif len(user_turns) < 8:
        target_length = "medium"
    else:
        target_length = "long"

    # Reasoning mode: synthesis for multi-turn; description for short sessions
    reasoning_mode = "synthesis" if len(user_turns) >= 3 else "description"

    return ScriptStyleProfile(
        language=language,
        tone=tone,
        structure=structure,
        target_length=target_length,
        reasoning_mode=reasoning_mode,
        source="transcript_analysis",
    )


def build_script_prompt_plan(
    *,
    topic: str,
    creation_intent: str,
    transcript: "TranscriptRecord",
    style_profile: ScriptStyleProfile,
    brief: EpisodeBrief,
    memory_context: str = "",
    memory_ids_used: list[str] | None = None,
) -> PromptPlan:
    """Assemble the script_generation PromptPlan.

    Selective transcript strategy (§7.2):
    - Short transcript (used_full_transcript=True): send full turn-by-turn text.
    - Long transcript: send EpisodeBrief + recent user turns.

    Section ordering (cache-friendly stable prefix):
    System: core_task → output_contract → reasoning_shape → tone.*
    User:   episode_context → [memory_context] → [brief | transcript] → final_request
    """
    omitted: list[dict[str, str]] = []

    # ---- System sections (stable, tone is session_stable) ----
    system_sections: list[PromptSection] = [
        _SECTION_CORE_TASK,
        _SECTION_OUTPUT_CONTRACT,
        _SECTION_REASONING_SHAPE,
    ]

    # Tone section — derived per session, stable during a script generation session.
    tone_section = _TONE_SECTIONS.get(style_profile.tone, _TONE_SECTIONS["reflective"])
    system_sections.append(tone_section)

    # ---- User sections (dynamic) ----
    user_sections: list[PromptSection] = []

    user_sections.append(PromptSection(
        section_id="script.episode_context",
        content=f"Topic: {topic}\nCreation intent: {creation_intent}",
        cache_policy=CachePolicy.SESSION_STABLE,
    ))

    if memory_context.strip():
        user_sections.append(PromptSection(
            section_id="script.memory_context",
            content=f"Relevant background (long-term memory):\n{memory_context.strip()}",
            cache_policy=CachePolicy.DYNAMIC,
        ))
    else:
        omitted.append({"section_id": "script.memory_context", "reason": "no memory context"})

    # Material: full transcript or selective brief
    if brief.used_full_transcript:
        material_text = _format_full_transcript(transcript)
        material_section_id = "script.full_transcript"
    else:
        material_text = _format_episode_brief(brief)
        material_section_id = "script.episode_brief"
        omitted.append({
            "section_id": "script.full_transcript",
            "reason": f"long transcript ({brief.omitted_agent_turn_count} agent turns omitted)",
        })

    user_sections.append(PromptSection(
        section_id=material_section_id,
        content=material_text,
        cache_policy=CachePolicy.PRIVATE_DYNAMIC,
    ))

    user_sections.append(PromptSection(
        section_id="script.final_request",
        content="Write the full spoken narration now.",
        cache_policy=CachePolicy.STABLE,
    ))

    return assemble_plan(
        operation_profile="script_generation",
        prompt_version=PROMPT_VERSION,
        system_sections=system_sections,
        user_sections=user_sections,
        gates={
            "used_full_transcript": brief.used_full_transcript,
            "tone": style_profile.tone,
            "structure": style_profile.structure,
            "language": style_profile.language,
            "has_memory_context": bool(memory_context.strip()),
            "memory_ids_used": list(memory_ids_used or []),
        },
        omitted_sections=omitted,
    )


def _format_full_transcript(transcript: "TranscriptRecord") -> str:
    lines = [
        f"{turn.speaker.value}: {turn.content}"
        for turn in transcript.turns
        if turn.content.strip()
    ]
    return "Interview transcript:\n" + "\n".join(lines)


def _format_episode_brief(brief: EpisodeBrief) -> str:
    """Format an EpisodeBrief as a structured text block for the prompt."""
    lines: list[str] = ["=== Episode Brief ==="]
    if brief.topic_trigger:
        lines.append(f"Topic trigger: {brief.topic_trigger}")
    if brief.core_viewpoint:
        lines.append(f"Core viewpoint: {brief.core_viewpoint}")
    if brief.supporting_examples:
        examples = "\n  - ".join(brief.supporting_examples)
        lines.append(f"Supporting examples:\n  - {examples}")
    if brief.tensions_or_tradeoffs:
        lines.append(f"Key tension: {brief.tensions_or_tradeoffs[0]}")
    if brief.desired_takeaway:
        lines.append(f"Desired takeaway: {brief.desired_takeaway}")
    if brief.recent_user_turns:
        lines.append("\nRecent user context (most recent first):")
        for turn_content in reversed(brief.recent_user_turns):
            lines.append(f"  - {turn_content[:200]}")
    return "\n".join(lines)


def build_script_generation_metadata(
    *,
    plan: PromptPlan,
    style_profile: ScriptStyleProfile,
    brief: EpisodeBrief,
    provider: str,
    model: str,
    memory_ids_used: list[str] | None = None,
) -> dict[str, Any]:
    """Build the compact generation_metadata dict for ScriptRecord.

    Does NOT include: full prompt text, transcript text, memory bodies, or
    sensitive content (§9.2).
    """
    from app.domain.common import utc_now_iso

    return {
        "prompt_version": plan.metadata.prompt_version,
        "operation_profile": plan.metadata.operation_profile,
        "section_ids": list(plan.metadata.section_ids),
        "style_profile": style_profile.to_dict(),
        "episode_brief_stats": {
            "user_turn_count": len(brief.evidence_turn_ids),
            "agent_turns_omitted": brief.omitted_agent_turn_count,
            "used_full_transcript": brief.used_full_transcript,
        },
        "memory_ids_used": list(memory_ids_used or []),
        "provider": provider,
        "model": model,
        "created_at": utc_now_iso(),
    }


# ---------------------------------------------------------------------------
# Backward-compatibility layer
# ---------------------------------------------------------------------------

SCRIPT_GENERATION_SYSTEM_PROMPT = (
    "You write solo podcast narration that will be sent directly to text-to-speech. "
    "Every character you output will be spoken aloud.\n\n"
    "Goal:\n"
    "Transform the interview transcript into a strong, engaging spoken essay. "
    "Do NOT simply summarize the transcript. Instead, synthesize the material into "
    "a compelling, structured argument with narrative depth.\n\n"
    "Core Requirements:\n"
    "- Tone: Thoughtful, calm, and reflective (not hyped or overly dramatic).\n"
    "- Narrative flow: Write continuous spoken prose only, organized as natural paragraphs "
    "separated by a single blank line.\n"
    "- Preserve authenticity: Retain the user's real ideas, stories, and details. Do NOT "
    "invent facts or make up generic advice/platitudes.\n"
    "- Structural logic: Build a logical progression: introduce what triggered the topic, "
    "the core viewpoint, a concrete example to make it real, and a final takeaway.\n"
    "- Depth & Tension: Surface any tension, contrast, or tradeoff mentioned in the transcript "
    "to give the argument depth and nuance.\n"
    "- Language: Match the language of the transcript.\n\n"
    "Suggested Reasoning Shape (Use this outline internally, do NOT output these outline labels):\n"
    "1. What triggered this topic?\n"
    "2. What does the user believe, and why does that belief matter?\n"
    "3. What concrete example or detail makes it real?\n"
    "4. What tension, conflict, or tradeoff gives this topic depth?\n"
    "5. What should the listener ultimately take away?\n\n"
    "Forbidden (never include these):\n"
    "- Preambles or meta text (e.g. 'Here is the script', '根据对话撰写').\n"
    "- Markdown formatting: no headings, bullet points, horizontal rules, or titles.\n"
    "- Speaker labels (e.g. Host:, 主播:, **主播:**).\n"
    "- Stage directions, SFX, music cues, or production notes (e.g. [opening music], (pause)).\n"
    "- Section labels (e.g. Opening, Body, Closing, 开场, 正文, 结尾).\n"
    "- Emojis or decorative symbols.\n\n"
    "Return only the spoken narration text."
)


def build_script_generation_user_prompt(
    *,
    topic: str,
    creation_intent: str,
    transcript_text: str,
    memory_context: str = "",
) -> str:
    memory_block = f"{memory_context.strip()}\n\n" if memory_context.strip() else ""
    return (
        f"Topic: {topic}\n"
        f"Creation intent: {creation_intent}\n\n"
        f"{memory_block}"
        f"Interview transcript:\n{transcript_text.strip()}\n\n"
        "Write the full spoken narration now."
    )
