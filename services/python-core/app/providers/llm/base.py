from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, Iterator

if TYPE_CHECKING:
    from app.orchestration.prompts.registry import PromptPlan


@dataclass(frozen=True, slots=True)
class ScriptGenerationRequest:
    session_id: str
    topic: str
    creation_intent: str
    transcript_text: str
    prompt_plan: "PromptPlan"
    source_text: str = ""
    memory_context: str = ""


@dataclass(frozen=True, slots=True)
class ScriptGenerationResponse:
    draft: str
    provider_name: str
    model_name: str


@dataclass(frozen=True, slots=True)
class SpeechPlanGenerationRequest:
    session_id: str
    script_id: str
    script_text: str
    segments: list[dict[str, Any]]
    prompt_plan: "PromptPlan"


@dataclass(frozen=True, slots=True)
class SpeechPlanGenerationResponse:
    directives: list[dict[str, Any]]
    provider_name: str
    model_name: str


@dataclass(frozen=True, slots=True)
class ImageInput:
    """One user-attached image. Providers that cannot accept image input must raise."""

    name: str
    mime_type: str
    data: bytes


@dataclass(frozen=True, slots=True)
class InterviewQuestionRequest:
    session_id: str
    topic: str
    creation_intent: str
    suggested_focus: str
    prompt_plan: "PromptPlan"
    script_exists: bool = False
    # Images from user turns, oldest first. Document attachments arrive as
    # extracted text inside the prompt plan instead.
    images: tuple[ImageInput, ...] = ()


@dataclass(frozen=True, slots=True)
class MemoryExtractionRequest:
    """Inputs for one memory-extraction batch.

    Only user turns may be sources. `user_turns` is a list of
    {"turn_id", "content"}; the prompt plan carries existing-entry hints.
    """

    session_id: str
    topic: str
    creation_intent: str
    user_turns: list[dict[str, str]]
    prompt_plan: "PromptPlan"


@dataclass(frozen=True, slots=True)
class MemoryExtractionResponse:
    candidates: list[dict[str, Any]]
    provider_name: str
    model_name: str


@dataclass(frozen=True, slots=True)
class MemoryRerankRequest:
    """Inputs for the script-stage semantic re-filter (§13.4).

    `candidates` carries only id/type/name/description (sensitive entries use a
    generalized description), never bodies — sensitive bodies must not reach the
    model during reranking.
    """

    topic: str
    creation_intent: str
    candidates: list[dict[str, str]]
    prompt_plan: "PromptPlan"
    max_select: int = 5


@dataclass(frozen=True, slots=True)
class MemoryRerankResponse:
    selected_ids: list[str]
    provider_name: str
    model_name: str


@dataclass(frozen=True, slots=True)
class MemoryMergeRequest:
    """One candidate group to consolidate during maintenance (§17.5).

    `entries` carries id/type/name/description/body/keywords/evidence so the
    model can merge semantic duplicates using only existing evidence.
    """

    entries: list[dict[str, Any]]
    prompt_plan: "PromptPlan"


@dataclass(frozen=True, slots=True)
class MemoryMergeResponse:
    primary_id: str
    name: str
    description: str
    body: str
    keywords: list[str]
    evidence_turn_ids: list[str]
    drop_ids: list[str]
    provider_name: str
    model_name: str


class LLMProvider(Protocol):
    def generate_script(self, request: ScriptGenerationRequest) -> ScriptGenerationResponse:
        """Generate a script draft from interview transcript text."""

    def generate_speech_plan(self, request: SpeechPlanGenerationRequest) -> SpeechPlanGenerationResponse:
        """Plan delivery controls without changing the supplied script text."""

    def stream_interview_question(self, request: InterviewQuestionRequest) -> Iterator[str]:
        """Produce the next interview follow-up question transcript context as a stream of chunks."""

    def extract_memories(self, request: MemoryExtractionRequest) -> MemoryExtractionResponse:
        """Propose long-term memory candidates from user turns (structured JSON)."""

    def rerank_memories(self, request: MemoryRerankRequest) -> MemoryRerankResponse:
        """Select the most relevant memory candidates for the current script (structured JSON)."""

    def merge_memories(self, request: MemoryMergeRequest) -> MemoryMergeResponse:
        """Consolidate a candidate group of duplicate memories (structured JSON)."""
