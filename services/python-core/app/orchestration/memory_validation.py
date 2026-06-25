from __future__ import annotations

from dataclasses import dataclass

from app.domain.common import utc_now_iso
from app.domain.memory import (
    MemoryEntry,
    MemoryEvidence,
    MemoryOrigin,
    MemoryType,
)
from app.orchestration.sensitive import contains_forbidden
from app.storage.memory_file_store import MemoryFileStore

MAX_CANDIDATES_PER_BATCH = 3
MAX_NAME = 80
MAX_DESCRIPTION = 200
MAX_BODY = 2000
MAX_KEYWORDS = 12
MAX_KEYWORD_LEN = 40
MAX_QUOTE = 400
MAX_EVIDENCE = 3


class MemoryValidationError(ValueError):
    """Raised when a model extraction batch violates the deterministic rules.

    Validation is all-or-nothing: a single bad candidate rejects the batch so
    untrusted partial results are never written.
    """


@dataclass(frozen=True, slots=True)
class ValidationContext:
    session_id: str
    # turn_id -> verbatim user-turn content (only user turns belong here)
    batch_turns: dict[str, str]
    origin: MemoryOrigin


def validate_candidates(
    candidates: list[dict],
    context: ValidationContext,
    store: MemoryFileStore,
) -> list[MemoryEntry]:
    if len(candidates) > MAX_CANDIDATES_PER_BATCH:
        raise MemoryValidationError(
            f"Batch proposes {len(candidates)} candidates; max is {MAX_CANDIDATES_PER_BATCH}."
        )

    valid_types = {t.value for t in MemoryType}
    entries: list[MemoryEntry] = []

    for candidate in candidates:
        mem_type = candidate.get("type")
        if mem_type not in valid_types:
            raise MemoryValidationError(f"Invalid memory type '{mem_type}'.")

        name = _require_str(candidate.get("name"), "name", MAX_NAME)
        description = _require_str(candidate.get("description"), "description", MAX_DESCRIPTION)
        body = _require_str(candidate.get("body"), "body", MAX_BODY)

        keywords = candidate.get("keywords") or []
        if not isinstance(keywords, list) or len(keywords) > MAX_KEYWORDS:
            raise MemoryValidationError("keywords must be a list of at most 12 items.")
        for kw in keywords:
            if not isinstance(kw, str) or len(kw) > MAX_KEYWORD_LEN:
                raise MemoryValidationError("keyword too long or non-string.")

        sensitive = bool(candidate.get("sensitive", False))

        raw_evidence = candidate.get("evidence") or []
        if not isinstance(raw_evidence, list) or not raw_evidence:
            raise MemoryValidationError("Each candidate must cite at least one evidence item.")
        if len(raw_evidence) > MAX_EVIDENCE:
            raise MemoryValidationError("Too many evidence items.")

        evidence: list[MemoryEvidence] = []
        evidence_turn_ids: list[str] = []
        for item in raw_evidence:
            if not isinstance(item, dict):
                raise MemoryValidationError("Evidence item must be an object.")
            turn_id = item.get("turn_id", "")
            quote = item.get("quote", "")
            if turn_id not in context.batch_turns:
                raise MemoryValidationError(
                    f"Evidence turn_id '{turn_id}' is not in the current user-turn batch."
                )
            if not isinstance(quote, str) or not quote.strip() or len(quote) > MAX_QUOTE:
                raise MemoryValidationError("Evidence quote missing or too long.")
            if quote not in context.batch_turns[turn_id]:
                raise MemoryValidationError(
                    "Evidence quote is not a verbatim substring of the cited user turn."
                )
            evidence.append(
                MemoryEvidence(
                    session_id=context.session_id,
                    turn_id=turn_id,
                    quote=quote,
                    observed_at=utc_now_iso(),
                )
            )
            evidence_turn_ids.append(turn_id)

        # Hard sensitive gate: never persist forbidden secrets even if the model returns them.
        if contains_forbidden(" ".join([name, description, body])):
            raise MemoryValidationError("Candidate contains forbidden sensitive content.")

        # Forget fingerprint gate: deleted memories must not regenerate from the same evidence.
        from app.storage.memory_file_store import content_fingerprint

        if store.has_forget_fingerprint(
            content_hash=content_fingerprint(body), turn_ids=evidence_turn_ids
        ):
            raise MemoryValidationError("Candidate matches an existing forget fingerprint.")

        entries.append(
            MemoryEntry(
                name=name,
                description=description,
                type=MemoryType(mem_type),
                body=body,
                origin=context.origin,
                sensitive=sensitive,
                keywords=[kw for kw in keywords if kw.strip()],
                evidence=evidence,
            )
        )

    return entries


def _require_str(value: object, field: str, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryValidationError(f"Field '{field}' is required.")
    if len(value) > max_len:
        raise MemoryValidationError(f"Field '{field}' exceeds {max_len} chars.")
    return value.strip()
