from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

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

_MEMORY_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["remember", "correct", "forget_candidates", "none"],
        },
        "subject": {"type": "string"},
    },
    "required": ["action", "subject"],
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
        *,
        system_content: str,
        user_content: str,
        output_schema: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        model = self._model()
        content = self._client().complete_turn(
            model=model,
            reasoning_effort=self.config.reasoning_effort,
            developer_instructions=system_content,
            user_content=user_content,
            output_schema=output_schema,
        )
        return content, model

    def generate_script(self, request: ScriptGenerationRequest) -> ScriptGenerationResponse:
        if request.prompt_plan is not None:
            system_content = request.prompt_plan.system
            user_content = request.prompt_plan.user
        else:
            system_content = SCRIPT_GENERATION_SYSTEM_PROMPT
            user_content = build_script_generation_user_prompt(
                topic=request.topic,
                creation_intent=request.creation_intent,
                transcript_text=request.transcript_text,
                memory_context=request.memory_context,
            )
        draft, model = self._complete(
            system_content=system_content,
            user_content=user_content,
        )
        return ScriptGenerationResponse(
            draft=draft,
            provider_name=PROVIDER_ID,
            model_name=model,
        )

    def generate_speech_plan(
        self,
        request: SpeechPlanGenerationRequest,
    ) -> SpeechPlanGenerationResponse:
        raw, model = self._complete(
            system_content=request.prompt_plan.system,
            user_content=request.prompt_plan.user,
            output_schema=_SPEECH_PLAN_SCHEMA,
        )
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
        model = self._model()
        yield from self._client().stream_turn(
            model=model,
            reasoning_effort=self.config.reasoning_effort,
            developer_instructions=system_content,
            user_content=user_content,
        )

    def extract_memories(self, request: MemoryExtractionRequest) -> MemoryExtractionResponse:
        if request.prompt_plan is not None:
            system_content = request.prompt_plan.system
            user_content = request.prompt_plan.user
        else:
            system_content = MEMORY_EXTRACTION_SYSTEM_PROMPT
            user_content = build_memory_extraction_user_content(
                topic=request.topic,
                creation_intent=request.creation_intent,
                user_turns=list(request.user_turns),
                existing_candidates=list(request.existing_candidates),
                explicit_intent=request.explicit_intent,
            )
        raw, model = self._complete(
            system_content=system_content,
            user_content=user_content,
            output_schema=_MEMORY_EXTRACTION_SCHEMA,
        )
        return MemoryExtractionResponse(
            candidates=parse_candidates(raw),
            provider_name=PROVIDER_ID,
            model_name=model,
        )

    def rerank_memories(self, request: MemoryRerankRequest) -> MemoryRerankResponse:
        if request.prompt_plan is not None:
            system_content = request.prompt_plan.system
            user_content = request.prompt_plan.user
        else:
            system_content = MEMORY_RERANK_SYSTEM_PROMPT
            user_content = build_memory_rerank_user_content(
                topic=request.topic,
                creation_intent=request.creation_intent,
                candidates=list(request.candidates),
                max_select=request.max_select,
            )
        raw, model = self._complete(
            system_content=system_content,
            user_content=user_content,
            output_schema=_MEMORY_RERANK_SCHEMA,
        )
        return MemoryRerankResponse(
            selected_ids=parse_selected_ids(raw),
            provider_name=PROVIDER_ID,
            model_name=model,
        )

    def merge_memories(self, request: MemoryMergeRequest) -> MemoryMergeResponse:
        if request.prompt_plan is not None:
            system_content = request.prompt_plan.system
            user_content = request.prompt_plan.user
        else:
            system_content = MEMORY_MAINTENANCE_SYSTEM_PROMPT
            user_content = build_memory_maintenance_user_content(entries=list(request.entries))
        raw, model = self._complete(
            system_content=system_content,
            user_content=user_content,
            output_schema=_MEMORY_MERGE_SCHEMA,
        )
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

    def classify_memory_action(self, request: MemoryActionRequest) -> MemoryActionResponse:
        fallback = MemoryActionResponse(
            action="none",
            subject="",
            provider_name=PROVIDER_ID,
            model_name=self.config.model,
        )
        if request.prompt_plan is not None:
            system_content = request.prompt_plan.system
            user_content = request.prompt_plan.user
        else:
            system_content = _MEMORY_ACTION_SYSTEM
            user_content = build_memory_action_classification_prompt(
                request.user_message,
                request.candidate_names,
            )
        try:
            raw, model = self._complete(
                system_content=system_content,
                user_content=user_content,
                output_schema=_MEMORY_ACTION_SCHEMA,
            )
        except Exception:
            return fallback
        payload = parse_json_object(raw)
        action = str(payload.get("action") or "none")
        if action not in {"remember", "correct", "forget_candidates", "none"}:
            action = "none"
        return MemoryActionResponse(
            action=action,  # type: ignore[arg-type]
            subject=str(payload.get("subject") or "").strip(),
            provider_name=PROVIDER_ID,
            model_name=model,
        )
