from __future__ import annotations

from dataclasses import dataclass

from app.domain.session import SessionRecord
from app.domain.transcript import TranscriptRecord
from app.orchestration.readiness import ReadinessReport

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


MEMORY_RERANK_SYSTEM_PROMPT = (
    "You select which long-term memories are most useful for writing the current "
    "podcast script. You return STRICT JSON only: {\"selected_ids\": [\"id1\", ...]}. "
    "Pick at most the requested number, ordered by relevance to the topic and intent. "
    "Only choose from the provided candidate ids. If none are relevant, return "
    "{\"selected_ids\": []}. Do not invent ids and do not add commentary."
)


def build_memory_rerank_user_content(
    *,
    topic: str,
    creation_intent: str,
    candidates: list[dict[str, str]],
    max_select: int,
) -> str:
    candidate_lines = "\n".join(
        f'- id: {c.get("id", "")} | type: {c.get("type", "")} | name: {c.get("name", "")} '
        f'| description: {c.get("description", "")}'
        for c in candidates
    ) or "(no candidates)"
    return (
        f"Topic: {topic}\n"
        f"Creation intent: {creation_intent}\n"
        f"Select at most {max_select} memory ids most useful for this script.\n\n"
        f"Candidates:\n{candidate_lines}\n\n"
        "Return the JSON object now."
    )


MEMORY_MAINTENANCE_SYSTEM_PROMPT = (
    "You consolidate a small group of long-term memories that look like duplicates "
    "of the same topic. You return STRICT JSON only — no prose, no markdown fences.\n\n"
    "Allowed: merge semantic duplicates into one entry, compress redundant wording, "
    "refresh the name/description, and drop duplicate evidence. You may ONLY reuse "
    "evidence turn_ids that already appear in the provided group — never invent facts, "
    "quotes, or turn_ids. Keep the user's original language and meaning.\n\n"
    "Output schema:\n"
    '{"primary_id": "<id to keep, or empty string if no merge>", "name": "...", '
    '"description": "...", "body": "...", "keywords": ["..."], '
    '"evidence_turn_ids": ["<from the group only>"], "drop_ids": ["<ids merged away>"]}\n\n'
    "If the entries are not真正重复 (not truly the same topic), return "
    '{"primary_id": "", "drop_ids": []}. primary_id and every drop_id must be ids '
    "from the group. Do not merge unrelated memories just to reduce count."
)


def build_memory_maintenance_user_content(*, entries: list[dict]) -> str:
    blocks = []
    for entry in entries:
        evidence = "; ".join(
            f'{ev.get("turn_id", "")}:"{ev.get("quote", "")}"' for ev in entry.get("evidence", [])
        )
        blocks.append(
            f'- id: {entry.get("id", "")} | type: {entry.get("type", "")}\n'
            f'  name: {entry.get("name", "")}\n'
            f'  description: {entry.get("description", "")}\n'
            f'  body: {entry.get("body", "")}\n'
            f'  keywords: {", ".join(entry.get("keywords", []))}\n'
            f'  evidence: {evidence}'
        )
    group = "\n".join(blocks) or "(empty group)"
    return (
        "Candidate group (possible duplicates of one topic):\n"
        f"{group}\n\n"
        "Return the JSON merge decision now."
    )


INTERVIEW_STREAM_SYSTEM_PROMPT = (
    "You are The Archivist, a perceptive conversation partner helping the user explore their ideas "
    "and gather material for a podcast script. Respond in a warm, companion-like tone. "
    "In each turn, briefly reflect the user's point, ask one high-value follow-up question, "
    "offer 2-3 structured answer options labeled A, B, and C, recommend one of them with a rationale, "
    "and make clear the user can respond freely. Avoid sounding like a dry interrogation or a quiz. "
    "Keep everything tightly grounded in the user's context and avoid generic platitudes."
)


