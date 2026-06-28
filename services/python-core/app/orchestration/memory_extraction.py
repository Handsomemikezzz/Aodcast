from __future__ import annotations

from app.domain.memory import MemoryEntry, MemoryOrigin, MemoryEvidence
from app.domain.transcript import Speaker, TranscriptRecord
from app.providers.llm.base import MemoryExtractionRequest
from app.providers.llm.factory import build_llm_provider
from app.orchestration.memory_validation import (
    ValidationContext,
    validate_candidates,
)
from app.storage.config_store import ConfigStore
from app.storage.memory_file_store import MemoryFileStore
from app.storage.project_store import ProjectStore

_MAX_EXISTING_HINTS = 20


class MemoryExtractor:
    def __init__(
        self,
        project_store: ProjectStore,
        config_store: ConfigStore,
        memory_store: MemoryFileStore,
    ) -> None:
        self.project_store = project_store
        self.config_store = config_store
        self.memory_store = memory_store

    def extract_turns(
        self, session_id: str, *, from_turn_id: str = "", to_turn_id: str = ""
    ) -> list[MemoryEntry]:
        """Extract memory from the user turns in (from_turn_id, to_turn_id].

        Advances the session memory cursor to to_turn_id only on success.
        Returns the entries written (possibly empty).
        """
        transcript = self.project_store.load_transcript(session_id)
        batch = self._user_turns_in_range(transcript, from_turn_id, to_turn_id)
        cursor_target = to_turn_id or (transcript.turns[-1].turn_id if transcript.turns else "")

        if not batch:
            self._advance_cursor(session_id, cursor_target)
            return []

        session = self.project_store.load_session(session_id)
        provider = build_llm_provider(self.config_store.load_llm_config())
        request = MemoryExtractionRequest(
            session_id=session_id,
            topic=session.topic,
            creation_intent=session.creation_intent,
            user_turns=[{"turn_id": t.turn_id, "content": t.content} for t in batch],
            existing_candidates=self._existing_hints(),
        )
        response = provider.extract_memories(request)

        written = self._persist(
            response.candidates,
            ValidationContext(
                session_id=session_id,
                batch_turns={t.turn_id: t.content for t in batch},
                origin=MemoryOrigin.AUTO,
            ),
        )
        # Cursor advances only after a successful, fully-validated write.
        self._advance_cursor(session_id, cursor_target)
        return written

    def normalize_correction(
        self,
        session_id: str,
        *,
        source_turn_id: str,
        raw_intent: str,
        target_id: str = "",
    ) -> list[MemoryEntry]:
        """§10.3: Normalize a correction intent and supersede the old memory.

        Creates a new explicit memory (same path as normalize_explicit), then
        moves the target to superseded/ if a target_id is provided.  When no
        target_id is given only the new memory is written; the caller is
        responsible for surfacing ambiguous candidates to the user.
        """
        new_entries = self.normalize_explicit(
            session_id, source_turn_id=source_turn_id, raw_intent=raw_intent
        )
        if target_id:
            # Move the old entry out of active entries into the superseded pool.
            self.memory_store.move_to_superseded(target_id)
        return new_entries

    def normalize_explicit(
        self, session_id: str, *, source_turn_id: str, raw_intent: str
    ) -> list[MemoryEntry]:
        """Normalize an explicit 'remember this' intent into a stored memory."""
        transcript = self.project_store.load_transcript(session_id)
        source_turn = next(
            (t for t in transcript.turns if t.turn_id == source_turn_id and t.speaker == Speaker.USER),
            None,
        )
        if source_turn is None:
            # Fall back to the latest user turn if the explicit source is unknown.
            user_turns = [t for t in transcript.turns if t.speaker == Speaker.USER]
            if not user_turns:
                return []
            source_turn = user_turns[-1]

        session = self.project_store.load_session(session_id)
        provider = build_llm_provider(self.config_store.load_llm_config())
        request = MemoryExtractionRequest(
            session_id=session_id,
            topic=session.topic,
            creation_intent=session.creation_intent,
            user_turns=[{"turn_id": source_turn.turn_id, "content": source_turn.content}],
            existing_candidates=self._existing_hints(),
            explicit_intent=raw_intent or source_turn.content,
        )
        response = provider.extract_memories(request)
        return self._persist(
            response.candidates,
            ValidationContext(
                session_id=session_id,
                batch_turns={source_turn.turn_id: source_turn.content},
                origin=MemoryOrigin.EXPLICIT,
            ),
        )

    # ------------------------------------------------------------------ helpers
    def _persist(self, candidates: list[dict], context: ValidationContext) -> list[MemoryEntry]:
        entries = validate_candidates(candidates, context, self.memory_store)
        written: list[MemoryEntry] = []
        for candidate, entry in zip(candidates, entries):
            merge_target_id = str(candidate.get("merge_target_id") or "").strip()
            if merge_target_id:
                merged = self._merge_into(merge_target_id, entry)
                if merged is not None:
                    written.append(merged)
                    continue
            self.memory_store.save_entry(entry)
            written.append(entry)
        if written:
            # Count new/updated units toward the next maintenance gate (§9.2/§17.3).
            self.memory_store.note_change(len(written))
        return written

    def _merge_into(self, target_id: str, incoming: MemoryEntry) -> MemoryEntry | None:
        target = self.memory_store.get_entry(target_id)
        if target is None or target.type != incoming.type:
            return None
        # Merge evidence (dedupe by turn_id), cap at 3, keeping the newest.
        existing_turn_ids = {ev.turn_id for ev in target.evidence}
        for ev in incoming.evidence:
            if ev.turn_id not in existing_turn_ids:
                target.evidence.append(ev)
                existing_turn_ids.add(ev.turn_id)
        if len(target.evidence) > 3:
            target.evidence = target.evidence[-3:]
        # Merged result keeps explicit origin if either side is explicit (§10.2).
        if incoming.origin == MemoryOrigin.EXPLICIT:
            target.origin = MemoryOrigin.EXPLICIT
        # Refresh the summary fields from the newer candidate.
        target.description = incoming.description or target.description
        merged_keywords = list(dict.fromkeys([*target.keywords, *incoming.keywords]))
        target.keywords = merged_keywords[:12]
        self.memory_store.save_entry(target)
        return target

    def _existing_hints(self) -> list[dict[str, str]]:
        hints: list[dict[str, str]] = []
        for entry in self.memory_store.list_entries()[:_MAX_EXISTING_HINTS]:
            hints.append(
                {
                    "id": entry.id,
                    "type": entry.type.value,
                    "name": entry.name,
                    "description": entry.description,
                }
            )
        return hints

    def _advance_cursor(self, session_id: str, turn_id: str) -> None:
        if not turn_id:
            return
        session = self.project_store.load_session(session_id)
        session.advance_memory_cursor(turn_id)
        self.project_store.save_session(session)

    @staticmethod
    def _user_turns_in_range(
        transcript: TranscriptRecord, from_turn_id: str, to_turn_id: str
    ):
        turns = transcript.turns
        start_idx = 0
        if from_turn_id:
            for i, t in enumerate(turns):
                if t.turn_id == from_turn_id:
                    start_idx = i + 1
                    break
        end_idx = len(turns) - 1
        if to_turn_id:
            for i, t in enumerate(turns):
                if t.turn_id == to_turn_id:
                    end_idx = i
                    break
        window = turns[start_idx : end_idx + 1] if turns else []
        return [t for t in window if t.speaker == Speaker.USER]
