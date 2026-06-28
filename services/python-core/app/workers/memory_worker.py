from __future__ import annotations

import threading
import time
from typing import Callable

from app.domain.memory import (
    PendingJob,
    PendingJobKind,
    WorkerState,
    WorkerStatus,
)
from app.domain.common import utc_now_iso
from app.orchestration.memory_extraction import MemoryExtractor
from app.storage.memory_file_store import MemoryFileStore

_MAX_RETRIES = 5
_BASE_BACKOFF_SECONDS = 2.0
_MAX_BACKOFF_SECONDS = 60.0


class MemoryWorker:
    """Single daemon thread that drains persistent `pending/*.json` jobs.

    Jobs survive restarts because they live on disk; the worker re-reads them on
    boot. It never blocks app shutdown on an in-flight LLM call — `stop()` only
    signals and joins briefly. Failures are retried with bounded backoff and the
    last error is surfaced into state.json for the UI.
    """

    def __init__(
        self,
        memory_store: MemoryFileStore,
        extractor: MemoryExtractor,
        *,
        maintenance=None,
        delete_source=None,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        self.memory_store = memory_store
        self.extractor = extractor
        self.maintenance = maintenance
        self._delete_source = delete_source
        self.poll_interval_seconds = poll_interval_seconds
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="memory-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)

    def notify(self) -> None:
        """Wake the worker promptly after a new job is enqueued."""
        self._wake_event.set()

    # ------------------------------------------------------------------- loop
    def _run_loop(self) -> None:
        # §17.2: check maintenance gating at runtime start.
        self._maybe_schedule_maintenance()
        while not self._stop_event.is_set():
            job = self.memory_store.claim_next()
            if job is None:
                # §17.2: idle is a maintenance check point.
                self._maybe_schedule_maintenance()
                if self.memory_store.claim_next() is not None:
                    continue
                self._set_worker_status(WorkerStatus.IDLE)
                self._wake_event.wait(timeout=self.poll_interval_seconds)
                self._wake_event.clear()
                continue
            if job.retry_count:
                # Bounded exponential backoff for repeatedly-failing jobs.
                delay = min(_BASE_BACKOFF_SECONDS * (2 ** (job.retry_count - 1)), _MAX_BACKOFF_SECONDS)
                if self._stop_event.wait(timeout=delay):
                    break
            self._process(job)

    def _maybe_schedule_maintenance(self) -> None:
        if self.maintenance is None:
            return
        try:
            if self._has_pending_kind(PendingJobKind.MAINTAIN_MEMORIES):
                return
            if self.maintenance.should_run():
                self.memory_store.enqueue(PendingJob(kind=PendingJobKind.MAINTAIN_MEMORIES))
        except Exception:
            # Scheduling must never crash the loop.
            pass

    def _has_pending_kind(self, kind: PendingJobKind) -> bool:
        return any(job.kind == kind for job in self.memory_store.list_pending())

    def _process(self, job: PendingJob) -> None:
        self._set_worker_status(WorkerStatus.RUNNING)
        try:
            self._dispatch(job)
            self.memory_store.complete(job.job_id)
            self._set_worker_status(WorkerStatus.IDLE)
        except Exception as exc:  # noqa: BLE001 - background isolation
            error = f"{type(exc).__name__}: {exc}"
            if job.retry_count + 1 >= _MAX_RETRIES:
                # Give up on this job so it stops blocking the queue, but keep
                # the error visible for the Memory page.
                self.memory_store.complete(job.job_id)
                self._set_worker_status(WorkerStatus.ERROR, error=f"dropped after retries: {error}")
            else:
                self.memory_store.fail(job.job_id, error)
                self._set_worker_status(WorkerStatus.ERROR, error=error)

    def _dispatch(self, job: PendingJob) -> None:
        if job.kind == PendingJobKind.EXTRACT_TURNS:
            self.extractor.extract_turns(
                job.session_id, from_turn_id=job.from_turn_id, to_turn_id=job.to_turn_id
            )
        elif job.kind == PendingJobKind.NORMALIZE_EXPLICIT_MEMORY:
            self.extractor.normalize_explicit(
                job.session_id, source_turn_id=job.source_turn_id, raw_intent=job.raw_intent
            )
        elif job.kind == PendingJobKind.REBUILD_INDEXES:
            self.memory_store.rebuild_indexes()
        elif job.kind == PendingJobKind.MAINTAIN_MEMORIES:
            if self.maintenance is not None:
                more = self.maintenance.run_batch()
                # §17.4: keep consolidating in further batches while work remains.
                if more and not self._has_pending_kind(PendingJobKind.MAINTAIN_MEMORIES):
                    self.memory_store.enqueue(PendingJob(kind=PendingJobKind.MAINTAIN_MEMORIES))
                # Drain aged-out superseded entries alongside maintenance (§15.3).
                if not self._has_pending_kind(PendingJobKind.PURGE_SUPERSEDED):
                    self.memory_store.enqueue(PendingJob(kind=PendingJobKind.PURGE_SUPERSEDED))
        elif job.kind == PendingJobKind.PURGE_SUPERSEDED:
            self.memory_store.purge_superseded()
        elif job.kind == PendingJobKind.DELETE_SOURCE:
            if self._delete_source is not None:
                self._delete_source(job.session_id)
        else:  # pragma: no cover - defensive
            raise ValueError(f"Unknown job kind '{job.kind}'.")

    def _set_worker_status(self, status: WorkerStatus, *, error: str = "") -> None:
        self.memory_store.save_worker_state(
            WorkerState(status=status, last_error=error, updated_at=utc_now_iso())
        )
