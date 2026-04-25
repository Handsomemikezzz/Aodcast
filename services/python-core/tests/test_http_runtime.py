from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib import error as urllib_error
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
from app.orchestration.audio_rendering import AudioRenderingService
from app.orchestration.interview_service import InterviewOrchestrator
from app.orchestration.script_generation import ScriptGenerationService
from app.runtime.request_state_store import RequestStateStore
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


class HttpRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self.temp_dir.name)
        self.config = AppConfig.from_cwd(self.cwd)
        self.store = ProjectStore(self.config.data_dir)
        self.config_store = ConfigStore(self.config.config_dir)
        self.artifact_store = ArtifactStore(self.config.data_dir)
        self.request_state_store = RequestStateStore(self.config.data_dir)

        self.store.bootstrap()
        self.config_store.bootstrap()
        self.artifact_store.bootstrap()
        self.request_state_store.bootstrap()
        self.config_store.save_llm_config(LLMProviderConfig(provider="mock"))

        self.context = RuntimeContext(
            cwd=self.cwd,
            config=self.config,
            store=self.store,
            config_store=self.config_store,
            artifact_store=self.artifact_store,
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

        status, _, listed = self.request_json("GET", "/api/v1/projects?search=runtime")
        self.assertEqual(status, 200)
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["data"]["request_state"]["operation"], "list_projects")
        self.assertEqual(listed["data"]["projects"][0]["session"]["session_id"], session_id)

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

    def test_audio_render_route_passes_provider_override_to_runtime_context(self) -> None:
        with patch.object(
            RuntimeContext,
            "start_render_audio",
            autospec=True,
            return_value=success_envelope({"task_id": "render_audio:session-123"}, operation="render_audio"),
        ) as mocked_start:
            status, _, payload = self.request_json(
                "POST",
                "/api/v1/sessions/session-123/audio:render",
                body={"provider_override": "mock_remote"},
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        mocked_start.assert_called_once_with(
            self.context,
            "session-123",
            script_id="",
            override_provider="mock_remote",
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
                body={"provider_override": "mock_remote", "script_id": "script-abc"},
            )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        mocked_start.assert_called_once_with(
            self.context,
            "session-123",
            script_id="script-abc",
            override_provider="mock_remote",
        )

    def test_cancel_task_preserves_run_token_in_cancelling_state(self) -> None:
        task_id = "render_audio:session-123"
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
        )

        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["task_state"]["phase"], "cancelling")
        self.assertEqual(payload["data"]["task_state"]["run_token"], "token-abc")
        self.assertEqual(payload["data"]["request_state"]["run_token"], "token-abc")

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
                override_provider="mock_remote",
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


if __name__ == "__main__":
    unittest.main()
