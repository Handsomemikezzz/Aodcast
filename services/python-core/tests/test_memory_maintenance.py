from __future__ import annotations

import tempfile
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domain.memory import (
    MemoryEntry,
    MemoryEvidence,
    MemoryOrigin,
    MemoryType,
    PendingJob,
    PendingJobKind,
)
from app.domain.provider_config import LLMProviderConfig
from app.domain.session import SessionRecord
from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.memory_maintenance import MemoryMaintenance
from app.orchestration.memory_service import MemoryService
from app.storage.config_store import ConfigStore
from app.storage.memory_file_store import MemoryFileStore
from app.storage.project_store import ProjectStore


def _entry(store: MemoryFileStore, **overrides) -> MemoryEntry:
    base = dict(
        name="n",
        description="d",
        type=MemoryType.VIEWPOINT,
        body="b",
        keywords=["复盘"],
        evidence=[MemoryEvidence(session_id="s", turn_id="t", quote="q")],
    )
    base.update(overrides)
    entry = MemoryEntry(**base)
    store.save_entry(entry)
    return entry


def _config(tmp: str) -> ConfigStore:
    cs = ConfigStore(Path(tmp))
    cs.bootstrap()
    cs.save_llm_config(LLMProviderConfig(provider="mock", model="m", base_url="", api_key=""))
    return cs


class MaintenanceGatingTests(unittest.TestCase):
    def test_should_run_truth_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryFileStore(Path(tmp))
            store.bootstrap()
            maint = MemoryMaintenance(store, _config(tmp))

            # No changes -> never run.
            self.assertFalse(maint.should_run())

            # 5+ changes -> run.
            store.note_change(5)
            self.assertTrue(maint.should_run())

            # Just maintained -> within 24h -> don't run even with a change.
            store.mark_maintained()
            store.note_change(6)
            self.assertFalse(maint.should_run())

    def test_forced_when_below_interval_skipped_if_all_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryFileStore(Path(tmp))
            store.bootstrap()
            maint = MemoryMaintenance(store, _config(tmp))
            # Fewer than threshold changes, just maintained, small store -> no run.
            store.mark_maintained()
            store.note_change(1)
            self.assertFalse(maint.should_run())


class MaintenanceMergeTests(unittest.TestCase):
    def test_merges_duplicates_and_supersedes_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryFileStore(Path(tmp))
            store.bootstrap()
            maint = MemoryMaintenance(store, _config(tmp))
            a = _entry(store, name="复盘A", body="b1", evidence=[MemoryEvidence(session_id="s", turn_id="t1", quote="q1")])
            b = _entry(store, name="复盘B", body="b2", evidence=[MemoryEvidence(session_id="s", turn_id="t2", quote="q2")])
            store.note_change(6)
            more = maint.run_batch()
            ids = {e.id for e in store.list_entries()}
            self.assertEqual(len(ids), 1)
            self.assertIn(a.id, ids)
            self.assertFalse(more)
            self.assertIn(b.id, {e.id for e in store.list_superseded()})
            # Maintenance resets the gate.
            self.assertEqual(store.load_state().settings.changes_since_maintenance, 0)

    def test_explicit_origin_preserved_through_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryFileStore(Path(tmp))
            store.bootstrap()
            maint = MemoryMaintenance(store, _config(tmp))
            _entry(store, name="A", origin=MemoryOrigin.AUTO, created_at="2024-01-01T00:00:00Z",
                   evidence=[MemoryEvidence(session_id="s", turn_id="t1", quote="q")])
            _entry(store, name="B", origin=MemoryOrigin.EXPLICIT, created_at="2024-02-01T00:00:00Z",
                   evidence=[MemoryEvidence(session_id="s", turn_id="t2", quote="q")])
            store.note_change(6)
            maint.run_batch()
            remaining = store.list_entries()
            self.assertEqual(len(remaining), 1)
            self.assertEqual(remaining[0].origin, MemoryOrigin.EXPLICIT)

    def test_fabricated_evidence_merge_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryFileStore(Path(tmp))
            store.bootstrap()
            maint = MemoryMaintenance(store, _config(tmp))
            _entry(store, name="A", evidence=[MemoryEvidence(session_id="s", turn_id="t1", quote="q")])
            _entry(store, name="B", evidence=[MemoryEvidence(session_id="s", turn_id="t2", quote="q")])

            class FakeProvider:
                def merge_memories(self, request):
                    from app.providers.llm.base import MemoryMergeResponse

                    return MemoryMergeResponse(
                        primary_id=request.entries[0]["id"], name="x", description="y", body="z",
                        keywords=[], evidence_turn_ids=["FAKE"], drop_ids=[request.entries[1]["id"]],
                        provider_name="f", model_name="f",
                    )

            import app.orchestration.memory_maintenance as mod

            original = mod.build_llm_provider
            mod.build_llm_provider = lambda cfg: FakeProvider()
            try:
                store.note_change(6)
                maint.run_batch()
            finally:
                mod.build_llm_provider = original
            self.assertEqual(len(store.list_entries()), 2)  # originals kept


