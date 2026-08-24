from __future__ import annotations

import json
import unittest
from typing import Any, Iterator
from unittest.mock import patch

from app.domain.provider_config import LLMProviderConfig
from app.providers.llm.base import (
    InterviewQuestionRequest,
    MemoryExtractionRequest,
    MemoryRerankRequest,
    ScriptGenerationRequest,
)
from app.providers.llm.codex_app_server import (
    CodexAppServerClient,
    CodexAppServerError,
    CodexModelInfo,
    CodexProviderStatus,
    CodexSubscriptionProvider,
)
from app.providers.llm.preflight import check_llm_config


class FakeCodexClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def resolve_model(self, requested_model: str) -> str:
        return requested_model or "gpt-test"

    def complete_turn(
        self,
        *,
        model: str,
        reasoning_effort: str,
        developer_instructions: str,
        user_content: str,
        output_schema: dict[str, Any] | None = None,
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "reasoning_effort": reasoning_effort,
                "developer_instructions": developer_instructions,
                "user_content": user_content,
                "output_schema": output_schema,
            }
        )
        properties = output_schema.get("properties", {}) if output_schema else {}
        if "candidates" in properties:
            return json.dumps(
                {
                    "candidates": [
                        {
                            "type": "preference",
                            "name": "Concrete examples",
                            "description": "Prefers examples",
                            "body": "Use concrete examples",
                            "keywords": ["examples"],
                            "sensitive": False,
                            "evidence": [{"turn_id": "t1", "quote": "concrete examples"}],
                            "merge_target_id": "",
                        }
                    ]
                }
            )
        if "selected_ids" in properties:
            return '{"selected_ids":["memory-1"]}'
        return "A clean spoken podcast draft."

    def stream_turn(
        self,
        *,
        model: str,
        reasoning_effort: str,
        developer_instructions: str,
        user_content: str,
        output_schema: dict[str, Any] | None = None,
    ) -> Iterator[str]:
        del output_schema
        self.calls.append(
            {
                "model": model,
                "reasoning_effort": reasoning_effort,
                "developer_instructions": developer_instructions,
                "user_content": user_content,
            }
        )
        yield "What changed "
        yield "your mind?"


class CodexSubscriptionProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeCodexClient()
        self.provider = CodexSubscriptionProvider(
            LLMProviderConfig(
                provider="codex_subscription",
                model="gpt-test",
                reasoning_effort="high",
            ),
            client=self.client,  # type: ignore[arg-type]
        )

    def test_generates_script_without_api_credentials(self) -> None:
        response = self.provider.generate_script(
            ScriptGenerationRequest(
                session_id="s1",
                topic="Reliable tools",
                creation_intent="Explain a lesson",
                transcript_text="User: boring tools win",
            )
        )

        self.assertEqual(response.draft, "A clean spoken podcast draft.")
        self.assertEqual(response.provider_name, "codex_subscription")
        self.assertEqual(response.model_name, "gpt-test")
        self.assertEqual(self.client.calls[0]["reasoning_effort"], "high")
        self.assertIn("Reliable tools", self.client.calls[0]["user_content"])

    def test_streams_interview_deltas(self) -> None:
        chunks = list(
            self.provider.stream_interview_question(
                InterviewQuestionRequest(
                    session_id="s1",
                    topic="A topic",
                    creation_intent="Explore it",
                    transcript_text="User: hello",
                    suggested_focus="example_or_detail",
                    missing_dimensions=["example_or_detail"],
                )
            )
        )

        self.assertEqual(chunks, ["What changed ", "your mind?"])

    def test_uses_output_schema_for_memory_extraction(self) -> None:
        response = self.provider.extract_memories(
            MemoryExtractionRequest(
                session_id="s1",
                topic="Examples",
                creation_intent="Remember a preference",
                user_turns=[{"turn_id": "t1", "content": "I prefer concrete examples"}],
            )
        )

        self.assertEqual(response.candidates[0]["type"], "preference")
        schema = self.client.calls[0]["output_schema"]
        self.assertIn("candidates", schema["properties"])

    def test_rerank_parses_selected_ids(self) -> None:
        response = self.provider.rerank_memories(
            MemoryRerankRequest(
                topic="Examples",
                creation_intent="Write a script",
                candidates=[{"id": "memory-1", "name": "Examples"}],
            )
        )
        self.assertEqual(response.selected_ids, ["memory-1"])


