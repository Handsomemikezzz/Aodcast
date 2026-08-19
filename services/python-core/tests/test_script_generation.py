from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import AppConfig
from app.domain.project import SessionProject
from app.domain.episode_source import EpisodeSource, SourceImportKind
from app.domain.provider_config import LLMProviderConfig
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord, SessionState
from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.script_generation import ScriptGenerationService
from app.providers.llm.base import ScriptGenerationResponse
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


class ScriptGenerationTests(unittest.TestCase):
    def build_environment(self) -> tuple[ProjectStore, ConfigStore, ScriptGenerationService]:
        self.temp_dir = tempfile.TemporaryDirectory()
        config = AppConfig.from_cwd(Path(self.temp_dir.name))
        store = ProjectStore(config.data_dir)
        config_store = ConfigStore(config.config_dir)
        store.bootstrap()
        config_store.bootstrap()
        return store, config_store, ScriptGenerationService(store, config_store)

    def tearDown(self) -> None:
        temp_dir = getattr(self, "temp_dir", None)
        if temp_dir is not None:
            temp_dir.cleanup()

    def seed_ready_project(self, store: ProjectStore) -> str:
        session = SessionRecord(topic="Local tools", creation_intent="Explain a workflow")
        session.transition(SessionState.READY_TO_GENERATE)
        transcript = TranscriptRecord(session_id=session.session_id)
        transcript.append(Speaker.AGENT, "What is the key idea?")
        transcript.append(
            Speaker.USER,
            (
                "I think local-first tools matter because they make recovery easier. "
                "For example, last week I rebuilt a broken setup, and the takeaway is "
                "that workflows should fail in recoverable ways."
            ),
        )
        store.save_project(SessionProject(session=session, transcript=transcript, script=None))
        return session.session_id

    def test_generate_script_with_mock_provider_updates_session(self) -> None:
        store, config_store, service = self.build_environment()
        config_store.save_llm_config(LLMProviderConfig(provider="mock"))
        session_id = self.seed_ready_project(store)

        result = service.generate_draft(session_id)
        loaded = store.load_project(session_id)

        self.assertEqual(result.provider, "mock")
        self.assertEqual(loaded.session.state, SessionState.SCRIPT_GENERATED)
        assert loaded.script is not None
        assert loaded.artifact is not None
        self.assertNotIn("Opening\n", loaded.script.draft)
        self.assertIn("Today I want to talk about", loaded.script.draft)
        self.assertEqual(loaded.session.llm_provider, "mock")
        self.assertEqual(loaded.artifact.session_id, session_id)

    def test_generate_script_from_markdown_without_transcript(self) -> None:
        store, config_store, service = self.build_environment()
        config_store.save_llm_config(LLMProviderConfig(provider="mock"))
        session = SessionRecord(topic="Imported ideas", creation_intent="Adapt the article")
        session.transition(SessionState.READY_TO_GENERATE)
        source = EpisodeSource.from_markdown(
            session_id=session.session_id,
            name="ideas.md",
            import_kind=SourceImportKind.FILE,
            raw_markdown=(
                "# Imported ideas\n\nLocal-first creative tools make recovery easier and help authors keep control. "
                "The most important takeaway is that ownership should remain visible."
            ),
        )
        store.save_project(SessionProject(session=session, source=source))

        service.generate_draft(session.session_id)
        loaded = store.load_project(session.session_id)

        self.assertEqual(loaded.session.state, SessionState.SCRIPT_GENERATED)
        self.assertIsNone(loaded.transcript)
        assert loaded.script is not None
        metadata_source = loaded.script.generation_metadata["source"]
        self.assertEqual(metadata_source["content_hash"], source.content_hash)
        self.assertEqual(metadata_source["version"], 1)
        self.assertIn("source material", loaded.script.draft)

    def test_concurrent_source_replace_cannot_be_rolled_back_by_generation(self) -> None:
        store, config_store, service = self.build_environment()
        config_store.save_llm_config(LLMProviderConfig(provider="mock"))
        session = SessionRecord(topic="Concurrent source", creation_intent="Protect latest source")
        session.transition(SessionState.READY_TO_GENERATE)
        first = EpisodeSource.from_markdown(
            session_id=session.session_id,
            name="v1.md",
            import_kind=SourceImportKind.FILE,
            raw_markdown="# Version one\n\nThis first article contains enough detail for generation.",
        )
        store.save_project(SessionProject(session=session, source=first))

        started = threading.Event()
        release = threading.Event()
        result_holder = []

        class BlockingProvider:
            def generate_script(self, request):
                started.set()
                release.wait(timeout=2)
                return ScriptGenerationResponse(
                    draft="Generated from version one.",
                    provider_name="blocking",
                    model_name="blocking-model",
                )

        def run_generation() -> None:
            result_holder.append(service.generate_draft(session.session_id))

        with patch("app.orchestration.script_generation.build_llm_provider", return_value=BlockingProvider()):
            thread = threading.Thread(target=run_generation)
            thread.start()
            self.assertTrue(started.wait(timeout=2))
            second = store.replace_source(
                session_id=session.session_id,
                raw_markdown="# Version two\n\nThis replacement is newer and has enough readable detail.",
                name="v2.md",
                import_kind=SourceImportKind.FILE,
                conversion_mode=first.conversion_mode,
                target_length=first.target_length,
                focus_instructions="",
            )
            release.set()
            thread.join(timeout=2)

        self.assertFalse(thread.is_alive())
        loaded = store.load_project(session.session_id)
        self.assertEqual(loaded.source.version, 2)
        self.assertEqual(loaded.source.content_hash, second.content_hash)
        self.assertEqual(loaded.script.generation_metadata["source"]["version"], 1)
        self.assertEqual(result_holder[0].project.source.version, 2)

    def test_generate_script_failure_preserves_project_and_marks_failed(self) -> None:
        store, config_store, service = self.build_environment()
        config_store.save_llm_config(
            LLMProviderConfig(
                provider="openai_compatible",
                model="gpt-test",
                base_url="https://example.invalid/v1",
                api_key="",
            )
        )
        session_id = self.seed_ready_project(store)

        with self.assertRaises(ValueError):
            service.generate_draft(session_id)

        loaded = store.load_project(session_id)
        self.assertEqual(loaded.session.state, SessionState.FAILED)
        self.assertIn("requires an api_key", loaded.session.last_error)
        assert loaded.transcript is not None
        self.assertEqual(len(loaded.transcript.turns), 2)

    def test_generate_script_rejects_audio_rendering_state(self) -> None:
        store, config_store, service = self.build_environment()
        config_store.save_llm_config(LLMProviderConfig(provider="mock"))
        session = SessionRecord(topic="Rendering", creation_intent="Busy")
        session.transition(SessionState.AUDIO_RENDERING)
        transcript = TranscriptRecord(session_id=session.session_id)
        transcript.append(Speaker.AGENT, "Hello")
        script = ScriptRecord(session_id=session.session_id)
        store.save_project(SessionProject(session=session, transcript=transcript, script=script))

        with self.assertRaises(ValueError):
            service.generate_draft(session.session_id)

    def test_second_generate_creates_new_script_file(self) -> None:
        store, config_store, service = self.build_environment()
        config_store.save_llm_config(LLMProviderConfig(provider="mock"))
        session_id = self.seed_ready_project(store)

        first = service.generate_draft(session_id)
        loaded_after_first = store.load_project(session_id)
        assert loaded_after_first.script is not None
        first_script_id = loaded_after_first.script.script_id
        loaded_after_first.script.save_final("User edited final script")
        loaded_after_first.session.transition(SessionState.READY_TO_GENERATE)
        store.save_project(loaded_after_first)

        second = service.generate_draft(session_id)
        loaded_after_second = store.load_project(session_id)
        assert loaded_after_second.script is not None

        self.assertEqual(first.provider, second.provider)
        self.assertNotEqual(first_script_id, loaded_after_second.script.script_id)
        scripts = store.list_scripts(session_id)
        self.assertEqual(len(scripts), 2)
        older = store.load_script_by_id(session_id, first_script_id)
        self.assertEqual(older.final, "User edited final script")


if __name__ == "__main__":
    unittest.main()
