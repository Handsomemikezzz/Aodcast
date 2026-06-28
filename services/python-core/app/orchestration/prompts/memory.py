"""Memory-related prompt constants (Phase 3 placeholder).

These are migrated verbatim from the legacy prompts.py so imports keep working.
Phase 3 will replace these with PromptPlan-based thin profiles for
memory_extraction / memory_rerank / memory_merge / memory_action_classifier.
"""

from __future__ import annotations

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


# ---------------------------------------------------------------------------
# §10.5 Memory action classification prompt
# ---------------------------------------------------------------------------

_MEMORY_ACTION_SYSTEM = (
    "You classify a single user message to detect explicit memory-management intent.\n"
    "Return a JSON object with exactly two string fields: 'action' and 'subject'.\n\n"
    "'action' must be one of:\n"
    "  - 'remember'         : user explicitly asks to save or remember something\n"
    "  - 'correct'          : user is correcting or updating a previously stated fact\n"
    "  - 'forget_candidates': user asks to forget or delete a past memory\n"
    "  - 'none'             : no clear memory-management intent\n\n"
    "'subject' is a short phrase (≤ 8 words) naming the topic the user mentioned, "
    "or an empty string when action is 'none'.\n\n"
    "Rules:\n"
    "- Only classify as 'remember'/'correct'/'forget_candidates' when the user's intent "
    "is explicit and unambiguous. Prefer 'none' when uncertain.\n"
    "- Never infer deletion intent from a casual correction of an AI mistake.\n"
    "- Return ONLY the JSON object, no explanation, no markdown fences."
)


def build_memory_action_classification_prompt(
    user_message: str, candidate_names: list[str]
) -> str:
    """Build the user-turn text for the §10.5 memory action classifier."""
    candidate_block = ""
    if candidate_names:
        names_fmt = "\n".join(f"  - {n}" for n in candidate_names[:20])
        candidate_block = f"\nExisting memory topics for reference:\n{names_fmt}\n"
    return (
        f"User message:\n{user_message.strip()}\n"
        f"{candidate_block}\n"
        "Classify the user's memory-management intent."
    )
