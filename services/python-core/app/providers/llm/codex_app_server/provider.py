from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Iterator

from app.domain.provider_config import LLMProviderConfig
from app.orchestration.prompts.registry import PromptPlan
from app.providers.llm.base import (
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
from app.providers.llm.codex_app_server.client import (
    PROVIDER_ID,
    CodexAppServerClient,
    get_codex_app_server_client,
)
from app.providers.llm.json_utils import parse_candidates, parse_json_object, parse_selected_ids


_STRING_ARRAY_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": {"type": "string"},
}

_SPEECH_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "position": {"type": "integer"},
                    "intent": {"type": "string"},
                    "emotion": {"type": "string"},
                    "energy": {"type": "number"},
                    "pace": {"type": "number"},
                    "pause_after_ms": {"type": "integer"},
                    "breaks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "after_text": {"type": "string"},
                                "duration_ms": {"type": "integer"},
                            },
                            "required": ["after_text", "duration_ms"],
                            "additionalProperties": False,
                        },
                    },
                    "emphasis": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "level": {
                                    "type": "string",
                                    "enum": ["light", "medium", "strong"],
                                },
                            },
                            "required": ["text", "level"],
                            "additionalProperties": False,
                        },
                    },
                    "pronunciations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                                "spoken_as": {"type": "string"},
                            },
                            "required": ["text", "spoken_as"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "position",
                    "intent",
                    "emotion",
                    "energy",
                    "pace",
                    "pause_after_ms",
                    "breaks",
                    "emphasis",
                    "pronunciations",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["segments"],
    "additionalProperties": False,
}

_MEMORY_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["profile", "experience", "viewpoint", "preference"],
                    },
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "body": {"type": "string"},
                    "keywords": _STRING_ARRAY_SCHEMA,
                    "sensitive": {"type": "boolean"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "turn_id": {"type": "string"},
                                "quote": {"type": "string"},
                            },
                            "required": ["turn_id", "quote"],
                            "additionalProperties": False,
                        },
                    },
                    "merge_target_id": {"type": "string"},
                },
                "required": [
                    "type",
                    "name",
                    "description",
                    "body",
                    "keywords",
                    "sensitive",
                    "evidence",
                    "merge_target_id",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}

_MEMORY_RERANK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"selected_ids": _STRING_ARRAY_SCHEMA},
    "required": ["selected_ids"],
    "additionalProperties": False,
}

_MEMORY_MERGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "primary_id": {"type": "string"},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "body": {"type": "string"},
        "keywords": _STRING_ARRAY_SCHEMA,
        "evidence_turn_ids": _STRING_ARRAY_SCHEMA,
        "drop_ids": _STRING_ARRAY_SCHEMA,
    },
    "required": [
        "primary_id",
        "name",
        "description",
        "body",
        "keywords",
        "evidence_turn_ids",
        "drop_ids",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class CodexSubscriptionProvider:
    config: LLMProviderConfig
    client: CodexAppServerClient | None = None

    def _client(self) -> CodexAppServerClient:
        return self.client or get_codex_app_server_client()

    def _model(self) -> str:
        return self._client().resolve_model(self.config.model)

    def _complete(
        self,
        plan: PromptPlan,
        output_schema: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        model = self._model()
        content = self._client().complete_turn(
            model=model,
            reasoning_effort=self.config.reasoning_effort,
            developer_instructions=plan.system,
            user_content=plan.user,
            output_schema=output_schema,
        )
        return content, model

    def generate_script(self, request: ScriptGenerationRequest) -> ScriptGenerationResponse:
        draft, model = self._complete(request.prompt_plan)
        return ScriptGenerationResponse(
            draft=draft,
            provider_name=PROVIDER_ID,
            model_name=model,
        )

    def generate_speech_plan(
        self,
        request: SpeechPlanGenerationRequest,
    ) -> SpeechPlanGenerationResponse:
        raw, model = self._complete(request.prompt_plan, _SPEECH_PLAN_SCHEMA)
        payload = parse_json_object(raw)
        directives = payload.get("segments")
        if not isinstance(directives, list):
            raise ValueError("Speech Director returned invalid JSON: expected a segments array.")
        return SpeechPlanGenerationResponse(
            directives=[item for item in directives if isinstance(item, dict)],
            provider_name=PROVIDER_ID,
            model_name=model,
        )

    def stream_interview_question(self, request: InterviewQuestionRequest) -> Iterator[str]:
        model = self._model()
        yield from self._client().stream_turn(
            model=model,
            reasoning_effort=self.config.reasoning_effort,
            developer_instructions=request.prompt_plan.system,
            user_content=request.prompt_plan.user,
            image_urls=tuple(
                f"data:{image.mime_type};base64,{base64.b64encode(image.data).decode('ascii')}"
                for image in request.images
            ),
        )

    def extract_memories(self, request: MemoryExtractionRequest) -> MemoryExtractionResponse:
        raw, model = self._complete(request.prompt_plan, _MEMORY_EXTRACTION_SCHEMA)
        return MemoryExtractionResponse(
            candidates=parse_candidates(raw),
            provider_name=PROVIDER_ID,
            model_name=model,
        )

    def rerank_memories(self, request: MemoryRerankRequest) -> MemoryRerankResponse:
        raw, model = self._complete(request.prompt_plan, _MEMORY_RERANK_SCHEMA)
        return MemoryRerankResponse(
            selected_ids=parse_selected_ids(raw),
            provider_name=PROVIDER_ID,
            model_name=model,
        )

    def merge_memories(self, request: MemoryMergeRequest) -> MemoryMergeResponse:
        raw, model = self._complete(request.prompt_plan, _MEMORY_MERGE_SCHEMA)
        payload = parse_json_object(raw)
        return MemoryMergeResponse(
            primary_id=str(payload.get("primary_id") or ""),
            name=str(payload.get("name") or ""),
            description=str(payload.get("description") or ""),
            body=str(payload.get("body") or ""),
            keywords=[str(item) for item in payload.get("keywords", []) if isinstance(item, str)],
            evidence_turn_ids=[
                str(item)
                for item in payload.get("evidence_turn_ids", [])
                if isinstance(item, str)
            ],
            drop_ids=[str(item) for item in payload.get("drop_ids", []) if isinstance(item, str)],
            provider_name=PROVIDER_ID,
            model_name=model,
        )
