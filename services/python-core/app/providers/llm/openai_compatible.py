from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterator

from openai import OpenAI

from app.domain.provider_config import LLMProviderConfig
from app.providers.llm.base import (
    InterviewQuestionRequest,
    InterviewQuestionResponse,
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
            stream=False,
        )

        draft = response.choices[0].message.content.strip()
        return ScriptGenerationResponse(
            draft=draft,
            provider_name=self.config.provider,
            model_name=self.config.model,
        )

    def generate_interview_question(
        self, request: InterviewQuestionRequest
    ) -> InterviewQuestionResponse:
        if not self.config.base_url:
            raise ValueError("OpenAI-compatible provider requires a base_url.")
        if not self.config.model:
            raise ValueError("OpenAI-compatible provider requires a model.")
        if not self.config.api_key:
            raise ValueError("OpenAI-compatible provider requires an api_key.")

        missing = ", ".join(request.missing_dimensions) or "(none)"
        transcript_block = request.transcript_text.strip() or (
            "(No messages yet — produce a short opening question for the guest.)"
        )
        user_content = (
            f"Session topic: {request.topic}\n"
            f"Creation intent: {request.creation_intent}\n"
            f"Priority dimension to explore next: {request.suggested_focus}\n"
            f"Still missing (for a complete solo episode): {missing}\n\n"
            f"Transcript so far:\n{transcript_block}\n\n"
            "Reply with exactly one concise follow-up question (one or two sentences). "
            "No bullets, no greeting, no role-play labels — only the question."
        )
        client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a skilled podcast interviewer preparing a solo episode. "
                        "Ask one sharp, specific follow-up that helps the guest deepen the story "
                        "or clarify their viewpoint. Stay on topic; do not write a script."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            stream=False,
        )

        question = response.choices[0].message.content.strip()
        return InterviewQuestionResponse(
            question=question,
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

        missing = ", ".join(request.missing_dimensions) or "(none)"
        transcript_block = request.transcript_text.strip() or (
            "(No messages yet — produce a short opening question for the guest.)"
        )
        user_content = (
            f"Session topic: {request.topic}\n"
            f"Creation intent: {request.creation_intent}\n"
            f"Priority dimension to explore next: {request.suggested_focus}\n"
            f"Still missing (for a complete solo episode): {missing}\n\n"
            f"Transcript so far:\n{transcript_block}\n\n"
            "Reply with exactly one concise follow-up question (one or two sentences). "
            "No bullets, no greeting, no role-play labels — only the question."
        )
        client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a skilled podcast interviewer preparing a solo episode. "
                        "Ask one sharp, specific follow-up that helps the guest deepen the story "
                        "or clarify their viewpoint. Stay on topic; do not write a script."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            stream=True,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
