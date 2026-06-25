from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.domain.memory import MemoryOrigin, MemoryType
from app.domain.provider_config import LLMProviderConfig
from app.domain.session import SessionRecord
from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.memory_extraction import MemoryExtractor
from app.orchestration.memory_validation import (
    MemoryValidationError,
    ValidationContext,
    validate_candidates,
)
from app.orchestration.sensitive import contains_forbidden, detect_forbidden
from app.storage.config_store import ConfigStore
from app.storage.memory_file_store import MemoryFileStore
from app.storage.project_store import ProjectStore


def _ctx(session_id: str, turns: dict[str, str], origin=MemoryOrigin.AUTO) -> ValidationContext:
    return ValidationContext(session_id=session_id, batch_turns=turns, origin=origin)


class MemoryValidationTests(unittest.TestCase):
    def _store(self, tmp: str) -> MemoryFileStore:
        store = MemoryFileStore(Path(tmp))
        store.bootstrap()
        return store

    def test_rejects_more_than_three_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            candidates = [
                {"type": "preference", "name": "n", "description": "d", "body": "b",
                 "evidence": [{"turn_id": "t1", "quote": "hi"}]}
                for _ in range(4)
            ]
            with self.assertRaises(MemoryValidationError):
                validate_candidates(candidates, _ctx("s1", {"t1": "hi there"}), store)

    def test_rejects_invalid_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            candidates = [{"type": "bogus", "name": "n", "description": "d", "body": "b",
                           "evidence": [{"turn_id": "t1", "quote": "hi"}]}]
            with self.assertRaises(MemoryValidationError):
                validate_candidates(candidates, _ctx("s1", {"t1": "hi"}), store)

    def test_rejects_evidence_turn_not_in_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            candidates = [{"type": "preference", "name": "n", "description": "d", "body": "b",
                           "evidence": [{"turn_id": "other", "quote": "hi"}]}]
            with self.assertRaises(MemoryValidationError):
                validate_candidates(candidates, _ctx("s1", {"t1": "hi"}), store)

    def test_rejects_quote_not_substring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            candidates = [{"type": "preference", "name": "n", "description": "d", "body": "b",
                           "evidence": [{"turn_id": "t1", "quote": "fabricated quote"}]}]
            with self.assertRaises(MemoryValidationError):
                validate_candidates(candidates, _ctx("s1", {"t1": "the real content"}), store)

    def test_rejects_forbidden_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            candidates = [{"type": "profile", "name": "pw", "description": "d",
                           "body": "我的密码是 hunter2secretpw",
                           "evidence": [{"turn_id": "t1", "quote": "我的密码是 hunter2secretpw"}]}]
            with self.assertRaises(MemoryValidationError):
                validate_candidates(
                    candidates, _ctx("s1", {"t1": "我的密码是 hunter2secretpw"}), store
                )

    def test_valid_candidate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store(tmp)
            candidates = [{"type": "preference", "name": "表达偏好", "description": "克制",
                           "body": "用户偏好具体例子", "keywords": ["具体"],
                           "evidence": [{"turn_id": "t1", "quote": "我喜欢具体例子"}]}]
            entries = validate_candidates(candidates, _ctx("s1", {"t1": "我喜欢具体例子讲述"}), store)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].type, MemoryType.PREFERENCE)


class SensitiveTests(unittest.TestCase):
    def test_detects_password_assignment(self) -> None:
        self.assertTrue(contains_forbidden("我的密码是 abc12345"))
        self.assertTrue(contains_forbidden("password: s3cretValue"))

    def test_detects_national_id(self) -> None:
        self.assertTrue(detect_forbidden("身份证 11010119900307123X"))

    def test_allows_ordinary_text(self) -> None:
        self.assertFalse(contains_forbidden("我喜欢从具体经历讲起，不要说教。"))


class MemoryExtractionTests(unittest.TestCase):
    def _setup(self, tmp: str):
        data = Path(tmp)
        ps = ProjectStore(data)
        ps.bootstrap()
        cs = ConfigStore(data)
        cs.bootstrap()
        cs.save_llm_config(LLMProviderConfig(provider="mock", model="m", base_url="", api_key=""))
        store = MemoryFileStore(data)
        store.bootstrap()
        return ps, cs, store

    def _session_with_turns(self, ps: ProjectStore, contents: list[str]) -> SessionRecord:
        session = SessionRecord(topic="职场成长", creation_intent="分享经验")
        transcript = TranscriptRecord(session_id=session.session_id)
        for content in contents:
            transcript.append(Speaker.USER, content)
        ps.save_session(session)
        ps.save_transcript(transcript)
        return session

    def test_extracts_only_from_user_turns_and_advances_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, cs, store = self._setup(tmp)
            session = self._session_with_turns(
                ps, ["我喜欢从一个具体经历讲起，不要最后突然上价值。"]
            )
            extractor = MemoryExtractor(ps, cs, store)
            written = extractor.extract_turns(session.session_id)
            self.assertGreaterEqual(len(written), 1)
            self.assertEqual(written[0].origin, MemoryOrigin.AUTO)
            # Evidence references a real user turn.
            self.assertTrue(written[0].evidence)
            transcript = ps.load_transcript(session.session_id)
            self.assertEqual(written[0].evidence[0].turn_id, transcript.turns[0].turn_id)
            # Cursor advanced to the last user turn.
            reloaded = ps.load_session(session.session_id)
            self.assertEqual(
                reloaded.memory_processed_through_turn_id, transcript.turns[-1].turn_id
            )

    def test_cursor_prevents_reprocessing_same_turns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, cs, store = self._setup(tmp)
            session = self._session_with_turns(ps, ["我喜欢具体例子，不喜欢说教。"])
            extractor = MemoryExtractor(ps, cs, store)
            extractor.extract_turns(session.session_id)
            count_after_first = len(store.list_entries())
            # In real operation the worker passes from_turn_id=cursor, so already
            # processed turns are never re-extracted -> no duplicate entries.
            cursor = ps.load_session(session.session_id).memory_processed_through_turn_id
            written = extractor.extract_turns(session.session_id, from_turn_id=cursor)
            self.assertEqual(written, [])
            self.assertEqual(len(store.list_entries()), count_after_first)

    def test_explicit_normalization_marks_origin_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps, cs, store = self._setup(tmp)
            session = self._session_with_turns(ps, ["请记住我喜欢用具体案例开场。"])
            transcript = ps.load_transcript(session.session_id)
            extractor = MemoryExtractor(ps, cs, store)
            written = extractor.normalize_explicit(
                session.session_id,
                source_turn_id=transcript.turns[-1].turn_id,
                raw_intent="请记住我喜欢用具体案例开场。",
            )
            self.assertGreaterEqual(len(written), 1)
            self.assertEqual(written[0].origin, MemoryOrigin.EXPLICIT)


if __name__ == "__main__":
    unittest.main()
