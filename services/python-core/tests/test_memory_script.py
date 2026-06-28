from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.domain.memory import MemoryEntry, MemoryEvidence, MemoryType
from app.domain.provider_config import LLMProviderConfig
from app.domain.session import SessionRecord, SessionState
from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.memory_retrieval import MemoryRetrieval, RetrievalQuery
from app.orchestration.memory_service import MemoryService
from app.orchestration.script_generation import ScriptGenerationService
from app.providers.llm.base import MemoryRerankRequest
from app.providers.llm.mock_provider import MockLLMProvider
from app.storage.config_store import ConfigStore
from app.storage.memory_file_store import MemoryFileStore
from app.storage.project_store import ProjectStore


def _entry(store: MemoryFileStore, **overrides) -> MemoryEntry:
    base = dict(
        name="n",
        description="d",
        type=MemoryType.VIEWPOINT,
        body="b",
        keywords=[],
        evidence=[MemoryEvidence(session_id="s", turn_id="t", quote="q")],
    )
    base.update(overrides)
    entry = MemoryEntry(**base)
    store.save_entry(entry)
    return entry


class RerankProviderTests(unittest.TestCase):
    def test_mock_rerank_is_deterministic_and_capped(self) -> None:
        provider = MockLLMProvider()
        req = MemoryRerankRequest(
            topic="职场成长复盘",
            creation_intent="分享",
            candidates=[
                {"id": "m1", "type": "viewpoint", "name": "复盘观点", "description": "成长靠复盘"},
                {"id": "m2", "type": "preference", "name": "天气", "description": "喜欢晴天"},
                {"id": "m3", "type": "experience", "name": "复盘经历", "description": "一次复盘"},
            ],
            max_select=2,
        )
        first = provider.rerank_memories(req).selected_ids
        second = provider.rerank_memories(req).selected_ids
        self.assertEqual(first, second)
        self.assertLessEqual(len(first), 2)
        self.assertIn("m1", first)


