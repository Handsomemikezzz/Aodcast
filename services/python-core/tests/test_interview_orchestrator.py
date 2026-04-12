from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import AppConfig
from app.domain.project import SessionProject
from app.domain.provider_config import LLMProviderConfig
from app.domain.session import SessionRecord, SessionState
from app.domain.transcript import Speaker
from app.orchestration.interview_service import InterviewOrchestrator
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


class InterviewOrchestratorTests(unittest.TestCase):
    def build_orchestrator(self) -> tuple[ProjectStore, InterviewOrchestrator]:
        self.temp_dir = tempfile.TemporaryDirectory()
        config = AppConfig.from_cwd(Path(self.temp_dir.name))
        store = ProjectStore(config.data_dir)
        config_store = ConfigStore(config.config_dir)
        store.bootstrap()
        config_store.bootstrap()
        config_store.save_llm_config(LLMProviderConfig(provider="mock"))
        return store, InterviewOrchestrator(store, config_store)

    def tearDown(self) -> None:
        temp_dir = getattr(self, "temp_dir", None)
        if temp_dir is not None:
            temp_dir.cleanup()

    def test_start_interview_appends_first_agent_question(self) -> None:
        store, orchestrator = self.build_orchestrator()
        session = SessionRecord(topic="Local-first tools", creation_intent="Test start")
        store.save_project(SessionProject(session=session))

        result = orchestrator.start_interview(session.session_id)
        loaded = store.load_project(session.session_id)

        self.assertEqual(result.project.session.state, SessionState.INTERVIEW_IN_PROGRESS)
        self.assertFalse(result.ai_can_finish)
        self.assertIsNotNone(result.next_question)
        assert loaded.transcript is not None
        self.assertEqual(len(loaded.transcript.turns), 1)
        self.assertEqual(loaded.transcript.turns[0].speaker, Speaker.AGENT)

    def test_user_response_with_missing_dimensions_keeps_interview_running(self) -> None:
        store, orchestrator = self.build_orchestrator()
        session = SessionRecord(topic="AI workflow", creation_intent="Test loop")
        store.save_project(SessionProject(session=session))
        orchestrator.start_interview(session.session_id)

        result = orchestrator.submit_user_response(
            session.session_id,
            "I want to talk about AI tooling because it keeps changing.",
        )
        loaded = store.load_project(session.session_id)

        self.assertEqual(result.project.session.state, SessionState.INTERVIEW_IN_PROGRESS)
        self.assertFalse(result.ai_can_finish)
        self.assertEqual(result.readiness.missing_dimensions(), ["example_or_detail", "conclusion"])
        assert loaded.transcript is not None
        self.assertEqual(len(loaded.transcript.turns), 3)
        self.assertEqual(loaded.transcript.turns[-1].speaker, Speaker.AGENT)

    def test_ready_response_moves_session_to_ready_to_generate(self) -> None:
        store, orchestrator = self.build_orchestrator()
        session = SessionRecord(topic="AI workflow", creation_intent="Test ready")
        store.save_project(SessionProject(session=session))
        orchestrator.start_interview(session.session_id)

        result = orchestrator.submit_user_response(
            session.session_id,
            (
                "I think local-first AI tools matter because teams need reliable workflows. "
                "For example, last week I had to recover a broken setup by rebuilding the project "
                "locally, and the takeaway is that tooling should fail in a way users can recover."
            ),
        )

        self.assertEqual(result.project.session.state, SessionState.READY_TO_GENERATE)
        self.assertTrue(result.ai_can_finish)
        self.assertTrue(result.readiness.is_ready)
        self.assertIsNone(result.next_question)

    def test_explicit_finish_request_moves_to_ready_even_if_not_ready(self) -> None:
        store, orchestrator = self.build_orchestrator()
        session = SessionRecord(topic="AI workflow", creation_intent="Test stop")
        store.save_project(SessionProject(session=session))
        orchestrator.start_interview(session.session_id)

        result = orchestrator.submit_user_response(
            session.session_id,
            "I think this matters.",
            user_requested_finish=True,
        )

        self.assertEqual(result.project.session.state, SessionState.READY_TO_GENERATE)
        self.assertTrue(result.ai_can_finish)


if __name__ == "__main__":
    unittest.main()
