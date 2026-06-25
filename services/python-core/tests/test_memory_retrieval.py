from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.domain.memory import MemoryEntry, MemoryEvidence, MemoryOrigin, MemoryType
from app.orchestration.memory_retrieval import MemoryRetrieval, RetrievalQuery
from app.storage.memory_file_store import MemoryFileStore


class MemoryRetrievalTests(unittest.TestCase):
    def _store(self, tmp: str) -> MemoryFileStore:
        store = MemoryFileStore(Path(tmp))
        store.bootstrap()
        return store

    def _save(self, store: MemoryFileStore, **overrides) -> MemoryEntry:
        base = dict(
            name="表达偏好",
            description="偏好具体例子",
            type=MemoryType.PREFERENCE,
            body="用户偏好用具体案例讲述",
            keywords=["具体案例", "concrete examples"],
            evidence=[MemoryEvidence(session_id="s1", turn_id="turn_a", quote="具体案例")],
        )
        base.update(overrides)
        entry = MemoryEntry(**base)
        store.save_entry(entry)
        return entry

    def test_keyword_recall_zh_and_en(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            self._save(store)
            retrieval = MemoryRetrieval(store)
            zh = retrieval.build_interview_context(
                RetrievalQuery(topic="职场成长", recent_user_message="想聊聊具体案例")
            )
            self.assertEqual(zh.item_count, 1)
            en = retrieval.build_interview_context(
                RetrievalQuery(topic="career", recent_user_message="give me concrete examples")
            )
            self.assertEqual(en.item_count, 1)

    def test_caps_at_three_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            for i in range(5):
                self._save(
                    store,
                    name=f"偏好{i}",
                    keywords=["叙事"],
                    evidence=[MemoryEvidence(session_id="s1", turn_id=f"t{i}", quote="叙事")],
                )
            retrieval = MemoryRetrieval(store)
            ctx = retrieval.build_interview_context(RetrievalQuery(recent_user_message="叙事"))
            self.assertLessEqual(ctx.item_count, 3)

    def test_prompt_block_carries_priority_notice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            self._save(store)
            retrieval = MemoryRetrieval(store)
            ctx = retrieval.build_interview_context(RetrievalQuery(recent_user_message="具体案例"))
            self.assertIn("background only", ctx.prompt_block)
            self.assertIn("you mentioned before", ctx.prompt_block)

    def test_sensitive_body_not_readable_without_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            entry = self._save(
                store,
                name="健康背景",
                description="敏感细节",
                type=MemoryType.EXPERIENCE,
                body="非常具体的私人健康正文",
                keywords=["健康"],
                sensitive=True,
            )
            retrieval = MemoryRetrieval(store)
            # Unauthorized: only a generalized placeholder, never the body.
            unauth = retrieval.build_interview_context(RetrievalQuery(recent_user_message="健康"))
            self.assertNotIn("非常具体的私人健康正文", unauth.prompt_block)
            self.assertNotIn("敏感细节", unauth.prompt_block)
            # Authorized: body/description may appear.
            auth = retrieval.build_interview_context(
                RetrievalQuery(recent_user_message="健康", authorized_memory_ids=(entry.id,))
            )
            self.assertIn("敏感细节", auth.prompt_block)

    def test_empty_when_no_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            retrieval = MemoryRetrieval(store)
            ctx = retrieval.build_interview_context(RetrievalQuery(recent_user_message="anything"))
            self.assertEqual(ctx.item_count, 0)
            self.assertEqual(ctx.prompt_block, "")


if __name__ == "__main__":
    unittest.main()
