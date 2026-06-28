"""Interview follow-up prompt profile (Phase 1).

This module implements the ``interview_followup`` OperationProfile using the
PromptPlan assembly layer.

Key design decisions (per design doc §6):
- Readiness drives focus section selection (one section per missing dimension).
- Option mode is state-dependent: ``abc`` | ``two_actions`` | ``none``.
- Stable sections (role, task contract, output scope) stay in the system prompt.
- Dynamic sections (episode context, focus, options, memory, transcript) go in
  the user message so the stable prefix can be cached in future provider integrations.
- Legacy compatibility: ``INTERVIEW_STREAM_SYSTEM_PROMPT``,
  ``build_interview_stream_user_content``, ``InterviewPromptInput``,
  ``build_prompt_input``, and ``build_question`` are still exported so existing
  provider and service code continues to work without changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

from app.orchestration.prompts.registry import (
    PROMPT_VERSION,
    CachePolicy,
    PromptPlan,
    PromptSection,
    assemble_plan,
)

if TYPE_CHECKING:
    from app.domain.session import SessionRecord
    from app.domain.transcript import Speaker, TranscriptRecord
    from app.orchestration.readiness import ReadinessReport


# ---------------------------------------------------------------------------
# Stable system-prompt sections (shared across all interview_followup calls)
# ---------------------------------------------------------------------------

_SECTION_CORE_IDENTITY = PromptSection(
    section_id="core_identity",
    content=(
        "You are The Archivist, a perceptive conversation partner helping the user "
        "explore their ideas and gather material for a podcast script. "
        "Respond in a warm, companion-like tone — engaged and curious, never dry or robotic."
    ),
    cache_policy=CachePolicy.STABLE,
    required=True,
)

_SECTION_TASK_CONTRACT = PromptSection(
    section_id="task_contract",
    content=(
        "Your task is to gather enough material for a solo podcast script with a hook, "
        "a clear argument, supporting detail, and a conclusion. "
        "In each turn, ask exactly one high-value follow-up question and nothing else."
    ),
    cache_policy=CachePolicy.STABLE,
    required=True,
)

_SECTION_OUTPUT_SCOPE = PromptSection(
    section_id="output_scope",
    content=(
        "You must NOT write the podcast script at any point during the interview. "
        "Do not invent user facts. Do not switch into long-form narration. "
        "Match the language of the user's replies."
    ),
    cache_policy=CachePolicy.STABLE,
    required=True,
)

# ---------------------------------------------------------------------------
# Stable focus sections — loaded individually based on the missing dimension
# ---------------------------------------------------------------------------

_FOCUS_SECTIONS: dict[str, PromptSection] = {
    "topic_context": PromptSection(
        section_id="focus.topic_context",
        content=(
            "Priority dimension to explore: TOPIC CONTEXT.\n"
            "The user has not yet explained what triggered this topic, its background, "
            "or why it feels relevant right now. Guide them toward the specific moment, "
            "event, or context that prompted this episode idea."
        ),
        cache_policy=CachePolicy.STABLE,
    ),
    "core_viewpoint": PromptSection(
        section_id="focus.core_viewpoint",
        content=(
            "Priority dimension to explore: CORE VIEWPOINT.\n"
            "The user's central thesis or belief about this topic is still unclear. "
            "Help them articulate what they actually think, believe, or want to argue — "
            "their thesis, their contrarian take, or the main problem they want to address."
        ),
        cache_policy=CachePolicy.STABLE,
    ),
    "example_or_detail": PromptSection(
        section_id="focus.example_or_detail",
        content=(
            "Priority dimension to explore: CONCRETE EXAMPLE OR DETAIL.\n"
            "The episode needs at least one real story, case, or specific detail to make "
            "the viewpoint tangible. Guide the user toward a personal story, concrete "
            "case study, or specific data point that illustrates their point."
        ),
        cache_policy=CachePolicy.STABLE,
    ),
    "conclusion": PromptSection(
        section_id="focus.conclusion",
        content=(
            "Priority dimension to explore: CONCLUSION OR TAKEAWAY.\n"
            "The episode needs a clear ending. Help the user articulate what they want "
            "listeners to remember, feel, or do after hearing this episode — one "
            "actionable insight, philosophical takeaway, or open question."
        ),
        cache_policy=CachePolicy.STABLE,
    ),
    "revision": PromptSection(
        section_id="focus.revision",
        content=(
            "A script draft has already been generated. The user is now gathering "
            "material for a new version. Frame follow-up questions around improving "
            "the existing draft: what to add, refine, or adjust in the core argument, "
            "tone, or structure."
        ),
        cache_policy=CachePolicy.STABLE,
    ),
}

# ---------------------------------------------------------------------------
# Option mode sections — how the response should be structured
# ---------------------------------------------------------------------------

_OPTION_MODE_SECTIONS: dict[str, PromptSection] = {
    "abc": PromptSection(
        section_id="option_mode.abc",
        content=(
            "Structure your response exactly:\n"
            "1. Briefly reflect on the user's latest input (1-2 sentences).\n"
            "2. Ask one focused follow-up question tied to the priority dimension above.\n"
            "3. Offer 2-3 specific answer directions labeled A, B, and C.\n"
            "4. Recommend one option and explain why it is the most useful next step.\n"
            "5. End with a warm reminder that the user can ignore the options and answer freely."
        ),
        cache_policy=CachePolicy.STABLE,
    ),
    "none": PromptSection(
        section_id="option_mode.none",
        content=(
            "The user is clearly engaged and giving detailed answers. Do NOT offer A/B/C options.\n"
            "Structure your response:\n"
            "1. Briefly acknowledge what the user shared (1 sentence).\n"
            "2. Ask one sharper, deeper follow-up question that pushes further into the nuance. "
            "Make the question specific, not generic."
        ),
        cache_policy=CachePolicy.STABLE,
    ),
    "two_actions": PromptSection(
        section_id="option_mode.two_actions",
        content=(
            "The episode material is nearly complete. Offer exactly two practical next steps:\n"
            "A. Generate the podcast script draft now (recommended).\n"
            "B. Add one more concrete detail or story before generating.\n"
            "Keep the response short. Affirm that the material gathered so far is strong."
        ),
        cache_policy=CachePolicy.STABLE,
    ),
}


# ---------------------------------------------------------------------------
# Public assembly function
# ---------------------------------------------------------------------------

def build_interview_prompt_plan(
    *,
    topic: str,
    creation_intent: str,
    transcript: "TranscriptRecord",
    readiness: "ReadinessReport",
    script_exists: bool,
    memory_context: str = "",
    transcript_text: str,
) -> PromptPlan:
    """Assemble a PromptPlan for the interview_followup operation profile.

    Section selection rules (§6.1, §6.2):
    - Revision mode (script_exists): load focus.revision section, use abc option mode.
    - Near-ready (3/4 dims done, not yet ready): use two_actions option mode.
    - Detailed last user answer (>250 chars): use none option mode (no A/B/C).
    - Otherwise: load the first missing focus section, use abc option mode.
    """
    from app.domain.transcript import Speaker

    missing = readiness.missing_dimensions()
    option_mode = _determine_option_mode(readiness, transcript, script_exists)

    # --- Gate decisions recorded in metadata ---
    gates: dict[str, object] = {
        "script_exists": script_exists,
        "option_mode": option_mode,
        "suggested_focus": _resolve_focus(missing, script_exists),
        "missing_dimensions": list(missing),
        "has_memory_context": bool(memory_context.strip()),
    }

    omitted: list[dict[str, str]] = []

    # ---- System sections (stable, ordered for cache-friendly prefix) ----
    system_sections: list[PromptSection] = [
        _SECTION_CORE_IDENTITY,
        _SECTION_TASK_CONTRACT,
        _SECTION_OUTPUT_SCOPE,
    ]

    # Load the focus section — one section for the dimension being explored.
    focus_key = _resolve_focus(missing, script_exists)
    focus_section = _FOCUS_SECTIONS.get(focus_key)
    if focus_section:
        system_sections.append(focus_section)
    else:
        omitted.append({"section_id": "focus.*", "reason": "ready_to_generate — no missing dimensions"})

    # Load the option mode section.
    option_section = _OPTION_MODE_SECTIONS.get(option_mode)
    if option_section:
        system_sections.append(option_section)

    # ---- User sections (dynamic, contain per-turn content) ----
    user_sections: list[PromptSection] = []

    # Episode context: topic, intent, missing dimensions.
    user_sections.append(PromptSection(
        section_id="episode_context",
        content=(
            f"Session topic: {topic}\n"
            f"Creation intent: {creation_intent}\n"
            f"Still missing dimensions: {', '.join(missing) or '(none)'}"
        ),
        cache_policy=CachePolicy.SESSION_STABLE,
    ))

    # Memory context: compact hints only, omitted when empty.
    if memory_context.strip():
        user_sections.append(PromptSection(
            section_id="memory_context",
            content=memory_context.strip(),
            cache_policy=CachePolicy.DYNAMIC,
        ))
    else:
        omitted.append({"section_id": "memory_context", "reason": "no memory context available"})

    # Full transcript (private — contains user text).
    transcript_block = transcript_text.strip() or (
        "(No messages yet — produce a short opening question for the guest.)"
    )
    user_sections.append(PromptSection(
        section_id="transcript",
        content=f"Transcript so far:\n{transcript_block}",
        cache_policy=CachePolicy.PRIVATE_DYNAMIC,
    ))

    # Final instruction.
    user_sections.append(PromptSection(
        section_id="final_request",
        content=(
            "Respond as a perceptive conversation partner. "
            "Follow the structure in the system instructions above. "
            "Keep the response natural, warm, and conversational."
        ),
        cache_policy=CachePolicy.STABLE,
    ))

    return assemble_plan(
        operation_profile="interview_followup",
        prompt_version=PROMPT_VERSION,
        system_sections=system_sections,
        user_sections=user_sections,
        gates=gates,
        omitted_sections=omitted,
    )


def _resolve_focus(missing: list[str], script_exists: bool) -> str:
    """Return the focus key to use for section selection."""
    if script_exists:
        return "revision"
    return missing[0] if missing else "ready_to_generate"


def _determine_option_mode(
    readiness: "ReadinessReport",
    transcript: "TranscriptRecord",
    script_exists: bool,
) -> str:
    """Determine option mode per §6.2 rules.

    Returns one of: ``"abc"``, ``"none"``, ``"two_actions"``.
    """
    from app.domain.transcript import Speaker

    done_count = sum([
        readiness.topic_context,
        readiness.core_viewpoint,
        readiness.example_or_detail,
        readiness.conclusion,
    ])

    # Near-ready: 3/4 dimensions done, or already fully ready.
    if done_count >= 3:
        return "two_actions"

    # Revision mode always gets abc (content differs via focus.revision section).
    if script_exists:
        return "abc"

    # Detailed last user answer → one sharper question, no A/B/C.
    user_turns = [t for t in transcript.turns if t.speaker == Speaker.USER]
    if user_turns and len(user_turns[-1].content) > 250:
        return "none"

    return "abc"


# ---------------------------------------------------------------------------
# Backward-compatibility layer
# ---------------------------------------------------------------------------
# The symbols below maintain the same public interface as the old prompts.py
# so that existing provider and service imports continue to work unchanged.

# Used directly by openai_compatible.py as the system prompt constant.
INTERVIEW_STREAM_SYSTEM_PROMPT = (
    "You are The Archivist, a perceptive conversation partner helping the user explore their ideas "
    "and gather material for a podcast script. Respond in a warm, companion-like tone. "
    "In each turn, briefly reflect the user's point, ask one high-value follow-up question, "
    "offer 2-3 structured answer options labeled A, B, and C, recommend one of them with a rationale, "
    "and make clear the user can respond freely. Avoid sounding like a dry interrogation or a quiz. "
    "Keep everything tightly grounded in the user's context and avoid generic platitudes."
)


def build_interview_stream_user_content(
    *,
    topic: str,
    creation_intent: str,
    missing_dimensions: list[str],
    transcript_text: str,
    script_exists: bool,
    suggested_focus: str,
    memory_context: str = "",
) -> str:
    """Legacy user-message builder — kept for backward compatibility.

    New code should call ``build_interview_prompt_plan`` directly.
    The provider will use ``plan.user`` in preference to this function when
    ``prompt_plan`` is supplied in ``InterviewQuestionRequest``.
    """
    missing = ", ".join(missing_dimensions) or "(none)"
    transcript_block = transcript_text.strip() or (
        "(No messages yet — produce a short opening question for the guest.)"
    )
    instructions = _build_legacy_instructions(
        script_exists=script_exists,
        suggested_focus=suggested_focus,
    )
    memory_block = f"{memory_context.strip()}\n\n" if memory_context.strip() else ""
    return (
        f"Session topic: {topic}\n"
        f"Creation intent: {creation_intent}\n"
        f"Still missing dimensions: {missing}\n\n"
        f"{memory_block}"
        f"Transcript so far:\n{transcript_block}\n\n"
        f"Respond as a perceptive conversation partner in the same language as the user. "
        f"Instructions:\n{instructions}\n"
        "Keep the response natural, warm, and conversational. Do not write the podcast script."
    )


def build_interview_stream_instructions(*, script_exists: bool, suggested_focus: str) -> str:
    """Legacy helper — kept as a backward-compatible alias."""
    return _build_legacy_instructions(script_exists=script_exists, suggested_focus=suggested_focus)


def _build_legacy_instructions(*, script_exists: bool, suggested_focus: str) -> str:
    if script_exists:
        return (
            "A draft script has already been generated for this topic, and the user is now coming back to provide more details or changes.\n"
            "Frame your response to guide them in gathering material for a NEW script version. "
            "Your response must follow this structure exactly:\n"
            "1. Briefly reflect on the user's latest input, framing it as a valuable addition for the new script version.\n"
            "2. Ask one focused follow-up question regarding how this input shapes the episode or what specific detail they want to expand next.\n"
            "3. Offer 2-3 answer directions labeled A, B, and C (e.g., A. Add a new concrete example, B. Adjust the core argument, C. Explain how they want this version to differ from the previous script).\n"
            "4. Recommend one option and explain why it makes sense.\n"
            "5. Conclude with a warm reminder that they can ignore the options and answer in their own way.\n"
        )
    return (
        f"You are still missing some elements to build a complete solo episode. Priority dimension to explore next: {suggested_focus}.\n"
        "Your response must follow this structure exactly:\n"
        "1. Briefly reflect on the user's latest point.\n"
        f"2. Ask one high-value follow-up question tied to exploring the '{suggested_focus}' dimension.\n"
        "3. Offer 2-3 specific answer directions labeled A, B, and C to help the user respond easily.\n"
        "4. Recommend one option and explain why it is the most critical next step.\n"
        "5. Conclude with a warm reminder that they can ignore the options and answer in their own way.\n"
    )


@dataclass(frozen=True, slots=True)
class InterviewPromptInput:
    session_id: str
    topic: str
    creation_intent: str
    state: str
    transcript_turn_count: int
    missing_dimensions: list[str]
    suggested_focus: str
    role_instruction: str
    goal_instruction: str
    strategy_instruction: str
    boundary_instruction: str

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "creation_intent": self.creation_intent,
            "state": self.state,
            "transcript_turn_count": self.transcript_turn_count,
            "missing_dimensions": self.missing_dimensions,
            "suggested_focus": self.suggested_focus,
            "role_instruction": self.role_instruction,
            "goal_instruction": self.goal_instruction,
            "strategy_instruction": self.strategy_instruction,
            "boundary_instruction": self.boundary_instruction,
        }


def build_prompt_input(
    session: "SessionRecord",
    transcript: "TranscriptRecord",
    readiness: "ReadinessReport",
) -> "InterviewPromptInput":
    missing = readiness.missing_dimensions()
    focus = missing[0] if missing else "ready_to_generate"

    return InterviewPromptInput(
        session_id=session.session_id,
        topic=session.topic,
        creation_intent=session.creation_intent,
        state=session.state.value,
        transcript_turn_count=len(transcript.turns),
        missing_dimensions=missing,
        suggested_focus=focus,
        role_instruction=(
            "You are a perceptive podcast interviewer helping the user clarify a "
            "real point of view."
        ),
        goal_instruction=(
            "Gather enough material for a solo podcast script with a hook, a "
            "clear argument, supporting detail, and a conclusion."
        ),
        strategy_instruction=(
            "Ask one high-value follow-up that fills the most important missing "
            "dimension first."
        ),
        boundary_instruction=(
            "Do not invent user details, ask multiple unrelated questions at once, "
            "or switch into long-form script writing."
        ),
    )


def build_question(
    prompt_input: InterviewPromptInput,
    last_user_turn: str = "",
    is_zh: bool = False,
) -> str:
    """Deterministic fallback question when the LLM call fails or is mocked.

    Mirrors the legacy prompts.py build_question output exactly.
    """
    focus = prompt_input.suggested_focus

    if last_user_turn:
        if is_zh:
            # Use \u201c/\u201d (curly quotes) to preserve original text; single-quote
            # outer f-string avoids tokenizer conflict with ASCII " delimiters.
            reflection = f'\u5173\u4e8e\u4f60\u63d0\u5230\u7684\u201c{last_user_turn}\u201d\uff0c\u6211\u7406\u89e3\u4e86\u3002\u63a5\u4e0b\u6765\u6211\u4eec\u91cd\u70b9\u8ba8\u8bba\u4e00\u4e0b\u4f60\u7684{focus}\u3002'
        else:
            reflection = f"I hear you on '{last_user_turn}'. Let's focus on exploring your {focus} next."
    else:
        if is_zh:
            reflection = f"我们开始吧，接下来重点讨论一下你的{focus}。"
        else:
            reflection = f"Let's focus on exploring your {focus} next."

    if focus == "topic_context":
        if is_zh:
            return (
                f"{reflection}\n你想把'{prompt_input.topic}'做成播客。关于这个话题，现在是什么事情或者什么契机让你想聊它？\n\n"
                "A. 描述触发这个想法的精确时刻或事件。\n"
                "B. 讨论这个话题背后的背景环境或情况。\n"
                "C. 解释为什么这个话题在今天对你来说很紧迫或相关。\n\n"
                "推荐从 A 开始，因为一个具体的触发时刻能构成一个很好的开场钩子。当然，如果你想忽略这些选项，直接按照你的方式回答也可以。"
            )
        return (
            f"{reflection}\nYou want to turn '{prompt_input.topic}' into a podcast. What happened or what prompted this topic for you right now?\n\n"
            "A. Describe the exact moment or incident that triggered this idea.\n"
            "B. Discuss the background environment or circumstances around the topic.\n"
            "C. Explain why this topic feels urgent or relevant to you today.\n\n"
            "I recommend starting with A, as a specific triggering moment makes a great hook. "
            "But feel free to ignore these options and answer in your own way."
        )
    if focus == "core_viewpoint":
        if is_zh:
            return (
                f"{reflection}\n关于这个话题，你想表达或论证的核心观点是什么？\n\n"
                "A. 直接陈述你的核心论点或观点。\n"
                "B. 强调大多数人对此有什么误解，以及你的相反观点是什么。\n"
                "C. 解释你想解决的主要问题或挑战。\n\n"
                "推荐从 A 开始，以建立一个清晰的锚点。当然，如果你想忽略这些选项，直接按照你的方式回答也可以。"
            )
        return (
            f"{reflection}\nWhat is the main thing you believe or want to argue about this topic?\n\n"
            "A. State your core thesis or viewpoint directly.\n"
            "B. Highlight what most people get wrong about this and what your contrarian take is.\n"
            "C. Explain the main problem or challenge you want to address.\n\n"
            "I recommend starting with A to establish a clear anchor. "
            "But feel free to ignore these options and answer in your own way."
        )
    if focus == "example_or_detail":
        if is_zh:
            return (
                f"{reflection}\n你能给我一个具体的例子、故事或细节，让这个观点感觉更真实吗？\n\n"
                "A. 讲述一个具体的个人故事或案例研究。\n"
                "B. 详细梳理这个在实践中是如何运作的具体例子。\n"
                "C. 分享具体的数据、引用或描述性观察。\n\n"
                "推荐从 A 开始，因为个人叙事对听众来说非常吸引人。当然，如果你想忽略这些选项，直接按照你的方式回答也可以。"
            )
        return (
            f"{reflection}\nCan you give me one concrete example, story, or detail that makes this point feel real?\n\n"
            "A. Relate a specific personal story or case study.\n"
            "B. Walk through a detailed step-by-step example of how this plays out in practice.\n"
            "C. Share specific data points, quotes, or descriptive observations.\n\n"
            "I recommend starting with A, as personal narratives are highly engaging for listeners. "
            "But feel free to ignore these options and answer in your own way."
        )
    if focus == "conclusion":
        if is_zh:
            return (
                f"{reflection}\n如果听众只记住这一期节目的一点收获或结论，那应该是什么？\n\n"
                "A. 提供一个可操作的具体建议或关键教训。\n"
                "B. 总结出一个最终的哲学感悟或总结陈词。\n"
                "C. 为听众留下一个行动号召或开放性问题来思考。\n\n"
                "推荐从 A 开始，为听众提供即时的价值。当然，如果你想忽略这些选项，直接按照你的方式回答也可以。"
            )
        return (
            f"{reflection}\nIf listeners remember one takeaway or conclusion from this episode, what should it be?\n\n"
            "A. Provide a single, actionable piece of advice or key lesson.\n"
            "B. Formulate a final philosophical takeaway or summary statement.\n"
            "C. Issue a call-to-action or open-ended question for listeners to ponder.\n\n"
            "I recommend starting with A to give listeners immediate value. "
            "But feel free to ignore these options and answer in your own way."
        )
    # ready_to_generate / unknown
    if is_zh:
        return (
            "我已经收集了足够的素材来起草这一期节目。如果你愿意，我们可以结束采访并开始生成脚本。\n\n"
            "A. 现在生成播客脚本草稿（推荐）\n"
            "B. 先添加另一个具体细节或故事\n"
            "C. 先调整这一期的核心角度"
        )
    return (
        "I have enough material to draft the episode. If you want, we can stop "
        "the interview and move to script generation.\n\n"
        "A. Generate the podcast script draft now (Recommended)\n"
        "B. Add another concrete detail or story first\n"
        "C. Adjust the core angle of this episode"
    )
