from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from app.domain.memory import MemoryEntry, MemoryOrigin, MemoryType, RetrievedMemoryContext
from app.storage.memory_file_store import MemoryFileStore

# Interview-stage budget per the design: at most 3 entries, ~800 tokens.
_MAX_ITEMS = 3
_CHAR_BUDGET = 2400

# Script-stage budget (§13.4): at most 5 entries, ~1600 tokens.
_SCRIPT_MAX_ITEMS = 5
_SCRIPT_CHAR_BUDGET = 4800
_SCRIPT_CANDIDATE_POOL = 12

_MEMORY_HEADER = (
    "[Long-term memory — background only. The current conversation always takes "
    "priority; do not treat these as the user re-confirming them now. When you "
    "state a specific past fact, say \"you mentioned before\".]"
)

_SCRIPT_MEMORY_HEADER = (
    "[Long-term memory about the author — use only to shape this script. The "
    "interview transcript is the primary source and always wins. Let profile, "
    "viewpoint, and preference memories shape tone, structure, reasoning, and "
    "forbidden phrasings. Treat experience memories as background material to use "
    "only as stated. Never invent new facts from memory.]"
)

_SENSITIVE_PLACEHOLDER = "存在相关敏感背景（未授权，未展开内容）"

# Type for the injected rerank step: candidate index -> selected ids.
RerankFn = Callable[[list[dict[str, str]]], list[str]]


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    topic: str = ""
    creation_intent: str = ""
    recent_user_message: str = ""
    transcript_text: str = ""
    authorized_memory_ids: tuple[str, ...] = ()


