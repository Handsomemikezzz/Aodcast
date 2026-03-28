from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib import request as urllib_request

from app.domain.provider_config import LLMProviderConfig
from app.providers.llm.base import ScriptGenerationRequest, ScriptGenerationResponse


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProvider:
    config: LLMProviderConfig

    def generate_script(self, request: ScriptGenerationRequest) -> ScriptGenerationResponse:
        if not self.config.base_url:
            raise ValueError("OpenAI-compatible provider requires a base_url.")
        if not self.config.model:
            raise ValueError("OpenAI-compatible provider requires a model.")
        if not self.config.api_key_env:
            raise ValueError("OpenAI-compatible provider requires an api_key_env.")

        api_key = os.getenv(self.config.api_key_env, "")
        if not api_key:
            raise ValueError(
                f"Environment variable '{self.config.api_key_env}' is required for the configured LLM provider."
            )

        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a podcast script writer. Produce a solo monologue script with "
                        "an opening, a coherent body, and a conclusion."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Topic: {request.topic}\n"
                        f"Intent: {request.creation_intent}\n"
                        f"Transcript:\n{request.transcript_text}"
                    ),
                },
            ],
        }
        req = urllib_request.Request(
            url=self.config.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))

        draft = body["choices"][0]["message"]["content"].strip()
        return ScriptGenerationResponse(
            draft=draft,
            provider_name=self.config.provider,
            model_name=self.config.model,
        )
