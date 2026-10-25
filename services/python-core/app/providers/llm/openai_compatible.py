from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Iterator

from openai import OpenAI

from app.domain.provider_config import LLMProviderConfig
from app.orchestration.prompts.registry import PromptPlan
from app.providers.llm.base import (
    ImageInput,
    InterviewQuestionRequest,
    MemoryExtractionRequest,
    MemoryExtractionResponse,
    MemoryMergeRequest,
    MemoryMergeResponse,
    MemoryRerankRequest,
    MemoryRerankResponse,
    ScriptGenerationRequest,
    ScriptGenerationResponse,
    SpeechPlanGenerationRequest,
    SpeechPlanGenerationResponse,
)
from app.providers.llm.json_utils import parse_candidates, parse_json_object, parse_selected_ids


def _user_message_content(text: str, images: tuple[ImageInput, ...]) -> str | list[dict[str, Any]]:
    """Chat Completions multimodal content: text first, then images as base64 data URLs."""
    if not images:
        return text
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for image in images:
        encoded = base64.b64encode(image.data).decode("ascii")
        parts.append(
            {"type": "image_url", "image_url": {"url": f"data:{image.mime_type};base64,{encoded}"}}
        )
    return parts


def _messages(plan: PromptPlan) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": plan.system},
        {"role": "user", "content": plan.user},
    ]


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProvider:
    config: LLMProviderConfig

    def _client(self) -> OpenAI:
        if not self.config.base_url:
            raise ValueError("OpenAI-compatible provider requires a base_url.")
        if not self.config.model:
            raise ValueError("OpenAI-compatible provider requires a model.")
        if not self.config.api_key:
            raise ValueError("OpenAI-compatible provider requires an api_key.")
        return OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)

    def _complete_json(self, plan: PromptPlan) -> str:
        response = self._client().chat.completions.create(
            model=self.config.model,
            messages=_messages(plan),
            temperature=0,
            stream=False,
        )
        if response.choices and response.choices[0].message:
            return response.choices[0].message.content or ""
        return ""

    def generate_script(self, request: ScriptGenerationRequest) -> ScriptGenerationResponse:
        response = self._client().chat.completions.create(
            model=self.config.model,
            messages=_messages(request.prompt_plan),
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

    def generate_speech_plan(self, request: SpeechPlanGenerationRequest) -> SpeechPlanGenerationResponse:
        payload = parse_json_object(self._complete_json(request.prompt_plan))
        directives = payload.get("segments") if isinstance(payload, dict) else None
        if not isinstance(directives, list):
            raise ValueError("Speech Director returned invalid JSON: expected a segments array.")
        return SpeechPlanGenerationResponse(
            directives=[item for item in directives if isinstance(item, dict)],
            provider_name=self.config.provider,
            model_name=self.config.model,
        )

    def stream_interview_question(self, request: InterviewQuestionRequest) -> Iterator[str]:
        client = self._client()
        # Endpoints or models without vision reject image parts with an API
        # error; that error surfaces to the user instead of dropping the images.
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": request.prompt_plan.system},
                {"role": "user", "content": _user_message_content(request.prompt_plan.user, request.images)},
            ],
            stream=True,
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def extract_memories(self, request: MemoryExtractionRequest) -> MemoryExtractionResponse:
        return MemoryExtractionResponse(
            candidates=parse_candidates(self._complete_json(request.prompt_plan)),
            provider_name=self.config.provider,
            model_name=self.config.model,
        )

    def rerank_memories(self, request: MemoryRerankRequest) -> MemoryRerankResponse:
        return MemoryRerankResponse(
            selected_ids=parse_selected_ids(self._complete_json(request.prompt_plan)),
            provider_name=self.config.provider,
            model_name=self.config.model,
        )

    def merge_memories(self, request: MemoryMergeRequest) -> MemoryMergeResponse:
        payload = parse_json_object(self._complete_json(request.prompt_plan))
        return MemoryMergeResponse(
            primary_id=str(payload.get("primary_id") or ""),
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            body=str(payload.get("body") or ""),
            keywords=[str(k) for k in (payload.get("keywords") or []) if isinstance(k, (str, int))],
            evidence_turn_ids=[str(t) for t in (payload.get("evidence_turn_ids") or []) if isinstance(t, (str, int))],
            drop_ids=[str(d) for d in (payload.get("drop_ids") or []) if isinstance(d, (str, int))],
            provider_name=self.config.provider,
            model_name=self.config.model,
        )
