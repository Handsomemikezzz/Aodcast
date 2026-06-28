from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterator

from openai import OpenAI

from app.domain.provider_config import LLMProviderConfig
from app.orchestration.prompts import (
    INTERVIEW_STREAM_SYSTEM_PROMPT,
    MEMORY_EXTRACTION_SYSTEM_PROMPT,
    MEMORY_MAINTENANCE_SYSTEM_PROMPT,
    MEMORY_RERANK_SYSTEM_PROMPT,
    SCRIPT_GENERATION_SYSTEM_PROMPT,
    _MEMORY_ACTION_SYSTEM,
    build_interview_stream_user_content,
    build_memory_action_classification_prompt,
    build_memory_extraction_user_content,
    build_memory_maintenance_user_content,
    build_memory_rerank_user_content,
    build_script_generation_user_prompt,
)
from app.providers.llm.base import (
    InterviewQuestionRequest,
    MemoryActionRequest,
    MemoryActionResponse,
    MemoryExtractionRequest,
    MemoryExtractionResponse,
    MemoryMergeRequest,
    MemoryMergeResponse,
    MemoryRerankRequest,
    MemoryRerankResponse,
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
                        memory_context=request.memory_context,
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

        # Prefer the orchestration-assembled PromptPlan when supplied; otherwise
        # fall back to the legacy string builders for backward compatibility.
        if request.prompt_plan is not None:
            system_content = request.prompt_plan.system
            user_content = request.prompt_plan.user
        else:
            system_content = INTERVIEW_STREAM_SYSTEM_PROMPT
            user_content = build_interview_stream_user_content(
                topic=request.topic,
                creation_intent=request.creation_intent,
                missing_dimensions=list(request.missing_dimensions),
                transcript_text=request.transcript_text,
                script_exists=request.script_exists,
                suggested_focus=request.suggested_focus,
                memory_context=request.memory_context,
            )

        client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            stream=True,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def extract_memories(self, request: MemoryExtractionRequest) -> MemoryExtractionResponse:
        if not self.config.base_url:
            raise ValueError("OpenAI-compatible provider requires a base_url.")
        if not self.config.model:
            raise ValueError("OpenAI-compatible provider requires a model.")
        if not self.config.api_key:
            raise ValueError("OpenAI-compatible provider requires an api_key.")

        user_content = build_memory_extraction_user_content(
            topic=request.topic,
            creation_intent=request.creation_intent,
            user_turns=list(request.user_turns),
            existing_candidates=list(request.existing_candidates),
            explicit_intent=request.explicit_intent,
        )
        client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": MEMORY_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            stream=False,
        )
        content = ""
        if response.choices and response.choices[0].message:
            content = response.choices[0].message.content or ""
        candidates = _parse_candidates(content)
        return MemoryExtractionResponse(
            candidates=candidates,
            provider_name=self.config.provider,
            model_name=self.config.model,
        )

    def rerank_memories(self, request: MemoryRerankRequest) -> MemoryRerankResponse:
        if not self.config.base_url or not self.config.model or not self.config.api_key:
            raise ValueError("OpenAI-compatible provider requires base_url, model, and api_key.")
        client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": MEMORY_RERANK_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_memory_rerank_user_content(
                        topic=request.topic,
                        creation_intent=request.creation_intent,
                        candidates=list(request.candidates),
                        max_select=request.max_select,
                    ),
                },
            ],
            temperature=0,
            stream=False,
        )
        content = ""
        if response.choices and response.choices[0].message:
            content = response.choices[0].message.content or ""
        return MemoryRerankResponse(
            selected_ids=_parse_selected_ids(content),
            provider_name=self.config.provider,
            model_name=self.config.model,
        )

    def merge_memories(self, request: MemoryMergeRequest) -> MemoryMergeResponse:
        if not self.config.base_url or not self.config.model or not self.config.api_key:
            raise ValueError("OpenAI-compatible provider requires base_url, model, and api_key.")
        client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": MEMORY_MAINTENANCE_SYSTEM_PROMPT},
                {"role": "user", "content": build_memory_maintenance_user_content(entries=list(request.entries))},
            ],
            temperature=0,
            stream=False,
        )
        content = ""
        if response.choices and response.choices[0].message:
            content = response.choices[0].message.content or ""
        payload = _parse_object(content)
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

    def classify_memory_action(self, request: MemoryActionRequest) -> MemoryActionResponse:
        """§10.5: Lightweight non-streaming classification of user memory intent."""
        _VALID_ACTIONS = {"remember", "correct", "forget_candidates", "none"}
        _FALLBACK = MemoryActionResponse(
            action="none", subject="", provider_name=self.config.provider, model_name=self.config.model
        )
        if not self.config.base_url or not self.config.model or not self.config.api_key:
            return _FALLBACK
        client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)
        user_content = build_memory_action_classification_prompt(
            request.user_message, request.candidate_names
        )
        try:
            response = client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": _MEMORY_ACTION_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
                max_tokens=100,
            )
        except Exception:
            return _FALLBACK
        raw = (response.choices[0].message.content or "").strip() if response.choices else ""
        payload = _parse_object(raw)
        action = str(payload.get("action") or "none").strip()
        if action not in _VALID_ACTIONS:
            action = "none"
        subject = str(payload.get("subject") or "").strip()
        return MemoryActionResponse(
            action=action,  # type: ignore[arg-type]
            subject=subject,
            provider_name=self.config.provider,
            model_name=self.config.model,
        )


def _parse_candidates(content: str) -> list[dict[str, Any]]:
    text = content.strip()
    if not text:
        return []
    # Tolerate fenced JSON or leading/trailing prose around the object.
    if "```" in text:
        fence = text.split("```")
        for segment in fence:
            segment = segment.strip()
            if segment.startswith("json"):
                segment = segment[len("json"):].strip()
            if segment.startswith("{"):
                text = segment
                break
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    candidates = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, dict)]


def _parse_selected_ids(content: str) -> list[str]:
    text = content.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    selected = payload.get("selected_ids") if isinstance(payload, dict) else None
    if not isinstance(selected, list):
        return []
    return [str(item) for item in selected if isinstance(item, (str, int))]


def _parse_object(content: str) -> dict[str, Any]:
    text = content.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
