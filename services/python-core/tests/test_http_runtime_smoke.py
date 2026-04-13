from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from app.api.http_runtime import RuntimeContext, RuntimeHttpServer
from app.config import AppConfig
from app.orchestration.audio_rendering import AudioRenderingService
from app.orchestration.interview_service import InterviewOrchestrator
from app.orchestration.script_generation import ScriptGenerationService
from app.runtime.request_state_store import RequestStateStore
from app.storage.artifact_store import ArtifactStore
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


class HttpRuntimeSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self.temp_dir.name)
        config = AppConfig.from_cwd(self.cwd)
        store = ProjectStore(config.data_dir)
        config_store = ConfigStore(config.config_dir)
        artifact_store = ArtifactStore(config.data_dir)
        request_state_store = RequestStateStore(config.data_dir)
        store.bootstrap()
        config_store.bootstrap()
        artifact_store.bootstrap()
        request_state_store.bootstrap()

        context = RuntimeContext(
            cwd=self.cwd,
            config=config,
            store=store,
            config_store=config_store,
            artifact_store=artifact_store,
            request_state_store=request_state_store,
            orchestrator=InterviewOrchestrator(store, config_store),
            script_generation=ScriptGenerationService(store, config_store),
            audio_rendering=AudioRenderingService(store, config_store, artifact_store),
            runtime_token="test-token",
            bootstrap_nonce="test-nonce",
            bootstrap_created_at=0.0,
            allowed_origins=frozenset({"http://127.0.0.1:1420"}),
        )
        self.server = RuntimeHttpServer(("127.0.0.1", 0), context)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temp_dir.cleanup()

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, object] | None = None,
        origin: str | None = None,
        token: str | None = None,
    ) -> tuple[int, dict[str, object]]:
        data = None
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if origin is not None:
            headers["Origin"] = origin
        if token is not None:
            headers["X-AOD-Runtime-Token"] = token
        request = urllib_request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib_request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_healthz_returns_ready(self) -> None:
        status, payload = self.request("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ready")

    def test_create_session_returns_bridge_envelope(self) -> None:
        status, payload = self.request(
            "POST",
            "/api/v1/sessions",
            payload={"topic": "HTTP smoke", "creation_intent": "Verify HTTP runtime"},
            origin="http://127.0.0.1:1420",
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["request_state"]["operation"], "create_session")
        self.assertEqual(payload["data"]["project"]["session"]["topic"], "HTTP smoke")

    def test_origin_is_rejected_when_not_allowlisted(self) -> None:
        status, payload = self.request("GET", "/api/v1/projects", origin="https://evil.example")
        self.assertEqual(status, 403)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "bridge_origin_rejected")
        self.assertEqual(payload["error"]["details"]["request_state"]["operation"], "list_projects")

    def test_protected_config_endpoint_requires_runtime_token(self) -> None:
        status, payload = self.request("GET", "/api/v1/config/llm", origin="http://127.0.0.1:1420")
        self.assertEqual(status, 401)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "bridge_auth_required")

    def test_bootstrap_nonce_is_single_use(self) -> None:
        self.server.runtime_context.bootstrap_created_at = __import__("time").time()
        status, payload = self.request(
            "POST",
            "/api/v1/runtime/bootstrap",
            payload={"nonce": "test-nonce"},
            origin="http://127.0.0.1:1420",
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["token"], "test-token")

        status, payload = self.request(
            "POST",
            "/api/v1/runtime/bootstrap",
            payload={"nonce": "test-nonce"},
            origin="http://127.0.0.1:1420",
        )
        self.assertEqual(status, 401)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "bridge_bootstrap_expired")


if __name__ == "__main__":
    unittest.main()
