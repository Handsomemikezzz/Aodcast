from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from openai import OpenAI

from app.domain.provider_config import LLMProviderConfig
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
            "Respond as a reflective interview partner in the same language as the user. "
            "Your reply must have three parts in this order:\n"
            "1) Brief understanding summary (2-4 sentences) of the user's latest point.\n"
            "2) Your analysis/viewpoint (2-4 sentences) that highlights tensions, assumptions, "
            "or hidden motivations grounded in the transcript.\n"
            "3) End with 2-3 gentle, companion-style follow-up questions that help the user "
            "uncover their deeper true view.\n"
            "Questions should feel warm and invitational, not interrogative: avoid rapid-fire "
            "cross-examination tone, and allow reflective space in wording.\n"
            "Keep the response focused, concrete, and non-generic. Do not write a podcast script."
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
                        "You are The Archivist, a perceptive conversation partner for deep "
                        "self-exploration. In each turn, first demonstrate understanding, then "
                        "offer your own thoughtful analysis, and finally ask 2-3 progressive "
                        "questions that invite deeper introspection. Use a warm, companion-like "
                        "tone with emotional safety; avoid sounding like an interrogation. Keep "
                        "everything tightly grounded in the user's context and avoid generic advice."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            stream=True,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