class CodexSubscriptionPreflightTests(unittest.TestCase):
    @staticmethod
    def _status(*, authenticated: bool) -> CodexProviderStatus:
        return CodexProviderStatus(
            installed=True,
            executable_path="/usr/local/bin/codex",
            version="codex-cli test",
            authenticated=authenticated,
            auth_mode="chatgpt" if authenticated else None,
            plan_type="plus" if authenticated else None,
            account_email="user@example.com" if authenticated else None,
            models=(
                CodexModelInfo(
                    id="gpt-test",
                    display_name="GPT Test",
                    is_default=True,
                    default_reasoning_effort="low",
                    supported_reasoning_efforts=("low",),
                ),
            ) if authenticated else (),
            rate_limit=None,
            message="Connected." if authenticated else "Sign in required.",
        )

    def test_ready_when_codex_is_authenticated(self) -> None:
        with patch(
            "app.providers.llm.codex_app_server.codex_provider_status",
            return_value=self._status(authenticated=True),
        ):
            result = check_llm_config(
                LLMProviderConfig(provider="codex_subscription", model="gpt-test")
            )
        self.assertTrue(result.ready)

    def test_requires_chatgpt_login(self) -> None:
        with patch(
            "app.providers.llm.codex_app_server.codex_provider_status",
            return_value=self._status(authenticated=False),
        ):
            result = check_llm_config(LLMProviderConfig(provider="codex_subscription"))
        self.assertFalse(result.ready)
        self.assertEqual(result.missing_fields, ("chatgpt_login",))

    def test_rejects_effort_not_supported_by_selected_model(self) -> None:
        with patch(
            "app.providers.llm.codex_app_server.codex_provider_status",
            return_value=self._status(authenticated=True),
        ):
            result = check_llm_config(
                LLMProviderConfig(
                    provider="codex_subscription",
                    model="gpt-test",
                    reasoning_effort="high",
                )
            )
        self.assertFalse(result.ready)
        self.assertEqual(result.missing_fields, ("reasoning_effort",))
        self.assertIn("not supported", result.message)


class CodexAccountModeTests(unittest.TestCase):
    def test_reasoning_effort_is_dynamic_and_auto_omits_override(self) -> None:
        client = CodexAppServerClient("/usr/bin/true")
        model = CodexModelInfo(
            id="gpt-test",
            display_name="GPT Test",
            is_default=True,
            default_reasoning_effort="low",
            supported_reasoning_efforts=("low", "high"),
        )
        try:
            with patch.object(client, "list_models", return_value=(model,)):
                self.assertIsNone(client.resolve_reasoning_effort("gpt-test", "auto"))
                self.assertEqual(client.resolve_reasoning_effort("gpt-test", "high"), "high")
                with self.assertRaises(CodexAppServerError):
                    client.resolve_reasoning_effort("gpt-test", "ultra")
        finally:
            client.close()

    def test_api_key_login_is_not_treated_as_subscription_auth(self) -> None:
        class ApiKeyClient(CodexAppServerClient):
            def read_account(self) -> dict[str, Any]:
                return {"account": {"type": "apiKey"}}

        client = ApiKeyClient("/usr/bin/true")
        try:
            status = client.status()
        finally:
            client.close()

        self.assertFalse(status.authenticated)
        self.assertIn("API-key billing", status.message)
        with self.assertRaises(CodexAppServerError):
            client.require_chatgpt_subscription()

    def test_login_rejects_non_openai_auth_url(self) -> None:
        class InvalidLoginClient(CodexAppServerClient):
            def _request(
                self,
                method: str,
                params: dict[str, Any] | None = None,
            ) -> dict[str, Any]:
                del method, params
                return {"loginId": "login-1", "authUrl": "https://example.com/phishing"}

        client = InvalidLoginClient("/usr/bin/true")
        try:
            with self.assertRaises(CodexAppServerError):
                client.start_chatgpt_login()
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()
