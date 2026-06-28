"""Script generation prompt constants (Phase 2 placeholder).

These are migrated verbatim from the legacy prompts.py so imports keep working.
Phase 2 will replace these with PromptPlan-based assembly (EpisodeBrief +
ScriptStyleProfile + selective transcript).
"""

from __future__ import annotations

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
