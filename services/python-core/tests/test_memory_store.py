from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.domain.memory import (
    MemoryEntry,
    MemoryEvidence,
    MemoryOrigin,
    MemorySettings,
    MemoryType,
    PendingJob,
    PendingJobKind,
)
from app.storage.memory_file_store import MemoryFileStore, content_fingerprint


def _entry(**overrides) -> MemoryEntry:
    base = dict(
        name="偏好的播客表达",
        description="用户偏好克制、具体、非说教式的独白",
        type=MemoryType.PREFERENCE,
        body="用户偏好在播客中使用具体例子建立观点，不喜欢抽象说教。",
        keywords=["具体案例", "concrete examples"],
        evidence=[MemoryEvidence(session_id="s1", turn_id="turn_a", quote="我喜欢从具体经历讲起")],
    )
    base.update(overrides)
    return MemoryEntry(**base)


class MemoryFileStoreTests(unittest.TestCase):
    def _store(self, tmp: str) -> MemoryFileStore:
        store = MemoryFileStore(Path(tmp))
        store.bootstrap()
        return store

    def test_frontmatter_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            entry = _entry(origin=MemoryOrigin.EXPLICIT)
            store.save_entry(entry)
            loaded = store.get_entry(entry.id)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.name, entry.name)
            self.assertEqual(loaded.type, MemoryType.PREFERENCE)
            self.assertEqual(loaded.origin, MemoryOrigin.EXPLICIT)
            self.assertEqual(loaded.keywords, entry.keywords)
            self.assertEqual(loaded.evidence[0].turn_id, "turn_a")
            self.assertEqual(loaded.source_count, 1)

    def test_indexes_rebuild_from_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            entry = _entry()
            store.save_entry(entry)
            # Delete the derived indexes and rebuild from markdown only.
            store.catalog_file.unlink()
            store.hot_index_file.unlink()
            store.rebuild_indexes()
            self.assertTrue(store.catalog_file.exists())
            hot = store.hot_index_file.read_text(encoding="utf-8")
            self.assertIn(entry.id, hot)

    def test_sensitive_description_is_generalized_in_hot_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            store.save_entry(
                _entry(
                    name="健康背景",
                    description="具体健康细节不应泄露",
                    type=MemoryType.EXPERIENCE,
                    sensitive=True,
                )
            )
            hot = store.hot_index_file.read_text(encoding="utf-8")
            self.assertNotIn("具体健康细节不应泄露", hot)

    def test_quarantine_on_malformed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            bad = store.entries_dir / "mem_bad.md"
            bad.write_text("not valid", encoding="utf-8")
            store.rebuild_indexes()
            self.assertFalse(bad.exists())
            self.assertTrue((store.quarantine_dir / "mem_bad.md").exists())

    def test_delete_writes_forget_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            entry = _entry()
            store.save_entry(entry)
            store.delete_entry(entry.id)
            self.assertIsNone(store.get_entry(entry.id))
            self.assertTrue(store.has_forget_fingerprint(turn_ids=["turn_a"]))
            self.assertTrue(
                store.has_forget_fingerprint(content_hash=content_fingerprint(entry.body))
            )
            self.assertFalse(store.has_forget_fingerprint(turn_ids=["turn_unrelated"]))

    def test_clear_all_resets_everything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            store.save_entry(_entry())
            store.delete_entry(store.list_entries()[0].id)
            store.clear_all()
            self.assertEqual(store.list_entries(), [])
            # Forget fingerprints are also cleared.
            self.assertFalse(store.has_forget_fingerprint(turn_ids=["turn_a"]))

    def test_settings_and_worker_state_are_independent_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            settings = MemorySettings(first_run_acknowledged=True, writing_enabled=True, usage_enabled=True)
            store.save_settings(settings)
            # Writing worker state must not clobber settings.
            from app.domain.memory import WorkerState, WorkerStatus

            store.save_worker_state(WorkerState(status=WorkerStatus.RUNNING))
            state = store.load_state()
            self.assertTrue(state.settings.writing_enabled)
            self.assertTrue(state.settings.usage_enabled)
            self.assertEqual(state.worker.status, WorkerStatus.RUNNING)

    def test_pending_jobs_fifo_and_retry_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            job = PendingJob(kind=PendingJobKind.EXTRACT_TURNS, session_id="s1")
            store.enqueue(job)
            claimed = store.claim_next()
            self.assertIsNotNone(claimed)
            assert claimed is not None
            self.assertEqual(claimed.job_id, job.job_id)
            store.fail(job.job_id, "boom")
            self.assertEqual(store.claim_next().retry_count, 1)
            store.complete(job.job_id)
            self.assertIsNone(store.claim_next())

    def test_search_and_type_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            store.save_entry(_entry())
            self.assertEqual(len(store.list_entries(search="具体")), 1)
            self.assertEqual(len(store.list_entries(search="不存在")), 0)
            self.assertEqual(len(store.list_entries(type=MemoryType.PREFERENCE)), 1)
            self.assertEqual(len(store.list_entries(type=MemoryType.PROFILE)), 0)


if __name__ == "__main__":
    unittest.main()
