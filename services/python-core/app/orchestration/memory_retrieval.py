from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.memory import MemoryEntry, MemoryOrigin, RetrievedMemoryContext
from app.storage.memory_file_store import MemoryFileStore

# Interview-stage budget per the design: at most 3 entries, ~800 tokens.
_MAX_ITEMS = 3
_CHAR_BUDGET = 2400

_MEMORY_HEADER = (
    "[Long-term memory — background only. The current conversation always takes "
    "priority; do not treat these as the user re-confirming them now. When you "
    "state a specific past fact, say \"you mentioned before\".]"
)

_SENSITIVE_PLACEHOLDER = "存在相关敏感背景（未授权，未展开内容）"


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    topic: str = ""
    creation_intent: str = ""
    recent_user_message: str = ""
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