class ScriptRetrievalTests(unittest.TestCase):
    def _store(self, tmp: str) -> MemoryFileStore:
        store = MemoryFileStore(Path(tmp))
        store.bootstrap()
        return store

    def test_eligibility_and_sensitive_two_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            vp = _entry(store, name="复盘观点", type=MemoryType.VIEWPOINT, keywords=["复盘"], body="坚信复盘")
            exp = _entry(store, name="复盘经历", type=MemoryType.EXPERIENCE, keywords=["复盘"], body="去年复盘")
            sens = _entry(
                store, name="健康", type=MemoryType.EXPERIENCE, sensitive=True, keywords=["复盘"],
                body="私人健康正文SECRET",
            )
            retrieval = MemoryRetrieval(store)
            captured: dict = {}

            def rerank(index):
                captured["index"] = index
                return [c["id"] for c in index]

            # transcript re-mentions 复盘 -> experience eligible; sensitive excluded (unauthorized)
            q = RetrievalQuery(topic="职场", creation_intent="分享", transcript_text="聊聊复盘")
            ctx = retrieval.build_script_context(q, rerank=rerank)
            self.assertIn(vp.id, ctx.memory_ids)
            self.assertIn(exp.id, ctx.memory_ids)
            self.assertNotIn(sens.id, ctx.memory_ids)
            self.assertNotIn("私人健康正文SECRET", ctx.prompt_block)
            # sensitive entry must never have appeared in the rerank index either
            self.assertFalse(any(c["id"] == sens.id for c in captured["index"]))

    def test_authorized_sensitive_body_included(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            sens = _entry(
                store, name="健康", type=MemoryType.EXPERIENCE, sensitive=True, keywords=["复盘"],
                body="私人健康正文SECRET",
            )
            captured: dict = {}

            def rerank(index):
                captured["index"] = index
                return [c["id"] for c in index]

            retrieval = MemoryRetrieval(store)
            q = RetrievalQuery(
                topic="职场", creation_intent="分享", transcript_text="复盘",
                authorized_memory_ids=(sens.id,),
            )
            ctx = retrieval.build_script_context(q, rerank=rerank)
            self.assertIn(sens.id, ctx.memory_ids)
            self.assertIn("私人健康正文SECRET", ctx.prompt_block)
            # Even when authorized, the body is not exposed during the rerank phase.
            sens_idx = next(c for c in captured["index"] if c["id"] == sens.id)
            self.assertNotIn("私人健康正文SECRET", sens_idx["description"])
            self.assertNotIn("私人健康正文SECRET", sens_idx["name"])

    def test_rerank_failure_falls_back_to_local(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            _entry(store, name="复盘观点", type=MemoryType.VIEWPOINT, keywords=["复盘"], body="坚信复盘")
            retrieval = MemoryRetrieval(store)

            def boom(_index):
                raise RuntimeError("provider down")

            ctx = retrieval.build_script_context(
                RetrievalQuery(topic="复盘", creation_intent="分享", transcript_text="复盘"),
                rerank=boom,
            )
            self.assertGreaterEqual(ctx.item_count, 1)

    def test_authorization_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            vp = _entry(store, name="复盘观点", type=MemoryType.VIEWPOINT, keywords=["复盘"])
            exp = _entry(store, name="复盘经历", type=MemoryType.EXPERIENCE, keywords=["复盘"])
            sens = _entry(store, name="健康", type=MemoryType.EXPERIENCE, sensitive=True, keywords=["健康"])
            retrieval = MemoryRetrieval(store)
            # relevant query, empty transcript so experience is not re-mentioned
            cands = retrieval.list_script_authorization_candidates(
                RetrievalQuery(topic="复盘 健康", creation_intent="分享", transcript_text="")
            )
            ids = {c.id for c in cands}
            self.assertIn(sens.id, ids)
            self.assertIn(exp.id, ids)
            self.assertNotIn(vp.id, ids)


class ScriptGenerationMemoryTests(unittest.TestCase):
    def _setup(self, tmp: str):
        data = Path(tmp)
        ps = ProjectStore(data)
        ps.bootstrap()
        cs = ConfigStore(data)
        cs.bootstrap()
        cs.save_llm_config(LLMProviderConfig(provider="mock", model="m", base_url="", api_key=""))
        svc = MemoryService(data, ps, cs)
        svc.store.bootstrap()
        svc.acknowledge_first_run()
        return ps, cs, svc

    def _ready_session(self, ps: ProjectStore) -> SessionRecord:
        session = SessionRecord(topic="职场复盘", creation_intent="分享复盘方法")
        session.transition(SessionState.READY_TO_GENERATE)
        transcript = TranscriptRecord(session_id=session.session_id)
        transcript.append(Speaker.USER, "我认为成长靠复盘。")
        ps.save_session(session)
        ps.save_transcript(transcript)
        return session

    def test_generation_without_memory_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, cs, svc = self._setup(tmp)
            session = self._ready_session(ps)
            gen = ScriptGenerationService(ps, cs, svc)
            result = gen.generate_draft(session.session_id)
            self.assertIsNotNone(result.project.script)

    def test_unauthorized_sensitive_never_reaches_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, cs, svc = self._setup(tmp)
            session = self._ready_session(ps)
            svc.store.save_entry(
                MemoryEntry(
                    name="复盘观点", description="成长靠复盘", type=MemoryType.VIEWPOINT,
                    body="我坚信职场成长来自持续复盘", keywords=["复盘", "职场"],
                    evidence=[MemoryEvidence(session_id="x", turn_id="t", quote="复盘")],
                )
            )
            svc.store.save_entry(
                MemoryEntry(
                    name="健康", description="敏感", type=MemoryType.EXPERIENCE, sensitive=True,
                    body="私人健康正文SECRET", keywords=["复盘"],
                    evidence=[MemoryEvidence(session_id="x", turn_id="t2", quote="复盘")],
                )
            )
            gen = ScriptGenerationService(ps, cs, svc)
            result = gen.generate_draft(session.session_id)
            draft = result.project.script.final or result.project.script.draft
            self.assertIn("持续复盘", draft)  # viewpoint flowed in
            self.assertNotIn("私人健康正文SECRET", draft)  # unauthorized sensitive did not
            # usage recorded as a "script" op
            reloaded = ps.load_session(session.session_id)
            self.assertIn("script", [e["operation"] for e in reloaded.memory_usage_events])

    def test_authorized_sensitive_reaches_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, cs, svc = self._setup(tmp)
            session = self._ready_session(ps)
            sens = MemoryEntry(
                name="健康", description="敏感", type=MemoryType.EXPERIENCE, sensitive=True,
                body="私人健康正文SECRET", keywords=["复盘"],
                evidence=[MemoryEvidence(session_id="x", turn_id="t2", quote="复盘")],
            )
            svc.store.save_entry(sens)
            svc.authorize(session.session_id, sens.id)
            gen = ScriptGenerationService(ps, cs, svc)
            result = gen.generate_draft(session.session_id)
            draft = result.project.script.final or result.project.script.draft
            self.assertIn("私人健康正文SECRET", draft)

    def test_memory_disabled_episode_uses_no_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, cs, svc = self._setup(tmp)
            session = self._ready_session(ps)
            session.set_memory_mode("disabled")
            ps.save_session(session)
            svc.store.save_entry(
                MemoryEntry(
                    name="复盘观点", description="d", type=MemoryType.VIEWPOINT,
                    body="我坚信职场成长来自持续复盘", keywords=["复盘"],
                    evidence=[MemoryEvidence(session_id="x", turn_id="t", quote="复盘")],
                )
            )
            gen = ScriptGenerationService(ps, cs, svc)
            result = gen.generate_draft(session.session_id)
            draft = result.project.script.final or result.project.script.draft
            self.assertNotIn("持续复盘", draft)

    def test_authorize_rejects_unknown_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, cs, svc = self._setup(tmp)
            session = self._ready_session(ps)
            with self.assertRaises(ValueError):
                svc.authorize(session.session_id, "mem_does_not_exist")


if __name__ == "__main__":
    unittest.main()