class MemoryRetrieval:
    def __init__(self, memory_store: MemoryFileStore) -> None:
        self.memory_store = memory_store

    def build_interview_context(self, query: RetrievalQuery) -> RetrievedMemoryContext:
        entries = self.memory_store.list_entries()
        if not entries:
            return RetrievedMemoryContext.empty()

        query_text = " ".join(
            [query.topic, query.creation_intent, query.recent_user_message]
        ).lower()

        scored = [(self._score(entry, query_text), entry) for entry in entries]
        scored = [(score, entry) for score, entry in scored if score > 0]
        scored.sort(key=lambda pair: (-pair[0], *self._tiebreak(pair[1])))

        lines: list[str] = []
        memory_ids: list[str] = []
        used_chars = len(_MEMORY_HEADER)
        authorized = set(query.authorized_memory_ids)

        for _score, entry in scored:
            if len(memory_ids) >= _MAX_ITEMS:
                break
            line = self._render_line(entry, authorized)
            if used_chars + len(line) > _CHAR_BUDGET:
                break
            lines.append(line)
            memory_ids.append(entry.id)
            used_chars += len(line)

        if not lines:
            return RetrievedMemoryContext.empty()

        prompt_block = "\n".join([_MEMORY_HEADER, *lines])
        return RetrievedMemoryContext(
            prompt_block=prompt_block,
            memory_ids=tuple(memory_ids),
            item_count=len(memory_ids),
        )

    def _render_line(self, entry: MemoryEntry, authorized: set[str]) -> str:
        if entry.sensitive and entry.id not in authorized:
            return f"- (sensitive {entry.type.value}) {_SENSITIVE_PLACEHOLDER}"
        return f"- ({entry.type.value}) {entry.name}: {entry.description}"

    # ----------------------------------------------------------------- script
    def build_script_context(self, query: RetrievalQuery, *, rerank: RerankFn) -> RetrievedMemoryContext:
        """Two-step script retrieval (§13.4): local eligible candidates -> LLM
        rerank (<=5). Falls back to local ordering if rerank raises."""
        authorized = set(query.authorized_memory_ids)
        query_text = self._script_query_text(query)

        eligible = [e for e in self.memory_store.list_entries() if self._script_eligible(e, query, authorized)]
        scored = [(self._score(e, query_text), e) for e in eligible]
        scored = [(s, e) for s, e in scored if s > 0 or e.origin == MemoryOrigin.EXPLICIT]
        scored.sort(key=lambda pair: (-pair[0], *self._tiebreak(pair[1])))
        pool = [entry for _s, entry in scored[:_SCRIPT_CANDIDATE_POOL]]
        if not pool:
            return RetrievedMemoryContext.empty()

        # Rerank index never carries sensitive bodies — generalized description only.
        index = [
            {
                "id": entry.id,
                "type": entry.type.value,
                "name": entry.name if not entry.sensitive else f"(sensitive {entry.type.value})",
                "description": entry.description if not entry.sensitive else _SENSITIVE_PLACEHOLDER,
            }
            for entry in pool
        ]
        by_id = {entry.id: entry for entry in pool}
        try:
            selected_ids = rerank(index)
            ordered = [by_id[mid] for mid in selected_ids if mid in by_id]
        except Exception:
            # §13.4: on rerank failure, use the local candidate ordering.
            ordered = pool[:_SCRIPT_MAX_ITEMS]

        lines: list[str] = []
        memory_ids: list[str] = []
        used_chars = len(_SCRIPT_MEMORY_HEADER)
        for entry in ordered:
            if len(memory_ids) >= _SCRIPT_MAX_ITEMS:
                break
            line = self._render_script_line(entry)
            if used_chars + len(line) > _SCRIPT_CHAR_BUDGET:
                break
            lines.append(line)
            memory_ids.append(entry.id)
            used_chars += len(line)

        if not lines:
            return RetrievedMemoryContext.empty()
        return RetrievedMemoryContext(
            prompt_block="\n".join([_SCRIPT_MEMORY_HEADER, *lines]),
            memory_ids=tuple(memory_ids),
            item_count=len(memory_ids),
        )

    def list_script_authorization_candidates(self, query: RetrievalQuery) -> list[MemoryEntry]:
        """Relevant experience/sensitive memories that are NOT yet usable in a
        script because they need current-episode authorization (§14.4)."""
        authorized = set(query.authorized_memory_ids)
        query_text = self._script_query_text(query)
        candidates: list[tuple[int, MemoryEntry]] = []
        for entry in self.memory_store.list_entries():
            if entry.id in authorized:
                continue
            needs_auth = entry.sensitive or (
                entry.type == MemoryType.EXPERIENCE and not self._re_mentioned(entry, query)
            )
            if not needs_auth:
                continue
            score = self._score(entry, query_text)
            if score > 0:
                candidates.append((score, entry))
        candidates.sort(key=lambda pair: (-pair[0], *self._tiebreak(pair[1])))
        return [entry for _s, entry in candidates[:_SCRIPT_CANDIDATE_POOL]]

    def _render_script_line(self, entry: MemoryEntry) -> str:
        # Eligibility guarantees sensitive entries here are authorized, so the
        # body is safe to include.
        body = entry.body.strip() or entry.description
        return f"- ({entry.type.value}) {entry.name}: {body}"

    def _script_eligible(self, entry: MemoryEntry, query: RetrievalQuery, authorized: set[str]) -> bool:
        if entry.sensitive:
            return entry.id in authorized
        if entry.type == MemoryType.EXPERIENCE:
            return entry.id in authorized or self._re_mentioned(entry, query)
        return True

    def _re_mentioned(self, entry: MemoryEntry, query: RetrievalQuery) -> bool:
        transcript = query.transcript_text.lower()
        if not transcript:
            return False
        terms = [kw.lower() for kw in entry.keywords] + _tokenize(entry.name)
        return any(term and term in transcript for term in terms)

    def _script_query_text(self, query: RetrievalQuery) -> str:
        return " ".join([query.topic, query.creation_intent, query.transcript_text]).lower()


    def _score(self, entry: MemoryEntry, query_text: str) -> int:
        # Explicit memories carry a stable base so durable preferences surface
        # even when topic keywords don't overlap.
        score = 1 if entry.origin == MemoryOrigin.EXPLICIT else 0
        for keyword in entry.keywords:
            token = keyword.lower().strip()
            if token and token in query_text:
                score += 2
        for token in _tokenize(f"{entry.name} {entry.description}"):
            if token in query_text:
                score += 1
        return score

    def _tiebreak(self, entry: MemoryEntry) -> tuple:
        return (
            0 if entry.origin == MemoryOrigin.EXPLICIT else 1,
            _reverse_str(entry.last_used_at or ""),
            -entry.source_count,
            _reverse_str(entry.updated_at or ""),
        )


def _tokenize(text: str) -> list[str]:
    # Latin words plus CJK bigrams give cheap zh/en recall without a tokenizer.
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9]{2,}", lowered)
    cjk_runs = re.findall(r"[㐀-鿿]{2,}", lowered)
    bigrams: list[str] = []
    for run in cjk_runs:
        bigrams.extend(run[i : i + 2] for i in range(len(run) - 1))
        bigrams.append(run)
    return [*latin, *bigrams]


def _reverse_str(value: str) -> str:
    return "".join(chr(0x10FFFF - ord(ch)) for ch in value)