def build_interview_stream_instructions(*, script_exists: bool, suggested_focus: str) -> str:
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
    missing = ", ".join(missing_dimensions) or "(none)"
    transcript_block = transcript_text.strip() or (
        "(No messages yet — produce a short opening question for the guest.)"
    )
    instructions = build_interview_stream_instructions(
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


MEMORY_EXTRACTION_SYSTEM_PROMPT = (
    "You extract reusable long-term memory about the USER from their own words, for a "
    "local-first podcast tool. You return STRICT JSON only — no prose, no markdown fences.\n\n"
    "Only the user's own turns may become memory. Never treat assistant text, scripts, or "
    "summaries as facts. Capture only knowledge that is reusable across future episodes: "
    "stable background, identity, long-term goals (profile); important reusable experiences "
    "or stories (experience); stable opinions or value judgments (viewpoint); tone, structure, "
    "and expression preferences (preference).\n\n"
    "Do NOT capture: one-off task requests for the current episode, momentary moods, idle "
    "hypotheticals, or your own guesses about the user.\n\n"
    "NEVER store high-sensitivity secrets, even if asked: passwords, API keys, tokens, private "
    "keys, bank/payment credentials, full ID/passport numbers, or precise home addresses. Omit "
    "such candidates entirely. Private-but-not-secret background (health, relationships, family) "
    "may be captured ONLY when the user explicitly asks to remember it; mark those sensitive=true.\n\n"
    "Output schema:\n"
    '{"candidates": [{"type": "profile|experience|viewpoint|preference", "name": "short label", '
    '"description": "one-line summary for retrieval", "body": "the memory in the user\'s own '
    'language and meaning", "keywords": ["zh and en synonyms"], "sensitive": false, '
    '"evidence": [{"turn_id": "<id from input>", "quote": "shortest verbatim substring from that '
    'user turn"}], "merge_target_id": "<existing id to merge into, or empty>"}]}\n\n'
    "Rules: at most 3 candidates; one topic unit per candidate; every candidate cites at least one "
    "evidence item whose turn_id is in the input and whose quote is an EXACT substring of that "
    "user turn; prefer merge_target_id when an existing candidate covers the same topic. If nothing "
    'qualifies, return {"candidates": []}.'
)


def build_memory_extraction_user_content(
    *,
    topic: str,
    creation_intent: str,
    user_turns: list[dict[str, str]],
    existing_candidates: list[dict[str, str]],
    explicit_intent: str = "",
) -> str:
    turn_lines = "\n".join(
        f'- turn_id: {turn.get("turn_id", "")}\n  content: {turn.get("content", "").strip()}'
        for turn in user_turns
    ) or "(no user turns)"
    existing_lines = "\n".join(
        f'- id: {cand.get("id", "")} | type: {cand.get("type", "")} | name: {cand.get("name", "")} '
        f'| description: {cand.get("description", "")}'
        for cand in existing_candidates
    ) or "(none)"
    explicit_block = (
        f"\nThe user explicitly asked to remember this; prioritize capturing it:\n{explicit_intent.strip()}\n"
        if explicit_intent.strip()
        else ""
    )
    return (
        f"Session topic: {topic}\n"
        f"Creation intent: {creation_intent}\n\n"
        f"Existing memory candidates (prefer merging):\n{existing_lines}\n\n"
        f"User turns to analyze (only these may be evidence):\n{turn_lines}\n"
        f"{explicit_block}\n"
        "Return the JSON object now."
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
    session: SessionRecord,
    transcript: TranscriptRecord,
    readiness: ReadinessReport,
) -> InterviewPromptInput:
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
    focus = prompt_input.suggested_focus

    # Build Reflection
    reflection = ""
    if last_user_turn:
        if is_zh:
            reflection = f"关于你提到的“{last_user_turn}”，我理解了。接下来我们重点讨论一下你的{focus}。"
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
                f"{reflection}\n你想把‘{prompt_input.topic}’做成播客。关于这个话题，现在是什么事情或者什么契机让你想聊它？\n\n"
                "A. 描述触发这个想法的精确时刻或事件。\n"
                "B. 讨论这个话题背后的背景环境或情况。\n"
                "C. 解释为什么这个话题在今天对你来说很紧迫或相关。\n\n"
                "推荐从 A 开始，因为一个具体的触发时刻能构成一个很好的开场钩子。当然，如果你想忽略这些选项，直接按照你的方式回答也可以。"
            )
        else:
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
        else:
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
        else:
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
        else:
            return (
                f"{reflection}\nIf listeners remember one takeaway or conclusion from this episode, what should it be?\n\n"
                "A. Provide a single, actionable piece of advice or key lesson.\n"
                "B. Formulate a final philosophical takeaway or summary statement.\n"
                "C. Issue a call-to-action or open-ended question for listeners to ponder.\n\n"
                "I recommend starting with A to give listeners immediate value. "
                "But feel free to ignore these options and answer in your own way."
            )

    if is_zh:
        return (
            "我已经收集了足够的素材来起草这一期节目。如果你愿意，我们可以结束采访并开始生成脚本。\n\n"
            "A. 现在生成播客脚本草稿（推荐）\n"
            "B. 先添加另一个具体细节或故事\n"
            "C. 先调整这一期的核心角度"
        )
    else:
        return (
            "I have enough material to draft the episode. If you want, we can stop "
            "the interview and move to script generation.\n\n"
            "A. Generate the podcast script draft now (Recommended)\n"
            "B. Add another concrete detail or story first\n"
            "C. Adjust the core angle of this episode"
        )
