from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from openai import OpenAI

from app.domain.provider_config import LLMProviderConfig
from app.orchestration.prompts import (
    INTERVIEW_STREAM_SYSTEM_PROMPT,
    SCRIPT_GENERATION_SYSTEM_PROMPT,
    build_interview_stream_user_content,
    build_script_generation_user_prompt,
)
from app.providers.llm.base import (
    InterviewQuestionRequest,
    ScriptGenerationRequest,
    ScriptGenerationResponse,
)


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProvider:
    config: LLMProviderConfig

    def generate_script(self, request: ScriptGenerationRequest) -> ScriptGenerationResponse:
        if not self.config.base_url:
            raise ValueError("OpenAI-compatible provider requires a base_url.")
        if not self.config.model:
            raise ValueError("OpenAI-compatible provider requires a model.")
        if not self.config.api_key:
            raise ValueError("OpenAI-compatible provider requires an api_key.")

        client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {
                    "role": "system",
                    "content": SCRIPT_GENERATION_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": build_script_generation_user_prompt(
                        topic=request.topic,
                        creation_intent=request.creation_intent,
                        transcript_text=request.transcript_text,
                    ),
                },
            ],
            stream=True,
        )

        draft = "".join(
            chunk.choices[0].delta.content
            for chunk in response
            if chunk.choices and chunk.choices[0].delta.content
        ).strip()
        return ScriptGenerationResponse(
            draft=draft,
            provider_name=self.config.provider,
            model_name=self.config.model,
        )

    def stream_interview_question(self, request: InterviewQuestionRequest) -> Iterator[str]:
        if not self.config.base_url:
            raise ValueError("OpenAI-compatible provider requires a base_url.")
        if not self.config.model:
            raise ValueError("OpenAI-compatible provider requires a model.")
        if not self.config.api_key:
            raise ValueError("OpenAI-compatible provider requires an api_key.")

        user_content = build_interview_stream_user_content(
            topic=request.topic,
            creation_intent=request.creation_intent,
            missing_dimensions=list(request.missing_dimensions),
            transcript_text=request.transcript_text,
            script_exists=request.script_exists,
            suggested_focus=request.suggested_focus,
        )
        client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": INTERVIEW_STREAM_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            stream=True,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
