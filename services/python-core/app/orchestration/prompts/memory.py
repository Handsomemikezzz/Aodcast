"""Memory prompt profiles (Phase 3).

PromptPlan thin profiles for the memory LLM calls:

- ``memory_extraction``       (§8.1)
- ``memory_rerank``           (§8.2)
- ``memory_merge``            (§8.3)

Design principles per §8 and §3 (Non-goals):
- Each profile is thin — a small stable system section + dynamic user payload.
- JSON tasks keep strict JSON output contracts (never prose, no markdown fences).
- Sensitive memory bodies never enter the rerank index (§8.2).
- No script/interview sections leak into memory profiles.
"""

from __future__ import annotations

from app.orchestration.prompts.registry import (
    PROMPT_VERSION,
    CachePolicy,
    PromptPlan,
    PromptSection,
    assemble_plan,
)


# ---------------------------------------------------------------------------
# Stable system sections — one per memory operation profile
# ---------------------------------------------------------------------------

_SECTION_EXTRACTION_SYSTEM = PromptSection(
    section_id="mem_extraction.system",
    content=(
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
    ),
    cache_policy=CachePolicy.STABLE,
    required=True,
)

_SECTION_RERANK_SYSTEM = PromptSection(
    section_id="mem_rerank.system",
    content=(
        "You select which long-term memories are most useful for writing the current "
        "podcast script. You return STRICT JSON only: {\"selected_ids\": [\"id1\", ...]}. "
        "Pick at most the requested number, ordered by relevance to the topic and intent. "
        "Only choose from the provided candidate ids. If none are relevant, return "
        "{\"selected_ids\": []}. Do not invent ids and do not add commentary."
    ),
    cache_policy=CachePolicy.STABLE,
    required=True,
)

_SECTION_MERGE_SYSTEM = PromptSection(
    section_id="mem_merge.system",
    content=(
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
        "If the entries are not\u771f\u6b63\u91cd\u590d (not truly the same topic), return "
        '{"primary_id": "", "drop_ids": []}. primary_id and every drop_id must be ids '
        "from the group. Do not merge unrelated memories just to reduce count."
    ),
    cache_policy=CachePolicy.STABLE,
    required=True,
)

# ---------------------------------------------------------------------------
# PromptPlan builders for each memory operation profile
# ---------------------------------------------------------------------------

def build_memory_extraction_plan(
    *,
    topic: str,
    creation_intent: str,
    user_turns: list[dict[str, str]],
    existing_candidates: list[dict[str, str]],
    explicit_intent: str = "",
) -> PromptPlan:
    """Build the memory_extraction PromptPlan (§8.1).

    Dynamic sections: topic/intent, user turn batch, existing candidates,
    optional explicit remember/correction intent.
    Sensitive bodies are NEVER included in any section.
    """
    user_content = _memory_extraction_payload(
        topic=topic,
        creation_intent=creation_intent,
        user_turns=user_turns,
        existing_candidates=existing_candidates,
        explicit_intent=explicit_intent,
    )
    return assemble_plan(
        operation_profile="memory_extraction",
        prompt_version=PROMPT_VERSION,
        system_sections=[_SECTION_EXTRACTION_SYSTEM],
        user_sections=[
            PromptSection(
                section_id="mem_extraction.payload",
                content=user_content,
                cache_policy=CachePolicy.PRIVATE_DYNAMIC,
            )
        ],
        gates={
            "has_explicit_intent": bool(explicit_intent.strip()),
            "user_turn_count": len(user_turns),
            "existing_candidate_count": len(existing_candidates),
        },
    )


def build_memory_rerank_plan(
    *,
    topic: str,
    creation_intent: str,
    candidates: list[dict[str, str]],
    max_select: int,
) -> PromptPlan:
    """Build the memory_rerank PromptPlan (§8.2).

    Thin profile: candidate index uses id/type/name/description only —
    sensitive bodies NEVER enter the rerank index.
    """
    user_content = _memory_rerank_payload(
        topic=topic,
        creation_intent=creation_intent,
        candidates=candidates,
        max_select=max_select,
    )
    return assemble_plan(
        operation_profile="memory_rerank",
        prompt_version=PROMPT_VERSION,
        system_sections=[_SECTION_RERANK_SYSTEM],
        user_sections=[
            PromptSection(
                section_id="mem_rerank.payload",
                content=user_content,
                cache_policy=CachePolicy.DYNAMIC,
            )
        ],
        gates={
            "candidate_count": len(candidates),
            "max_select": max_select,
        },
    )


def build_memory_merge_plan(*, entries: list[dict]) -> PromptPlan:
    """Build the memory_merge PromptPlan (§8.3).

    Thin profile: merge only true semantic duplicates using existing evidence only.
    """
    user_content = _memory_maintenance_payload(entries=entries)
    return assemble_plan(
        operation_profile="memory_merge",
        prompt_version=PROMPT_VERSION,
        system_sections=[_SECTION_MERGE_SYSTEM],
        user_sections=[
            PromptSection(
                section_id="mem_merge.payload",
                content=user_content,
                cache_policy=CachePolicy.PRIVATE_DYNAMIC,
            )
        ],
        gates={"entry_count": len(entries)},
    )


def _memory_rerank_payload(
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


def _memory_maintenance_payload(*, entries: list[dict]) -> str:
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


def _memory_extraction_payload(
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
