from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from app.domain.provider_config import LLMProviderConfig
from app.domain.memory import PendingJob, PendingJobKind, WorkerStatus
from app.domain.session import SessionRecord
from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.memory_extraction import MemoryExtractor
from app.storage.config_store import ConfigStore
from app.storage.memory_file_store import MemoryFileStore
from app.storage.project_store import ProjectStore
from app.workers.memory_worker import MemoryWorker


class MemoryWorkerTests(unittest.TestCase):
    def _setup(self, tmp: str):
        data = Path(tmp)
        ps = ProjectStore(data)
        ps.bootstrap()
        cs = ConfigStore(data)
        cs.bootstrap()
        cs.save_llm_config(LLMProviderConfig(provider="mock", model="m", base_url="", api_key=""))
        store = MemoryFileStore(data)
        store.bootstrap()
        extractor = MemoryExtractor(ps, cs, store)
        return ps, cs, store, extractor

    def _wait_until(self, predicate, timeout=5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.05)
        return predicate()

    def test_worker_processes_enqueued_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, cs, store, extractor = self._setup(tmp)
            session = SessionRecord(topic="职场成长", creation_intent="分享")
            transcript = TranscriptRecord(session_id=session.session_id)
            transcript.append(Speaker.USER, "我喜欢从一个具体经历讲起。")
            ps.save_session(session)
            ps.save_transcript(transcript)

            store.enqueue(
                PendingJob(
                    kind=PendingJobKind.EXTRACT_TURNS,
                    session_id=session.session_id,
                    to_turn_id=transcript.turns[-1].turn_id,
                )
            )
            worker = MemoryWorker(store, extractor, poll_interval_seconds=0.1)
            worker.start()
            try:
                ok = self._wait_until(lambda: len(store.list_entries()) >= 1)
            finally:
                worker.stop()
            self.assertTrue(ok, "worker did not produce a memory entry")
            self.assertIsNone(store.claim_next(), "pending job should be drained")

    def test_pending_jobs_survive_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, cs, store, extractor = self._setup(tmp)
            session = SessionRecord(topic="主题", creation_intent="意图")
            transcript = TranscriptRecord(session_id=session.session_id)
            transcript.append(Speaker.USER, "我喜欢具体案例。")
            ps.save_session(session)
            ps.save_transcript(transcript)
            store.enqueue(
                PendingJob(
                    kind=PendingJobKind.EXTRACT_TURNS,
                    session_id=session.session_id,
                    to_turn_id=transcript.turns[-1].turn_id,
                )
            )
            # Simulate restart: a brand-new store instance sees the job on disk.
            restarted = MemoryFileStore(Path(tmp))
            restarted.bootstrap()
            self.assertIsNotNone(restarted.claim_next())

            worker = MemoryWorker(restarted, MemoryExtractor(ps, cs, restarted), poll_interval_seconds=0.1)
            worker.start()
            try:
                ok = self._wait_until(lambda: restarted.claim_next() is None)
            finally:
                worker.stop()
            self.assertTrue(ok)

    def test_unknown_session_failure_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, cs, store, extractor = self._setup(tmp)
            store.enqueue(
                PendingJob(
                    kind=PendingJobKind.EXTRACT_TURNS,
                    session_id="does-not-exist",
                    to_turn_id="turn_x",
                )
            )
            worker = MemoryWorker(store, extractor, poll_interval_seconds=0.1)
            worker.start()
            try:
                # The job fails and is retried; the worker surfaces an error but
                # keeps running rather than crashing.
                ok = self._wait_until(
                    lambda: store.load_state().worker.status == WorkerStatus.ERROR
                )
            finally:
                worker.stop()
            self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
