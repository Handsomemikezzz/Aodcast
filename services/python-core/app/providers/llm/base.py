from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, Iterator

if TYPE_CHECKING:
    from app.orchestration.prompts.registry import PromptPlan


@dataclass(frozen=True, slots=True)
class ScriptGenerationRequest:
    session_id: str
    topic: str
    creation_intent: str
    transcript_text: str
    memory_context: str = ""
    # When present, providers must use plan.system / plan.user instead of the
    # legacy string builders. Enables PromptPlan-driven script generation.
    prompt_plan: "PromptPlan | None" = None


@dataclass(frozen=True, slots=True)
class ScriptGenerationResponse:
    draft: str
    provider_name: str
    model_name: str


@dataclass(frozen=True, slots=True)
class InterviewQuestionRequest:
    session_id: str
    topic: str
    creation_intent: str
    transcript_text: str
    suggested_focus: str
    missing_dimensions: list[str]
    script_exists: bool = False
    memory_context: str = ""
    # When present, providers must use plan.system / plan.user instead of
    # building the prompt from individual fields. Allows orchestration-layer
    # PromptPlan assembly without breaking existing provider call sites.
    prompt_plan: "PromptPlan | None" = None


@dataclass(frozen=True, slots=True)
class MemoryExtractionRequest:
    """Inputs for one memory-extraction batch.

    Only user turns may be sources. `user_turns` is a list of
    {"turn_id", "content"}; `existing_candidates` carries name/description/type
    of current entries so the model can prefer merging over fragmenting.
    """

    session_id: str
    topic: str
    creation_intent: str
    user_turns: list[dict[str, str]]
    existing_candidates: list[dict[str, str]] = field(default_factory=list)
    explicit_intent: str = ""


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


@dataclass(frozen=True, slots=True)
class MemoryActionRequest:
    """§10.5: Lightweight classification to detect memory control intent.

    `candidate_names` is a snapshot of existing memory entry names so the model
    can reference them when signalling correction or forgetting. Only names, never
    bodies or sensitive content, are sent to the classifier.
    """

    user_message: str
    candidate_names: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MemoryActionResponse:
    """§10.5: Structured control signal returned by the classifier.

    - `remember`         : user explicitly wants to save something
    - `correct`          : user is correcting a previous memory
    - `forget_candidates`: user wants to delete a past memory (subject extracted)
    - `none`             : no memory action implied
    `subject` carries the topic the user mentioned (used to seed candidate search).
    """

    action: Literal["remember", "correct", "forget_candidates", "none"]
    subject: str
    provider_name: str
    model_name: str


class LLMProvider(Protocol):
    def generate_script(self, request: ScriptGenerationRequest) -> ScriptGenerationResponse:
        """Generate a script draft from interview transcript text."""

    def stream_interview_question(self, request: InterviewQuestionRequest) -> Iterator[str]:
        """Produce the next interview follow-up question transcript context as a stream of chunks."""

    def extract_memories(self, request: MemoryExtractionRequest) -> MemoryExtractionResponse:
        """Propose long-term memory candidates from user turns (structured JSON)."""

    def rerank_memories(self, request: MemoryRerankRequest) -> MemoryRerankResponse:
        """Select the most relevant memory candidates for the current script (structured JSON)."""

    def merge_memories(self, request: MemoryMergeRequest) -> MemoryMergeResponse:
        """Consolidate a candidate group of duplicate memories (structured JSON)."""

    def classify_memory_action(self, request: MemoryActionRequest) -> MemoryActionResponse:
        """§10.5: Classify the user message for memory control intent (structured JSON).

        Providers that cannot reliably produce structured JSON must return
        MemoryActionResponse(action="none", subject="", ...).  The caller treats
        any exception as a `none` result and falls back to deterministic rules.
        """
