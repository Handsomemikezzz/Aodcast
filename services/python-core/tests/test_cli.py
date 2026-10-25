from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from app.config import AppConfig
from app.main import run
from app.storage.project_store import ProjectStore


class OperatorCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, dict[str, object] | None, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = run(list(args))
        output = stdout.getvalue().strip()
        payload = json.loads(output) if output.startswith("{") else None
        return code, payload, stderr.getvalue()

    def test_configure_and_show_llm_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            code, payload, _ = self.run_cli("--cwd", tmp_dir, "--configure-llm-provider", "mock", "--llm-model", "mock-x")
            self.assertEqual(code, 0)
            assert payload is not None
            self.assertEqual(payload["llm_config"]["provider"], "mock")

            code, payload, _ = self.run_cli("--cwd", tmp_dir, "--show-llm-config")
            self.assertEqual(code, 0)
            assert payload is not None
            self.assertEqual(payload["llm_config"]["model"], "mock-x")

    def test_configure_local_tts_defaults_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            code, payload, _ = self.run_cli("--cwd", tmp_dir, "--configure-tts-provider", "local_http")
            self.assertEqual(code, 0)
            assert payload is not None
            self.assertEqual(payload["tts_config"]["provider"], "local_http")
            self.assertTrue(payload["tts_config"]["model"])

    def test_unsupported_provider_fails_with_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            code, payload, stderr = self.run_cli("--cwd", tmp_dir, "--configure-llm-provider", "bad-provider")
        self.assertEqual(code, 1)
        self.assertIsNone(payload)
        self.assertIn("Unsupported LLM provider", stderr)

    def test_create_demo_session_persists_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            code, payload, _ = self.run_cli("--cwd", tmp_dir, "--create-demo-session", "--topic", "Demo")
            self.assertEqual(code, 0)
            assert payload is not None
            store = ProjectStore(AppConfig.from_cwd(Path(tmp_dir)).data_dir)
            project = store.load_project(str(payload["session_id"]))
        self.assertEqual(project.session.topic, "Demo")
        self.assertIsNotNone(project.script)

    def test_removed_product_commands_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir, self.assertRaises(SystemExit):
            self.run_cli("--cwd", tmp_dir, "--generate-script", "session-123")


if __name__ == "__main__":
    unittest.main()
