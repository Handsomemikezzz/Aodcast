from __future__ import annotations

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
from typing import Iterator
import re
import time


def _mock_tokens(text: str) -> list[str]:
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9]{2,}", lowered)
    cjk = re.findall(r"[㐀-鿿]{2,}", lowered)
    bigrams: list[str] = []
    for run in cjk:
        bigrams.extend(run[i : i + 2] for i in range(len(run) - 1))
    return [*latin, *bigrams]


_PREFERENCE_TRIGGERS = ("喜欢", "不喜欢", "prefer", "以后", "口吻", "风格")
_VIEWPOINT_TRIGGERS = ("觉得", "认为", "believe", "观点", "立场")
_PROFILE_TRIGGERS = ("我是", "背景", "职业", "工作", "i am", "my job")


class MockLLMProvider:
    provider_name = "mock"
    model_name = "mock-solo-writer"

    def generate_script(self, request: ScriptGenerationRequest) -> ScriptGenerationResponse:
        transcript_lines = [
            line.strip()
            for line in request.transcript_text.splitlines()
            if line.strip()
        ]
        supporting_detail = transcript_lines[-1] if transcript_lines else "The interview transcript is still sparse."
        opening = (
            f"Today I want to talk about {request.topic.lower()} and why it matters right now."
        )
        body = (
            f"My core intent for this episode is: {request.creation_intent}. "
            f"One useful detail from the interview is: {supporting_detail}"
        )
        closing = (
            "If there is one takeaway from this conversation, it is that good tools "
            "should make complex work more understandable and recoverable."
        )
        parts = [opening, body, closing]
        if request.memory_context.strip():
            # Surface that memory shaped this draft so callers/tests can observe it.
            parts.append(f"[memory-informed]\n{request.memory_context.strip()}")
        draft = "\n\n".join(parts)
        return ScriptGenerationResponse(
            draft=draft,
            provider_name=self.provider_name,
            model_name=self.model_name,
        )

    def _build_interview_question(self, request: InterviewQuestionRequest) -> str:
        if request.script_exists:
            reflection = (
                f"[mock interviewer] That addition will help shape a new script version for '{request.topic}'."
            )
            question = "What would you like to expand next for this revised episode?"
            options = (
                "A. Add a new concrete example\n"
                "B. Adjust the core argument\n"
                "C. Explain how you want this version to differ from the previous script"
            )
            recommendation = "I suggest starting with A, as fresh examples often sharpen the new draft. "
        else:
            focus = request.suggested_focus
            reflection = f"[mock interviewer] I hear you on '{request.topic}'."
            question = f"Let's focus on exploring your {focus} next."
            options = (
                f"A. Share a concrete detail or story about {focus}\n"
                f"B. Tell me how {focus} shapes your viewpoint\n"
                f"C. Focus on the final takeaway regarding {focus}"
            )
            recommendation = "I suggest starting with A, as a concrete example will ground the topic. "
        ignore_msg = "Of course, feel free to ignore these options and answer in your own way."

        return f"{reflection} {question}\n\n{options}\n\n{recommendation}{ignore_msg}"

    def stream_interview_question(self, request: InterviewQuestionRequest) -> Iterator[str]:
        full_response = self._build_interview_question(request)
        for word in full_response.split(" "):
            yield word + " "
            time.sleep(0.05)

    def extract_memories(self, request: MemoryExtractionRequest) -> MemoryExtractionResponse:
        """Deterministic heuristic extraction (no network).

        Produces at most one candidate from the first user turn that contains a
        recognizable preference/viewpoint/profile trigger, quoting that turn
        verbatim so server-side evidence validation passes.
        """
        candidates: list[dict[str, object]] = []
        for turn in request.user_turns:
            content = (turn.get("content") or "").strip()
            turn_id = turn.get("turn_id") or ""
            if not content or not turn_id:
                continue
            lowered = content.lower()
            if any(trigger in content or trigger in lowered for trigger in _PREFERENCE_TRIGGERS):
                memory_type = "preference"
            elif any(trigger in content or trigger in lowered for trigger in _VIEWPOINT_TRIGGERS):
                memory_type = "viewpoint"
            elif any(trigger in content or trigger in lowered for trigger in _PROFILE_TRIGGERS):
                memory_type = "profile"
            else:
                continue
            candidates.append(
                {
                    "type": memory_type,
                    "name": content[:24],
                    "description": content[:60],
                    "body": content,
                    "keywords": [],
                    "sensitive": False,
                    "evidence": [{"turn_id": turn_id, "quote": content}],
                    "merge_target_id": "",
                }
            )
            break
        return MemoryExtractionResponse(
            candidates=candidates,
            provider_name=self.provider_name,
            model_name=self.model_name,
        )

    def rerank_memories(self, request: MemoryRerankRequest) -> MemoryRerankResponse:
        """Deterministic rerank: score each candidate by token overlap (latin words
        + CJK bigrams) with the topic/intent, then take the highest-scoring ids in
        stable order."""
        query_tokens = set(_mock_tokens(f"{request.topic} {request.creation_intent}"))

        def score(candidate: dict[str, str]) -> int:
            tokens = _mock_tokens(f"{candidate.get('name', '')} {candidate.get('description', '')}")
            return sum(1 for token in tokens if token in query_tokens)

        ordered = sorted(
            enumerate(request.candidates),
            key=lambda pair: (-score(pair[1]), pair[0]),
        )
        selected = [
            str(candidate.get("id", ""))
            for _, candidate in ordered
            if candidate.get("id")
        ][: max(0, request.max_select)]
        return MemoryRerankResponse(
            selected_ids=selected,
            provider_name=self.provider_name,
            model_name=self.model_name,
        )

    def merge_memories(self, request: MemoryMergeRequest) -> MemoryMergeResponse:
        """Deterministic merge: if the group shares a keyword and a single type,
        keep the earliest-created entry as primary and drop the rest. Otherwise
        signal 'no merge' with an empty primary_id."""
        entries = list(request.entries)
        empty = MemoryMergeResponse(
            primary_id="", name="", description="", body="", keywords=[],
            evidence_turn_ids=[], drop_ids=[],
            provider_name=self.provider_name, model_name=self.model_name,
        )
        if len(entries) < 2:
            return empty
        types = {str(e.get("type")) for e in entries}
        if len(types) != 1:
            return empty
        keyword_sets = [set(e.get("keywords") or []) for e in entries]
        shared = set.intersection(*keyword_sets) if keyword_sets else set()
        if not shared:
            return empty

        primary = min(entries, key=lambda e: str(e.get("created_at", "")))
        merged_keywords: list[str] = []
        evidence_turn_ids: list[str] = []
        for entry in entries:
            for kw in entry.get("keywords") or []:
                if kw not in merged_keywords:
                    merged_keywords.append(kw)
            for ev in entry.get("evidence") or []:
                tid = ev.get("turn_id")
                if tid and tid not in evidence_turn_ids:
                    evidence_turn_ids.append(tid)
        return MemoryMergeResponse(
            primary_id=str(primary.get("id", "")),
            name=str(primary.get("name", "")),
            description=str(primary.get("description", "")),
            body=str(primary.get("body", "")),
            keywords=merged_keywords[:12],
            evidence_turn_ids=evidence_turn_ids[:3],
            drop_ids=[str(e.get("id")) for e in entries if e.get("id") != primary.get("id")],
            provider_name=self.provider_name,
            model_name=self.model_name,
        )

    def classify_memory_action(self, request: MemoryActionRequest) -> MemoryActionResponse:
        """§10.5: Mock always returns none — deterministic rules handle test scenarios."""
        return MemoryActionResponse(
            action="none",
            subject="",
            provider_name=self.provider_name,
            model_name=self.model_name,
        )
