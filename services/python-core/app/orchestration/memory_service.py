from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.common import utc_now_iso
from app.domain.memory import (
    MemoryEntry,
    MemoryState,
    PendingJob,
    PendingJobKind,
    WorkerStatus,
)
from app.domain.session import SessionRecord
from app.domain.transcript import Speaker
from app.orchestration.memory_extraction import MemoryExtractor
from app.orchestration.memory_retrieval import MemoryRetrieval, RetrievalQuery
from app.orchestration.sensitive import detect_forbidden
from app.storage.config_store import ConfigStore
from app.storage.memory_file_store import MemoryFileStore
from app.storage.project_store import ProjectStore
from app.workers.memory_worker import MemoryWorker

# After this many unprocessed user turns, schedule a background extraction.
_AUTO_EXTRACT_THRESHOLD = 3


@dataclass(frozen=True, slots=True)
class MemoryOverview:
    state: MemoryState
    entry_count: int
    pending_job_count: int


class ExplicitMemoryRejected(ValueError):
    """Raised when an explicit 'remember' request is blocked (e.g. secrets)."""


class MemoryService:
    """Facade over the file store, extraction, retrieval, and background worker.

    The main interview/script flow only ever calls read-only retrieval and
    fire-and-forget enqueue methods here; all LLM work happens on the worker.
    """

    def __init__(self, data_dir: Path, project_store: ProjectStore, config_store: ConfigStore) -> None:
        self.data_dir = data_dir
        self.project_store = project_store
        self.config_store = config_store
        self.store = MemoryFileStore(data_dir)
        self.extractor = MemoryExtractor(project_store, config_store, self.store)
        self.retrieval = MemoryRetrieval(self.store)
        self.worker = MemoryWorker(self.store, self.extractor)

    # --------------------------------------------------------------- lifecycle
    def bootstrap(self) -> None:
        self.store.bootstrap()
        self._delete_legacy_sqlite()
        self.worker.start()

    def shutdown(self) -> None:
        self.worker.stop()

    def _delete_legacy_sqlite(self) -> None:
        legacy = self.data_dir / "memory" / "memory.sqlite"
        try:
            legacy.unlink(missing_ok=True)
        except OSError:
            pass

    # ----------------------------------------------------------------- settings
    def get_overview(self) -> MemoryOverview:
        state = self.store.load_state()
        return MemoryOverview(
            state=state,
            entry_count=len(self.store.list_entries()),
            pending_job_count=len(self.store.list_pending()),
        )

    def acknowledge_first_run(self) -> MemoryState:
        state = self.store.load_state()
        state.settings.first_run_acknowledged = True
        state.settings.writing_enabled = True
        state.settings.usage_enabled = True
        self.store.save_settings(state.settings)
        return state

    def update_settings(
        self, *, writing_enabled: bool | None = None, usage_enabled: bool | None = None
    ) -> MemoryState:
        state = self.store.load_state()
        if writing_enabled is not None:
            state.settings.writing_enabled = writing_enabled
            if not writing_enabled:
                # Disabling writing cancels not-yet-run extraction jobs immediately.
                self.store.cancel_jobs(
                    kinds={
                        PendingJobKind.EXTRACT_TURNS.value,
                        PendingJobKind.NORMALIZE_EXPLICIT_MEMORY.value,
                    }
                )
        if usage_enabled is not None:
            state.settings.usage_enabled = usage_enabled
        self.store.save_settings(state.settings)
        return state

    # -------------------------------------------------------------------- reads
    def list_memories(self, *, search: str | None = None, type: str | None = None) -> list[MemoryEntry]:
        from app.domain.memory import MemoryType

        mem_type = MemoryType(type) if type else None
        return self.store.list_entries(type=mem_type, search=search)

    def get_memory(self, memory_id: str) -> MemoryEntry | None:
        return self.store.get_entry(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        deleted = self.store.delete_entry(memory_id)
        if deleted:
            self._purge_authorizations(memory_id)
        return deleted

    def clear_all(self) -> None:
        self.store.clear_all()
        self._purge_authorizations(None)

    # -------------------------------------------------------------------- writes
    def enqueue_extraction(self, session: SessionRecord) -> None:
        """Schedule background extraction if writing is on and enough new turns exist."""
        if not self._writing_active(session):
            return
        transcript = self.project_store.load_transcript(session.session_id)
        user_turns = [t for t in transcript.turns if t.speaker == Speaker.USER]
        if not user_turns:
            return
        cursor = session.memory_processed_through_turn_id
        unprocessed = self._user_turns_after(user_turns, cursor)
        if len(unprocessed) < _AUTO_EXTRACT_THRESHOLD:
            return
        self.store.enqueue(
            PendingJob(
                kind=PendingJobKind.EXTRACT_TURNS,
                session_id=session.session_id,
                from_turn_id=cursor,
                to_turn_id=user_turns[-1].turn_id,
            )
        )
        self.worker.notify()

    def enqueue_extraction_now(self, session: SessionRecord) -> None:
        """Force-schedule extraction of all unprocessed turns (script gen / leave)."""
        if not self._writing_active(session):
            return
        transcript = self.project_store.load_transcript(session.session_id)
        user_turns = [t for t in transcript.turns if t.speaker == Speaker.USER]
        if not user_turns:
            return
        self.store.enqueue(
            PendingJob(
                kind=PendingJobKind.EXTRACT_TURNS,
                session_id=session.session_id,
                from_turn_id=session.memory_processed_through_turn_id,
                to_turn_id=user_turns[-1].turn_id,
            )
        )
        self.worker.notify()

    def remember_explicit(self, session_id: str, *, source_turn_id: str, raw_intent: str) -> None:
        """Synchronously persist an explicit 'remember' intent as a pending job.

        Hard-blocked secrets are rejected up front so they never reach disk.
        The pending job is durable, so the intent survives an immediate restart.
        """
        forbidden = detect_forbidden(raw_intent)
        if forbidden:
            raise ExplicitMemoryRejected(
                "无法保存包含敏感秘密的信息（如密码、密钥、支付凭据、证件号或精确住址）。"
            )
        state = self.store.load_state()
        if not state.settings.writing_enabled:
            raise ExplicitMemoryRejected("记忆记录当前已关闭。")
        self.store.enqueue(
            PendingJob(
                kind=PendingJobKind.NORMALIZE_EXPLICIT_MEMORY,
                session_id=session_id,
                source_turn_id=source_turn_id,
                raw_intent=raw_intent,
            )
        )
        self.worker.notify()

    # ----------------------------------------------------------------- retrieval
    def build_interview_context(self, session: SessionRecord, *, recent_user_message: str = ""):
        from app.domain.memory import RetrievedMemoryContext

        state = self.store.load_state()
        if not state.settings.usage_enabled or not session.memory_enabled():
            return RetrievedMemoryContext.empty()
        return self.retrieval.build_interview_context(
            RetrievalQuery(
                topic=session.topic,
                creation_intent=session.creation_intent,
                recent_user_message=recent_user_message,
                authorized_memory_ids=tuple(session.authorized_memory_ids),
            )
        )

    # ------------------------------------------------------------------ helpers
    def _writing_active(self, session: SessionRecord) -> bool:
        if not session.memory_enabled():
            return False
        return self.store.load_state().settings.writing_enabled

    @staticmethod
    def _user_turns_after(user_turns, cursor: str):
        if not cursor:
            return list(user_turns)
        seen = False
        after = []
        for turn in user_turns:
            if seen:
                after.append(turn)
            if turn.turn_id == cursor:
                seen = True
        # If the cursor turn wasn't found, treat everything as unprocessed.
        return after if seen else list(user_turns)

    def _purge_authorizations(self, memory_id: str | None) -> None:
        for session in self.project_store.list_sessions(include_deleted=True):
            if memory_id is None:
                changed = bool(session.authorized_memory_ids or session.memory_usage_events)
                session.authorized_memory_ids = []
                session.memory_usage_events = []
            elif memory_id in session.authorized_memory_ids:
                session.authorized_memory_ids = [
                    mid for mid in session.authorized_memory_ids if mid != memory_id
                ]
                changed = True
            else:
                changed = False
            if changed:
                self.project_store.save_session(session)