class EpisodeLifecycleTests(unittest.TestCase):
    def _service(self, tmp: str):
        data = Path(tmp)
        ps = ProjectStore(data)
        ps.bootstrap()
        cs = _config(tmp)
        svc = MemoryService(data, ps, cs)
        svc.store.bootstrap()
        svc.acknowledge_first_run()
        return ps, svc

    def test_delete_source_drops_evidence_and_single_source_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, svc = self._service(tmp)
            # Entry sourced only from session S1 -> should be deleted (no forget).
            solo = _entry(svc.store, name="solo", evidence=[MemoryEvidence(session_id="S1", turn_id="t1", quote="q")])
            # Entry with two sources -> kept, source_count drops.
            multi = _entry(
                svc.store, name="multi",
                evidence=[
                    MemoryEvidence(session_id="S1", turn_id="t2", quote="q"),
                    MemoryEvidence(session_id="S2", turn_id="t3", quote="q"),
                ],
            )
            svc.delete_source("S1")
            self.assertIsNone(svc.store.get_entry(solo.id))
            # No forget fingerprint -> re-expressible.
            self.assertFalse(svc.store.has_forget_fingerprint(turn_ids=["t1"]))
            kept = svc.store.get_entry(multi.id)
            self.assertIsNotNone(kept)
            self.assertEqual(kept.source_count, 1)
            self.assertEqual(kept.evidence[0].session_id, "S2")

    def test_on_session_deleted_enqueues_delete_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, svc = self._service(tmp)
            svc.on_session_deleted("S9")
            pending = svc.store.list_pending()
            self.assertTrue(any(j.kind == PendingJobKind.DELETE_SOURCE and j.session_id == "S9" for j in pending))


class PurgeWorkerTests(unittest.TestCase):
    def test_purge_superseded_removes_old_and_writes_forget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryFileStore(Path(tmp))
            store.bootstrap()
            e = _entry(store, evidence=[MemoryEvidence(session_id="s", turn_id="t1", quote="q")])
            store.move_to_superseded(e.id)
            # Backdate superseded_at beyond 30 days.
            sup = store.list_superseded()[0]
            sup.superseded_at = (datetime.now(UTC) - timedelta(days=40)).isoformat()
            (store.superseded_dir / f"{sup.id}.md").write_text(store._entry_to_markdown(sup), encoding="utf-8")
            removed = store.purge_superseded(days=30)
            self.assertEqual(removed, 1)
            self.assertEqual(store.list_superseded(), [])
            self.assertTrue(store.has_forget_fingerprint(turn_ids=["t1"]))

    def test_worker_dispatches_new_job_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            ps = ProjectStore(data)
            ps.bootstrap()
            cs = _config(tmp)
            svc = MemoryService(data, ps, cs)
            svc.bootstrap()
            try:
                # Seed two duplicates + enough changes so should_run() triggers on idle.
                _entry(svc.store, name="复盘A", evidence=[MemoryEvidence(session_id="s", turn_id="t1", quote="q1")])
                _entry(svc.store, name="复盘B", evidence=[MemoryEvidence(session_id="s", turn_id="t2", quote="q2")])
                svc.store.note_change(6)
                deadline = time.time() + 5.0
                while time.time() < deadline and len(svc.store.list_entries()) > 1:
                    time.sleep(0.05)
                self.assertEqual(len(svc.store.list_entries()), 1)
            finally:
                svc.shutdown()


if __name__ == "__main__":
    unittest.main()
