from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import types
import unittest
import uuid
import wave
from pathlib import Path
from unittest.mock import patch
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class _DummyOpenAI:  # pragma: no cover - import shim only
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    openai_stub.OpenAI = _DummyOpenAI
    sys.modules["openai"] = openai_stub

from app.api.http_runtime import RuntimeContext, RuntimeHttpServer, success_envelope
from app.config import AppConfig
from app.domain.artifact import ArtifactRecord
from app.domain.provider_config import LLMProviderConfig
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord, SessionState
from app.models_catalog import save_custom_model_storage_base
from app.orchestration.audio_rendering import AudioRenderingService, VoicePreviewResult, VoiceRenderSettings
from app.orchestration.interview_service import InterviewOrchestrator
from app.orchestration.script_generation import ScriptGenerationService
from app.providers.llm.codex_app_server import (
    CodexLoginStart,
    CodexModelInfo,
    CodexProviderStatus,
)
from app.runtime.request_state_store import RequestStateStore
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore
from app.storage.speaker_reference_store import SpeakerReferenceStore


class HttpRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self.temp_dir.name)
        self.config = AppConfig.from_cwd(self.cwd)
        self.store = ProjectStore(self.config.data_dir)
        self.config_store = ConfigStore(self.config.config_dir)
        self.artifact_store = ArtifactStore(self.config.data_dir)
        self.speaker_reference_store = SpeakerReferenceStore(self.config.data_dir, self.artifact_store)
        self.request_state_store = RequestStateStore(self.config.data_dir)

        self.store.bootstrap()
        self.config_store.bootstrap()
        self.artifact_store.bootstrap()
        self.speaker_reference_store.bootstrap()
        self.request_state_store.bootstrap()
        self.config_store.save_llm_config(LLMProviderConfig(provider="mock"))

        self.context = RuntimeContext(
            cwd=self.cwd,
            config=self.config,
            store=self.store,
            config_store=self.config_store,
            artifact_store=self.artifact_store,
            speaker_reference_store=self.speaker_reference_store,
            request_state_store=self.request_state_store,
            orchestrator=InterviewOrchestrator(self.store, self.config_store),
            script_generation=ScriptGenerationService(self.store, self.config_store),
            audio_rendering=AudioRenderingService(self.store, self.config_store, self.artifact_store),
            runtime_token="runtime-token",
            bootstrap_nonce="bootstrap-nonce",
            bootstrap_created_at=time.time(),
            allowed_origins=frozenset({"http://localhost:1420"}),
        )
        self.server = RuntimeHttpServer(("127.0.0.1", 0), self.context)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)
        self.temp_dir.cleanup()

    def request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
        token: str | None = None,
    ) -> tuple[int, dict[str, str], dict[str, object]]:
        payload = None
        request_headers = dict(headers or {})
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        if token is not None:
            request_headers.setdefault("X-AOD-Runtime-Token", token)
        request = urllib_request.Request(
            f"{self.base_url}{path}",
            data=payload,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib_request.urlopen(request, timeout=5) as response:
                raw = response.read().decode("utf-8")
                return response.status, dict(response.headers.items()), json.loads(raw)
        except urllib_error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            return exc.code, dict(exc.headers.items()), json.loads(raw)

    def request_bytes(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        request = urllib_request.Request(
            f"{self.base_url}{path}",
            headers=dict(headers or {}),
            method=method,
        )
        try:
            with urllib_request.urlopen(request, timeout=5) as response:
                return response.status, dict(response.headers.items()), response.read()
        except urllib_error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()

    def request_multipart(
        self,
        method: str,
        path: str,
        *,
        fields: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
    ) -> tuple[int, dict[str, str], dict[str, object]]:
        boundary = f"aodcast-{uuid.uuid4().hex}"
        chunks: list[bytes] = []
        for name, value in fields.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                    value.encode("utf-8"),
                    b"\r\n",
                ]
            )
        for name, (filename, content, content_type) in files.items():
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"),
                    f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                    content,
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        request = urllib_request.Request(
            f"{self.base_url}{path}",
            data=b"".join(chunks),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method=method,
        )
        try:
            with urllib_request.urlopen(request, timeout=5) as response:
                raw = response.read().decode("utf-8")
                return response.status, dict(response.headers.items()), json.loads(raw)
        except urllib_error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            return exc.code, dict(exc.headers.items()), json.loads(raw)

    def silent_wav_bytes(self, *, seconds: float, sample_rate: int = 24_000) -> bytes:
        path = self.cwd / f"silent-{uuid.uuid4().hex}.wav"
        frame_count = int(seconds * sample_rate)
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"\x00\x00" * frame_count)
        return path.read_bytes()

    def create_speaker_reference(self, *, name: str = "稳定主播", reference_text: str = "这是一段参考文本。"):
        source_path = self.cwd / f"reference-{uuid.uuid4().hex}.wav"
        source_path.write_bytes(self.silent_wav_bytes(seconds=1))
        return self.speaker_reference_store.create_user_reference(
            name=name,
            source_audio_path=source_path,
            reference_text=reference_text,
            language="zh",
            audio_format="wav",
        )

    def seed_renderable_project(self, *, state: SessionState = SessionState.SCRIPT_EDITED) -> tuple[str, str]:
        session = SessionRecord(topic="Render test", creation_intent="Exercise render task state")
        session.transition(state)
        script = ScriptRecord(
            session_id=session.session_id,
            draft="Draft script",
            final="Final script content for render test.",
        )
        artifact = ArtifactRecord(session_id=session.session_id)
        self.store.save_project(SessionProject(session=session, script=script, artifact=artifact))
        return session.session_id, script.script_id

    def test_cors_preflight_allows_delete_requests(self) -> None:
        status, headers, _ = self.request_bytes(
            "OPTIONS",
            "/api/v1/artifacts/audio",
            headers={
                "Origin": "http://localhost:1420",
                "Access-Control-Request-Method": "DELETE",
            },
        )

        self.assertEqual(status, 204)
        self.assertIn("DELETE", headers["Access-Control-Allow-Methods"])

    def test_artifact_audio_route_streams_export_audio_for_browser_playback(self) -> None:
        audio_path = self.artifact_store.write_audio("session-a", b"RIFF-audio-bytes", "wav")
        encoded_path = urllib_parse.quote(str(audio_path), safe="")

        status, headers, body = self.request_bytes(
            "GET",
            f"/api/v1/artifacts/audio?path={encoded_path}",
            headers={"Origin": "http://localhost:1420"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/wav")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "http://localhost:1420")
        self.assertEqual(body, b"RIFF-audio-bytes")

    def test_artifact_audio_route_serves_mp4_as_audio_mp4(self) -> None:
        audio_path = self.artifact_store.exports_dir / "sample.mp4"
        audio_path.write_bytes(b"fake-mp4-audio")
        encoded_path = urllib_parse.quote(str(audio_path), safe="")

        status, headers, body = self.request_bytes(
            "GET",
            f"/api/v1/artifacts/audio?path={encoded_path}",
            headers={"Origin": "http://localhost:1420"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "audio/mp4")
        self.assertEqual(body, b"fake-mp4-audio")


    def test_delete_artifact_audio_route_removes_preview_file(self) -> None:
        audio_path = self.artifact_store.write_preview_audio(b"preview", "wav")
        encoded_path = urllib_parse.quote(str(audio_path), safe="")

        status, _, payload = self.request_json(
            "DELETE",
            f"/api/v1/artifacts/audio?path={encoded_path}",
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(audio_path.exists())

    def test_delete_artifact_audio_route_rejects_persistent_speaker_reference(self) -> None:
        session_id, script_id = self.seed_renderable_project()
        reference = self.create_speaker_reference()
        self.context.audio_rendering.select_speaker_reference(
            session_id,
            script_id=script_id,
            reference=reference,
        )
        encoded_path = urllib_parse.quote(reference.audio_path, safe="")

        status, _, payload = self.request_json(
            "DELETE",
            f"/api/v1/artifacts/audio?path={encoded_path}",
        )

        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertIn("Only disposable", payload["error"]["message"])
        self.assertTrue(Path(reference.audio_path).is_file())
        reloaded = self.store.load_project_for_script(session_id, script_id)
        assert reloaded.artifact is not None
        self.assertEqual(
            reloaded.artifact.speaker_reference["speaker_reference_id"],
            reference.speaker_reference_id,
        )

    def test_delete_generated_audio_route_clears_project_artifact(self) -> None:
        session_id, _ = self.seed_renderable_project()
        project = self.store.load_project(session_id)
        assert project.artifact is not None
        audio_path = self.artifact_store.write_audio(session_id, b"audio", "wav")
        transcript_path = self.artifact_store.write_transcript(session_id, "transcript")
        project.artifact.audio_path = str(audio_path)
        project.artifact.transcript_path = str(transcript_path)
        project.artifact.provider = "openai_compatible"
        self.store.save_project(project)

        status, _, payload = self.request_json("DELETE", f"/api/v1/sessions/{session_id}/audio")

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(audio_path.exists())
        artifact = payload["data"]["project"]["artifact"]
        self.assertEqual(artifact["audio_path"], "")
        self.assertEqual(artifact["provider"], "")

    def test_delete_generated_audio_route_passes_script_id_scope(self) -> None:
        session_id, script_id = self.seed_renderable_project()
        project = self.store.load_project_for_script(session_id, script_id)
        with patch.object(
            self.context.audio_rendering,
            "delete_generated_audio",
            return_value=project,
        ) as mocked_delete:
            status, _, payload = self.request_json(
                "DELETE",
                f"/api/v1/sessions/{session_id}/audio?script_id={script_id}",
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        mocked_delete.assert_called_once_with(session_id, script_id=script_id)

    def test_artifact_audio_route_rejects_paths_outside_exports_dir(self) -> None:
        outside_path = self.config.data_dir / "sessions" / "not-audio.wav"
        outside_path.parent.mkdir(parents=True, exist_ok=True)
        outside_path.write_bytes(b"not exported audio")
        encoded_path = urllib_parse.quote(str(outside_path), safe="")

        status, _, payload = self.request_json(
            "GET",
            f"/api/v1/artifacts/audio?path={encoded_path}",
            headers={"Origin": "http://localhost:1420"},
        )

        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["request_state"]["operation"], "serve_artifact_audio")

    def test_healthz_is_ready_without_origin_or_auth_checks(self) -> None:
        status, headers, payload = self.request_json(
            "GET",
            "/healthz",
            headers={"Origin": "http://evil.invalid"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(payload["ok"], True)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["service"], "aodcast-python-core-http")
        self.assertIsInstance(payload["runtime"]["pid"], int)
        self.assertIsInstance(payload["runtime"]["started_at_unix"], float)
        self.assertIsInstance(payload["runtime"]["build_token"], str)
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_create_and_list_projects_dispatch_through_cli_envelopes(self) -> None:
        status, _, created = self.request_json(
            "POST",
            "/api/v1/sessions",
            body={"topic": "HTTP Runtime Topic", "creation_intent": "Verify route dispatch"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(created["ok"])
        self.assertEqual(created["data"]["request_state"]["operation"], "create_session")
        session_id = created["data"]["project"]["session"]["session_id"]
        self.assertIsNotNone(created["data"]["project"]["artifact"])

        status, _, listed = self.request_json("GET", "/api/v1/projects?search=runtime")
        self.assertEqual(status, 200)
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["data"]["request_state"]["operation"], "list_projects")
        self.assertEqual(listed["data"]["projects"][0]["session"]["session_id"], session_id)

    def test_markdown_source_create_replace_and_generate_flow(self) -> None:
        source_body = {
            "topic": "Imported",
            "creation_intent": "Adapt an article",
            "source": {
                "raw_markdown": "# My imported post\n\nThis article has enough useful detail to become a spoken podcast episode.",
                "name": "post.md",
                "import_kind": "file",
                "conversion_mode": "adapt",
                "target_length": "short",
                "focus_instructions": "Keep the central lesson.",
            },
        }
        status, _, created = self.request_json("POST", "/api/v1/sessions", body=source_body)

        self.assertEqual(status, 200)
        project = created["data"]["project"]
        session_id = project["session"]["session_id"]
        self.assertEqual(project["session"]["creation_mode"], "markdown")
        self.assertEqual(project["session"]["state"], "ready_to_generate")
        self.assertIsNone(project["transcript"])
        self.assertEqual(project["source"]["version"], 1)

        replacement = dict(source_body["source"])
        replacement["raw_markdown"] = "# Updated post\n\nThis replacement contains enough different material for a new source version."
        status, _, updated = self.request_json(
            "PUT",
            f"/api/v1/sessions/{session_id}/source",
            body=replacement,
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["data"]["request_state"]["operation"], "update_episode_source")
        self.assertEqual(updated["data"]["project"]["source"]["version"], 2)

        status, _, generated = self.request_json(
            "POST",
            f"/api/v1/sessions/{session_id}/script:generate",
            body={},
        )
        self.assertEqual(status, 200)
        self.assertEqual(generated["data"]["project"]["script"]["generation_metadata"]["source"]["version"], 2)

    def test_delete_and_restore_session_colon_routes(self) -> None:
        status, _, created = self.request_json(
            "POST",
            "/api/v1/sessions",
            body={"topic": "Delete route", "creation_intent": "Verify colon route parsing"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(created["ok"])
        session_id = created["data"]["project"]["session"]["session_id"]

        status, _, deleted = self.request_json("POST", f"/api/v1/sessions/{session_id}:delete", body={})
        self.assertEqual(status, 200)
        self.assertTrue(deleted["ok"])
        self.assertEqual(deleted["data"]["request_state"]["operation"], "delete_session")
        self.assertIsNotNone(deleted["data"]["project"]["session"]["deleted_at"])

        status, _, restored = self.request_json("POST", f"/api/v1/sessions/{session_id}:restore", body={})
        self.assertEqual(status, 200)
        self.assertTrue(restored["ok"])
        self.assertEqual(restored["data"]["request_state"]["operation"], "restore_session")
        self.assertIsNone(restored["data"]["project"]["session"]["deleted_at"])

    def test_unknown_route_returns_error_envelope_with_request_state_details(self) -> None:
        status, _, payload = self.request_json("GET", "/api/v1/not-real")

        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "python_core_error")
        self.assertEqual(payload["request_state"]["operation"], "http_runtime")
        self.assertEqual(payload["error"]["details"]["request_state"], payload["request_state"])
        self.assertNotIn("runtime", payload)
        self.assertIsInstance(payload["error"]["details"]["runtime"]["pid"], int)
        self.assertIn("Unknown route", payload["error"]["message"])

    def test_config_routes_require_runtime_token(self) -> None:
        status, _, payload = self.request_json("GET", "/api/v1/config/llm")

        self.assertEqual(status, 401)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "bridge_auth_required")
        self.assertEqual(payload["request_state"]["operation"], "show_llm_config")

    def test_llm_preflight_reports_missing_openai_compatible_fields(self) -> None:
        self.config_store.save_llm_config(
            LLMProviderConfig(
                provider="openai_compatible",
                model="",
                base_url=" ",
                api_key="",
            )
        )

        status, _, payload = self.request_json(
            "GET",
            "/api/v1/config/llm/preflight",
            token="runtime-token",
        )

        self.assertEqual(status, 200)
        data = payload["data"]["llm_preflight"]
        self.assertFalse(data["ready"])
        self.assertEqual(data["provider"], "openai_compatible")
        self.assertEqual(data["missing_fields"], ["base_url", "model", "api_key"])
        self.assertEqual(data["supported_actions"], ["start_interview", "submit_reply", "generate_script"])
        self.assertIn("Language model setup is incomplete", data["message"])

    def test_llm_preflight_reports_mock_as_ready(self) -> None:
        self.config_store.save_llm_config(LLMProviderConfig(provider="mock"))

        status, _, payload = self.request_json(
            "GET",
            "/api/v1/config/llm/preflight",
            token="runtime-token",
        )

        self.assertEqual(status, 200)
        data = payload["data"]["llm_preflight"]
        self.assertTrue(data["ready"])
        self.assertEqual(data["provider"], "mock")
        self.assertEqual(data["missing_fields"], [])
        self.assertIn("ready", data["message"].lower())

    def test_configure_tts_persists_local_ref_audio_path(self) -> None:
        status, _, bootstrap = self.request_json(
            "POST",
            "/api/v1/runtime/bootstrap",
            body={"nonce": "bootstrap-nonce"},
        )
        self.assertEqual(status, 200)
        token = bootstrap["data"]["token"]

        status, _, payload = self.request_json(
            "PUT",
            "/api/v1/config/tts",
            token=token,
            body={
                "provider": "local_mlx",
                "model": "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
                "local_runtime": "mlx",
                "local_model_path": "/tmp/model",
                "local_ref_audio_path": "/tmp/ref.wav",
            },
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["tts_config"]["local_ref_audio_path"], "/tmp/ref.wav")

    def test_model_storage_status_route(self) -> None:
        status, _, payload = self.request_json("GET", "/api/v1/models/storage")

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["request_state"]["operation"], "show_model_storage")
        storage = payload["data"]["model_storage"]
        self.assertIn("current_base", storage)
        self.assertFalse(storage["is_custom"])

    def test_model_storage_reset_route(self) -> None:
        status, _, payload = self.request_json("POST", "/api/v1/models/storage:reset", body={})

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["request_state"]["operation"], "reset_model_storage")
        self.assertIn("model_storage", payload["data"])

    def test_model_storage_migrate_route_persists_task_state(self) -> None:
        save_custom_model_storage_base(self.config_store, self.cwd / "source-models")
        destination = self.cwd / "migrated-models"

        status, _, payload = self.request_json(
            "POST",
            "/api/v1/models/storage:migrate",
            body={"destination": str(destination)},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["request_state"]["operation"], "migrate_model_storage")
        task_id = str(payload["data"]["task_id"])
        self.assertEqual(task_id, "migrate_model_storage")
        task_state: dict[str, object] | None = None
        for _ in range(50):
            state_status, _, state_payload = self.request_json("GET", f"/api/v1/tasks/{task_id}")
            self.assertEqual(state_status, 200)
            task_state = state_payload["data"]["task_state"]  # type: ignore[assignment]
            if isinstance(task_state, dict) and task_state.get("phase") == "succeeded":
                break
            time.sleep(0.05)
        assert isinstance(task_state, dict)
        self.assertEqual(task_state["phase"], "succeeded")

    def test_runtime_bootstrap_nonce_is_single_use(self) -> None:
        status, _, first = self.request_json(
            "POST",
            "/api/v1/runtime/bootstrap",
            body={"nonce": "bootstrap-nonce"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(first["ok"])
        self.assertEqual(first["data"]["token"], "runtime-token")
        self.assertEqual(first["data"]["request_state"]["operation"], "runtime_bootstrap")

        status, _, second = self.request_json(
            "POST",
            "/api/v1/runtime/bootstrap",
            body={"nonce": "bootstrap-nonce"},
        )
        self.assertEqual(status, 401)
        self.assertFalse(second["ok"])
        self.assertEqual(second["error"]["code"], "bridge_bootstrap_expired")

    def test_audio_render_route_passes_provider_and_model_overrides_to_runtime_context(self) -> None:
        with patch.object(
            RuntimeContext,
            "start_render_audio",
            autospec=True,
            return_value=success_envelope({"task_id": "render_audio:session-123"}, operation="render_audio"),
        ) as mocked_start:
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/sessions/session-123/audio:render",
                body={"provider_override": "local_mlx", "model_id": "voxcpm2-8bit"},
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        mocked_start.assert_called_once_with(
            self.context,
            "session-123",
            script_id="",
            override_provider="local_mlx",
            override_model="mlx-community/VoxCPM2-8bit",
            settings=None,
            require_speaker_reference=False,
        )

    def test_audio_render_route_passes_script_id_to_runtime_context(self) -> None:
        with patch.object(
            RuntimeContext,
            "start_render_audio",
            autospec=True,
            return_value=success_envelope({"task_id": "render_audio:session-123"}, operation="render_audio"),
        ) as mocked_start:
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/sessions/session-123/audio:render",
                body={"provider_override": "openai_compatible", "script_id": "script-abc"},
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        mocked_start.assert_called_once_with(
            self.context,
            "session-123",
            script_id="script-abc",
            override_provider="openai_compatible",
            override_model="",
            settings=None,
            require_speaker_reference=False,
        )


    def test_audio_render_route_passes_voice_settings_to_runtime_context(self) -> None:
        with patch.object(
            RuntimeContext,
            "start_render_audio",
            autospec=True,
            return_value=success_envelope({"task_id": "render_audio:session-123"}, operation="render_audio"),
        ) as mocked_start:
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/sessions/session-123/audio:render",
                body={
                    "script_id": "script-abc",
                    "voice_settings": {
                        "voice_id": "casual_chat",
                        "style_id": "casual",
                        "speed": 0.9,
                    },
                },
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        mocked_start.assert_called_once()
        _, args, kwargs = mocked_start.mock_calls[0]
        self.assertEqual(args[1], "session-123")
        self.assertEqual(kwargs["script_id"], "script-abc")
        self.assertEqual(kwargs["settings"].voice_id, "casual_chat")
        self.assertEqual(kwargs["settings"].style_id, "casual")
        self.assertEqual(kwargs["settings"].speed, 0.9)
        self.assertEqual(kwargs["require_speaker_reference"], False)

    def test_audio_render_route_passes_require_speaker_reference_to_runtime_context(self) -> None:
        with patch.object(
            RuntimeContext,
            "start_render_audio",
            autospec=True,
            return_value=success_envelope({"task_id": "render_audio:session-123"}, operation="render_audio"),
        ) as mocked_start:
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/sessions/session-123/audio:render",
                body={"require_speaker_reference": True},
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        mocked_start.assert_called_once_with(
            self.context,
            "session-123",
            script_id="",
            override_provider="",
            override_model="",
            settings=None,
            require_speaker_reference=True,
        )

    def test_audio_render_route_parses_string_false_require_speaker_reference(self) -> None:
        with patch.object(
            RuntimeContext,
            "start_render_audio",
            autospec=True,
            return_value=success_envelope({"task_id": "render_audio:session-123"}, operation="render_audio"),
        ) as mocked_start:
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/sessions/session-123/audio:render",
                body={"require_speaker_reference": "false"},
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(mocked_start.call_args.kwargs["require_speaker_reference"], False)

    def test_voice_presets_route_returns_packaged_cards(self) -> None:
        status, _, payload = self.request_json("GET", "/api/v1/voice-studio/presets")

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["request_state"]["operation"], "list_voice_presets")
        self.assertGreaterEqual(len(payload["data"]["voices"]), 5)
        self.assertGreaterEqual(len(payload["data"]["styles"]), 4)
        self.assertEqual(payload["data"]["standard_preview_text"], "欢迎收听今天的节目，我们将用几分钟理清一个复杂但重要的话题。")

    def test_voice_preview_route_returns_audio_without_session(self) -> None:
        from tests.tts_test_fakes import SineWaveTTSProvider

        with (
            patch(
                "app.orchestration.audio_rendering.build_tts_provider",
                return_value=SineWaveTTSProvider(),
            ),
            patch(
                "app.orchestration.podcast_rendering.build_tts_provider",
                return_value=SineWaveTTSProvider(),
            ),
        ):
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/voice-studio/preview",
                body={
                    "voice_id": "warm_narrator",
                    "voice_name": "Warm Narrator",
                    "style_id": "natural",
                    "style_name": "Natural",
                    "speed": 1.2,
                    "preview_text": "自定义试音文本。",
                },
            )

            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["data"]["request_state"]["operation"], "render_voice_preview")
            self.assertEqual(payload["data"]["request_state"]["phase"], "running")
            task_id = str(payload["data"]["task_id"])
            self.assertTrue(task_id.startswith("render_voice_preview:"))
            self.assertEqual(payload["data"]["request_state"].get("task_id"), task_id)
            self.assertTrue(str(payload["data"]["request_state"].get("run_token") or ""))

            task_state: dict[str, object] | None = None
            for _ in range(20):
                state_status, _, state_payload = self.request_json("GET", f"/api/v1/tasks/{task_id}")
                self.assertEqual(state_status, 200)
                task_state = state_payload["data"]["task_state"]  # type: ignore[assignment]
                if isinstance(task_state, dict) and task_state.get("phase") == "succeeded":
                    break
                time.sleep(0.05)

            assert isinstance(task_state, dict)
            self.assertEqual(task_state["phase"], "succeeded")
            self.assertEqual(task_state["settings"]["preview_text"], "自定义试音文本。")
            self.assertTrue(Path(str(task_state["audio_path"])).exists())


    def test_voice_preview_route_passes_provider_override_to_runtime_context(self) -> None:
        with patch.object(
            RuntimeContext,
            "start_render_voice_preview",
            autospec=True,
            return_value=success_envelope({"task_id": "render_voice_preview:token"}, operation="render_voice_preview"),
        ) as mocked_start:
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/voice-studio/preview",
                body={
                    "voice_id": "news_anchor",
                    "style_id": "news",
                    "provider_override": "openai_compatible",
                    "session_id": "session-123",
                    "script_id": "script-abc",
                },
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        mocked_start.assert_called_once()
        _, args, kwargs = mocked_start.mock_calls[0]
        self.assertEqual(kwargs["session_id"], "session-123")
        self.assertEqual(kwargs["script_id"], "script-abc")
        self.assertEqual(kwargs["override_provider"], "openai_compatible")
        self.assertEqual(args[1].voice_id, "news_anchor")

    def test_voice_preview_route_passes_speaker_reference_id_to_runtime_context(self) -> None:
        with patch.object(
            RuntimeContext,
            "start_render_voice_preview",
            autospec=True,
            return_value=success_envelope({"task_id": "render_voice_preview:test"}, operation="render_voice_preview"),
        ) as mocked_start:
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/voice-studio/preview",
                body={
                    "session_id": "session-123",
                    "script_id": "script-abc",
                    "speaker_reference_id": "speaker-123",
                    "preview_text": "试听当前音色。",
                },
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        settings = mocked_start.call_args.args[1]
        self.assertEqual(settings.preview_text, "试听当前音色。")
        self.assertEqual(mocked_start.call_args.kwargs["session_id"], "session-123")
        self.assertEqual(mocked_start.call_args.kwargs["script_id"], "script-abc")
        self.assertEqual(mocked_start.call_args.kwargs["speaker_reference_id"], "speaker-123")

    def test_start_render_voice_preview_resolves_speaker_reference(self) -> None:
        reference = self.create_speaker_reference()
        preview_audio = self.artifact_store.write_preview_audio(b"preview-audio", "wav")
        settings = VoiceRenderSettings(preview_text="试听当前音色。")

        with patch.object(
            self.context.audio_rendering,
            "render_voice_preview_with_cancellation",
            return_value=VoicePreviewResult(
                provider="local_mlx",
                model="mlx-voice",
                audio_path=str(preview_audio),
                settings=settings,
            ),
        ) as mocked_render:
            result = self.context.start_render_voice_preview(
                settings,
                speaker_reference_id=reference.speaker_reference_id,
            )

            task_id = str(result["data"]["task_id"])
            deadline = time.time() + 2.0
            state: dict[str, object] | None = None
            while time.time() < deadline:
                loaded_state = self.request_state_store.load(task_id)
                if isinstance(loaded_state, dict) and str(loaded_state.get("phase")) == "succeeded":
                    state = loaded_state
                    break
                time.sleep(0.02)

        self.assertIsNotNone(state)
        speaker_reference = mocked_render.call_args.kwargs["speaker_reference"]
        self.assertEqual(speaker_reference["speaker_reference_id"], reference.speaker_reference_id)
        self.assertEqual(speaker_reference["audio_path"], reference.audio_path)
        self.assertEqual(speaker_reference["reference_text"], reference.reference_text)

    def test_speaker_references_route_lists_builtins(self) -> None:
        status, _, payload = self.request_json("GET", "/api/v1/speaker-references")

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["request_state"]["operation"], "list_speaker_references")
        references = payload["data"]["speaker_references"]
        built_ins = [reference for reference in references if reference["source"] == "built_in"]
        self.assertEqual(len(built_ins), 2)
        self.assertTrue(all(Path(reference["audio_path"]).exists() for reference in built_ins))

    def test_create_speaker_reference_accepts_single_multipart_request(self) -> None:
        status, _, payload = self.request_multipart(
            "POST",
            "/api/v1/speaker-references",
            fields={
                "name": "我的知识主播",
                "reference_text": "这是一段用于克隆音色的参考文本。",
                "language": "zh",
                "audio_format": "wav",
            },
            files={"audio": ("reference.wav", self.silent_wav_bytes(seconds=2), "audio/wav")},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["request_state"]["operation"], "create_speaker_reference")
        reference = payload["data"]["speaker_reference"]
        self.assertEqual(reference["name"], "我的知识主播")
        self.assertEqual(reference["source"], "user_saved")
        self.assertEqual(reference["reference_text"], "这是一段用于克隆音色的参考文本。")
        self.assertEqual(reference["duration_ms"], 2000)
        self.assertTrue(Path(reference["audio_path"]).exists())

    def test_patch_speaker_reference_updates_metadata(self) -> None:
        reference = self.create_speaker_reference(name="待编辑音色", reference_text="原始参考文本。")

        status, _, payload = self.request_json(
            "PATCH",
            f"/api/v1/speaker-references/{reference.speaker_reference_id}",
            body={"name": "已编辑音色", "reference_text": "更新后的参考文本。", "language": "zh-CN"},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["request_state"]["operation"], "update_speaker_reference")
        updated = payload["data"]["speaker_reference"]
        self.assertEqual(updated["speaker_reference_id"], reference.speaker_reference_id)
        self.assertEqual(updated["name"], "已编辑音色")
        self.assertEqual(updated["reference_text"], "更新后的参考文本。")
        self.assertEqual(updated["language"], "zh-CN")

    def test_select_speaker_reference_for_script(self) -> None:
        session_id, script_id = self.seed_renderable_project()
        reference = self.create_speaker_reference()

        status, _, payload = self.request_json(
            "POST",
            f"/api/v1/sessions/{session_id}/scripts/{script_id}/speaker-reference:select",
            body={"speaker_reference_id": reference.speaker_reference_id},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["request_state"]["operation"], "select_speaker_reference")
        selected = payload["data"]["project"]["artifact"]["speaker_reference"]
        self.assertEqual(selected["speaker_reference_id"], reference.speaker_reference_id)
        self.assertEqual(selected["reference_hash"], reference.reference_hash)
        self.assertEqual(selected["audio_path"], reference.audio_path)

    def test_segment_regeneration_route_passes_manifest_ids(self) -> None:
        with patch.object(
            RuntimeContext,
            "start_regenerate_audio_window",
            autospec=True,
            return_value=success_envelope(
                {"task_id": "render_audio:session-123:script-abc", "affected_segment_ids": ["segment-2"]},
                operation="regenerate_audio_window",
            ),
        ) as mocked_start:
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/sessions/session-123/scripts/script-abc/audio/segments/segment-2:regenerate",
                body={"speech_plan_id": "plan-123", "render_manifest_id": "render-123"},
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        mocked_start.assert_called_once_with(
            self.context,
            "session-123",
            script_id="script-abc",
            target_segment_id="segment-2",
            expected_plan_id="plan-123",
            expected_render_id="render-123",
        )

    def test_cancel_task_accepts_current_run_token(self) -> None:
        task_id = "render_audio:session-123:script-abc"
        self.request_state_store.save(
            task_id,
            {
                "operation": "render_audio",
                "phase": "running",
                "progress_percent": 42.0,
                "message": "Rendering audio...",
                "run_token": "token-abc",
            },
        )

        status, _, payload = self.request_json(
            "POST",
            f"/api/v1/tasks/{task_id}:cancel",
            body={"run_token": "token-abc"},
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["task_state"]["phase"], "cancelling")
        self.assertEqual(payload["data"]["task_state"]["run_token"], "token-abc")
        self.assertEqual(payload["data"]["request_state"]["run_token"], "token-abc")
        self.assertTrue(self.request_state_store.is_cancel_requested(task_id, run_token="token-abc"))

    def test_cancel_task_rejects_stale_run_token(self) -> None:
        task_id = "render_audio:session-123:script-abc"
        self.request_state_store.save(
            task_id,
            {
                "operation": "render_audio",
                "phase": "running",
                "progress_percent": 42.0,
                "message": "Rendering audio...",
                "run_token": "token-current",
            },
        )

        status, _, payload = self.request_json(
            "POST",
            f"/api/v1/tasks/{task_id}:cancel",
            body={"run_token": "token-stale"},
        )

        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["request_state"]["operation"], "cancel_task")
        self.assertEqual(payload["error"]["message"], "stale_task_run")
        state = self.request_state_store.load(task_id)
        assert state is not None
        self.assertEqual(state["phase"], "running")
        self.assertFalse(self.request_state_store.is_cancel_requested(task_id, run_token="token-current"))

    def test_start_render_audio_failure_persists_run_token_and_non_empty_message(self) -> None:
        session_id, script_id = self.seed_renderable_project()
        with patch.object(
            self.context.audio_rendering,
            "render_audio_with_cancellation",
            side_effect=Exception(""),
        ):
            result = self.context.start_render_audio(
                session_id,
                script_id=script_id,
                override_provider="openai_compatible",
            )

        task_id = str(result["data"]["task_id"])
        deadline = time.time() + 2.0
        state: dict[str, object] | None = None
        while time.time() < deadline:
            loaded_state = self.request_state_store.load(task_id)
            if isinstance(loaded_state, dict) and str(loaded_state.get("phase")) == "failed":
                state = loaded_state
                break
            time.sleep(0.02)

        self.assertIsNotNone(state)
        assert state is not None
        self.assertEqual(state["operation"], "render_audio")
        self.assertEqual(state["phase"], "failed")
        self.assertIsInstance(state.get("message"), str)
        self.assertNotEqual(str(state.get("message")).strip(), "")
        self.assertIsInstance(state.get("run_token"), str)
        self.assertNotEqual(str(state.get("run_token")).strip(), "")

    def test_config_routes_reject_unsupported_providers(self) -> None:
        status, _, payload = self.request_json(
            "PUT",
            "/api/v1/config/llm",
            body={"provider": "bad-provider"},
            token="runtime-token",
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertIn("Unsupported LLM provider", payload["error"]["message"])

        status, _, payload = self.request_json(
            "PUT",
            "/api/v1/config/tts",
            body={"provider": "bad-provider"},
            token="runtime-token",
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])
        self.assertIn("Unsupported TTS provider", payload["error"]["message"])

    def test_llm_connection_mock_provider_returns_success_instantly(self) -> None:
        status, _, payload = self.request_json(
            "POST",
            "/api/v1/config/llm/test",
            body={
                "provider": "mock",
                "model": "any-model",
                "base_url": "http://any-url",
                "api_key": "any-key",
            },
            token="runtime-token",
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], "success")
        self.assertEqual(payload["data"]["latency_ms"], 0)

    @staticmethod
    def _codex_status() -> CodexProviderStatus:
        return CodexProviderStatus(
            installed=True,
            executable_path="/usr/local/bin/codex",
            version="codex-cli test",
            authenticated=True,
            auth_mode="chatgpt",
            plan_type="plus",
            account_email="user@example.com",
            models=(
                CodexModelInfo(
                    id="gpt-test",
                    display_name="GPT Test",
                    is_default=True,
                    default_reasoning_effort="low",
                    supported_reasoning_efforts=("low", "medium"),
                ),
            ),
            rate_limit=None,
            message="Connected to ChatGPT subscription (plus).",
        )

    def test_codex_subscription_status_route_returns_account_models(self) -> None:
        with patch(
            "app.api.http_runtime.codex_provider_status",
            return_value=self._codex_status(),
        ):
            status, _, payload = self.request_json(
                "GET",
                "/api/v1/config/llm/status",
                token="runtime-token",
            )

        self.assertEqual(status, 200)
        data = payload["data"]["llm_provider_status"]
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["plan_type"], "plus")
        self.assertEqual(data["models"][0]["id"], "gpt-test")
        self.assertNotIn("access_token", data)

    def test_codex_subscription_login_route_returns_official_auth_url(self) -> None:
        with patch(
            "app.api.http_runtime.start_codex_login",
            return_value=CodexLoginStart(
                login_id="login-1",
                auth_url="https://chatgpt.com/auth/codex?state=test",
            ),
        ):
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/config/llm/auth:start",
                body={"provider": "codex_subscription"},
                token="runtime-token",
            )

        self.assertEqual(status, 200)
        auth = payload["data"]["llm_auth"]
        self.assertEqual(auth["login_id"], "login-1")
        self.assertTrue(auth["auth_url"].startswith("https://chatgpt.com/"))

    def test_codex_connection_rejects_unsupported_reasoning_effort(self) -> None:
        with patch(
            "app.api.http_runtime.codex_provider_status",
            return_value=self._codex_status(),
        ):
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/config/llm/test",
                body={
                    "provider": "codex_subscription",
                    "model": "gpt-test",
                    "reasoning_effort": "ultra",
                    "base_url": "",
                    "api_key": "",
                },
                token="runtime-token",
            )

        self.assertEqual(status, 500)
        self.assertFalse(payload["ok"])
        self.assertIn("not supported", payload["error"]["message"])

    def test_configuring_codex_subscription_clears_api_credentials(self) -> None:
        self.config_store.save_llm_config(
            LLMProviderConfig(
                provider="openai_compatible",
                model="gpt-api",
                base_url="https://api.openai.com/v1",
                api_key="secret-key",
            )
        )

        status, _, payload = self.request_json(
            "PUT",
            "/api/v1/config/llm",
            body={
                "provider": "codex_subscription",
                "model": "gpt-test",
                "reasoning_effort": "high",
            },
            token="runtime-token",
        )

        self.assertEqual(status, 200)
        config = payload["data"]["llm_config"]
        self.assertEqual(config["provider"], "codex_subscription")
        self.assertEqual(config["reasoning_effort"], "high")
        self.assertEqual(config["base_url"], "")
        self.assertEqual(config["api_key"], "")


    def test_audio_export_route_converts_to_wav(self) -> None:
        audio_path = self.artifact_store.write_audio("session-a", b"RIFF-audio-bytes", "wav")
        status, _, payload = self.request_json(
            "POST",
            "/api/v1/artifacts/audio/export",
            body={
                "audio_path": str(audio_path),
                "format": "wav",
                "filename": "my-podcast-episode",
            },
            token="runtime-token",
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["file_name"], "my-podcast-episode.wav")
        self.assertIn("/api/v1/artifacts/audio?path=", payload["data"]["audio_url"])
        exported_path = Path(payload["data"]["audio_path"])
        self.assertTrue(exported_path.is_file())
        self.assertEqual(exported_path.name, "my-podcast-episode.wav")

    def test_audio_export_route_writes_192k_mp3_beside_the_wav_take(self) -> None:
        audio_path = self.artifact_store.write_audio("session-a", b"RIFF-audio-bytes", "wav")
        with patch("shutil.which", return_value="/usr/local/bin/ffmpeg"), patch("subprocess.run") as run:
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/artifacts/audio/export",
                body={
                    "audio_path": str(audio_path),
                    "format": "mp3",
                    "bitrate": "192k",
                },
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["file_name"], "audio.mp3")
        exported_path = Path(payload["data"]["audio_path"])
        self.assertEqual(exported_path, audio_path.with_suffix(".mp3"))
        command = run.call_args.args[0]
        self.assertIn("libmp3lame", command)
        self.assertEqual(command[command.index("-b:a") + 1], "192k")

    def test_audio_export_route_rejects_unsupported_format(self) -> None:
        audio_path = self.artifact_store.write_audio("session-a", b"RIFF-audio-bytes", "wav")
        status, _, payload = self.request_json(
            "POST",
            "/api/v1/artifacts/audio/export",
            body={
                "audio_path": str(audio_path),
                "format": "flac",
            },
            token="runtime-token",
        )
        self.assertEqual(status, 400)
        self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
