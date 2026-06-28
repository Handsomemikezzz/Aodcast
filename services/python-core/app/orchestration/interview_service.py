from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator, Union

from app.domain.project import SessionProject
from app.domain.session import SessionRecord, SessionState
from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.prompts import (
    InterviewPromptInput,
    build_interview_prompt_plan,
    build_prompt_input,
    build_question,
)
from app.orchestration.readiness import ReadinessReport, evaluate_readiness
from app.providers.llm.base import InterviewQuestionRequest
from app.providers.llm.factory import build_llm_provider
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore

if TYPE_CHECKING:
    from app.orchestration.memory_service import MemoryService


def _transcript_text(transcript: TranscriptRecord) -> str:
    return "\n".join(f"{turn.speaker.value}: {turn.content}" for turn in transcript.turns)


def _detect_language_is_zh(topic: str, transcript: TranscriptRecord) -> bool:
    text_to_check = topic + "".join(turn.content for turn in transcript.turns)
    return any("\u3400" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff" for char in text_to_check)


def _get_last_user_turn(transcript: TranscriptRecord) -> str:
    user_turns = [turn.content for turn in transcript.turns if turn.speaker == Speaker.USER]
    return user_turns[-1] if user_turns else ""


def _get_preceding_agent_focus(transcript: TranscriptRecord) -> str:
    """Return the interview_focus from the last agent turn, or 'unknown'."""
    for turn in reversed(transcript.turns):
        if turn.speaker == Speaker.AGENT:
            return str(turn.metadata.get("interview_focus") or "unknown")
    return "unknown"


def _agent_turn_metadata(plan_out: list) -> dict:
    """Extract compact turn metadata from a plan_out list populated by _stream_next_question."""
    if not plan_out:
        return {"interview_focus": "unknown", "turn_role": "question"}
    plan = plan_out[0]
    return {
        "interview_focus": str(plan.metadata.gates.get("suggested_focus", "unknown")),
        "turn_role": "question",
        "prompt_version": plan.metadata.prompt_version,
        # Keep section_ids compact: only the non-private section IDs for debugging.
        "prompt_section_ids": [
            sid for sid in plan.metadata.section_ids
            if not sid.startswith("transcript")
        ],
    }


# Deterministic explicit "remember this" directives (§10.2 obvious-instruction rule).
_EXPLICIT_REMEMBER_MARKERS = (
    "请记住",
    "记住",
    "记一下",
    "帮我记住",
    "remember that",
    "please remember",
    "note that i",
)

# §10.3: Deterministic correction markers — user explicitly corrects a past memory.
_EXPLICIT_CORRECT_MARKERS = (
    "你记错了",
    "记错了",
    "纠正一下",
    "不对，我",
    "说错了，应该是",
    "actually, i",
    "that's not right",
    "that's wrong",
    "not quite right",
    "i meant to say",
    "let me correct",
)

# §10.4: Deterministic forget markers — user explicitly asks to delete a past memory.
_EXPLICIT_FORGET_MARKERS = (
    "忘记我之前",
    "忘掉我之前",
    "别记",
    "别记录这个",
    "删掉这条记忆",
    "please forget",
    "forget that",
    "forget what i said about",
    "don't remember that",
)


def detect_explicit_remember(content: str) -> bool:
    lowered = content.strip().lower()
    if not lowered:
        return False
    return any(marker in content or marker in lowered for marker in _EXPLICIT_REMEMBER_MARKERS)


def detect_explicit_correct(content: str) -> bool:
    """§10.3: True when the user unambiguously signals a correction of a stored memory."""
    lowered = content.strip().lower()
    if not lowered:
        return False
    return any(marker in content or marker in lowered for marker in _EXPLICIT_CORRECT_MARKERS)


def detect_explicit_forget(content: str) -> bool:
    """§10.4: True when the user explicitly asks to forget/delete a past memory."""
    lowered = content.strip().lower()
    if not lowered:
        return False
    return any(marker in content or marker in lowered for marker in _EXPLICIT_FORGET_MARKERS)


@dataclass(frozen=True, slots=True)
class InterviewTurnResult:
    project: SessionProject
    readiness: ReadinessReport
    prompt_input: InterviewPromptInput
    next_question: str | None
    ai_can_finish: bool
    # §10.5: internal memory control signal detected from this user turn.
    # Values: "remember" | "correct" | "forget_candidates" | "none" | None (not evaluated)
    memory_action: str | None = None
    # §10.4: populated when memory_action == "forget_candidates" or
    # memory_action == "correct" with multiple ambiguous targets, so the frontend
    # can render a disambiguation panel.
    memory_action_candidates: list = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Default mutable field — dataclass frozen=True prevents normal assignment.
        if self.memory_action_candidates is None:
            object.__setattr__(self, "memory_action_candidates", [])


def _dispatch_memory_action(
    memory_service: "MemoryService",
    config_store: ConfigStore,
    session_id: str,
    turn_id: str,
    content: str,
    session: "SessionRecord",
) -> tuple[str | None, list]:
    """§10.3–10.5: Classify user intent and execute the corresponding memory action.

    Returns (action_label, candidate_list):
    - action_label: one of "remember", "correct", "forget_candidates", "none", or None
    - candidate_list: list of MemoryEntry dicts for disambiguation panels; empty otherwise

    Execution order:
      1. Deterministic forget markers  → §10.4
      2. Deterministic correction markers → §10.3
      3. Deterministic remember markers  → §10.2 (already handled, just label)
      4. Optional LLM classify_memory_action → §10.5 (fallback to none on error)

    Deletions are NEVER applied solely by model output; candidates are surfaced to
    the frontend which confirms via bridge.deleteMemory / bridge.supersedeMemory.
    """
    from app.orchestration.memory_service import ExplicitMemoryRejected
    from app.providers.llm.base import MemoryActionRequest
    from app.providers.llm.factory import build_llm_provider

    # §10.4: Forget — deterministic detection takes priority.
    if detect_explicit_forget(content):
        candidates = memory_service.find_forget_candidates(content)
        if len(candidates) == 1:
            # Unambiguous single target: delete immediately (user already stated intent).
            memory_service.delete_memory(candidates[0].id)
            return "none", []
        if len(candidates) > 1:
            # Ambiguous: surface to user for pick; deletion requires explicit UI confirmation.
            return "forget_candidates", [c.to_dict() for c in candidates]
        # No matching memory — nothing to forget.
        return "none", []

    # §10.3: Correction — deterministic detection.
    if detect_explicit_correct(content):
        candidates = memory_service.find_forget_candidates(content)
        target_id = candidates[0].id if len(candidates) == 1 else ""
        try:
            memory_service.apply_correction(
                session_id,
                source_turn_id=turn_id,
                raw_intent=content,
                target_id=target_id,
            )
        except ExplicitMemoryRejected:
            pass
        if len(candidates) > 1:
            # Surface candidates so user can confirm which old memory to supersede.
            return "correct", [c.to_dict() for c in candidates]
        return "correct", []

    # §10.2: Remember — already persisted if detect_explicit_remember fired;
    # still classify for the UI label.
    if detect_explicit_remember(content):
        try:
            memory_service.remember_explicit(
                session_id, source_turn_id=turn_id, raw_intent=content
            )
        except ExplicitMemoryRejected:
            pass
        return "remember", []

    # §10.5: No deterministic hit — fall back to optional LLM classifier.
    try:
        existing_names = [e.name for e in memory_service.list_memories()]
        llm_config = config_store.load_llm_config()
        provider = build_llm_provider(llm_config)
        result = provider.classify_memory_action(
            MemoryActionRequest(user_message=content, candidate_names=existing_names)
        )
        if result.action == "remember":
            try:
                memory_service.remember_explicit(
                    session_id, source_turn_id=turn_id, raw_intent=content
                )
            except ExplicitMemoryRejected:
                pass
            return "remember", []
        if result.action == "correct":
            subject = result.subject or content
            candidates = memory_service.find_forget_candidates(subject)
            target_id = candidates[0].id if len(candidates) == 1 else ""
            try:
                memory_service.apply_correction(
                    session_id,
                    source_turn_id=turn_id,
                    raw_intent=content,
                    target_id=target_id,
                )
            except ExplicitMemoryRejected:
                pass
            return "correct", [c.to_dict() for c in candidates] if len(candidates) > 1 else []
        if result.action == "forget_candidates":
            subject = result.subject or content
            candidates = memory_service.find_forget_candidates(subject)
            if len(candidates) == 1:
                memory_service.delete_memory(candidates[0].id)
                return "none", []
            if candidates:
                return "forget_candidates", [c.to_dict() for c in candidates]
    except Exception:
        pass

    return "none", []


class InterviewOrchestrator:
    def __init__(
        self,
        store: ProjectStore,
        config_store: ConfigStore,
        memory_service: "MemoryService | None" = None,
    ) -> None:
        self.store = store
        self.config_store = config_store
        self.memory_service = memory_service

    def _stream_next_question(
        self,
        project: SessionProject,
        prompt_input: InterviewPromptInput,
        transcript: TranscriptRecord,
        readiness: ReadinessReport | None = None,
        plan_out: list | None = None,
    ) -> Iterator[str]:
        """Stream the next interview question chunk by chunk.

        ``plan_out``: if a list is passed, the assembled PromptPlan is appended
        as its first element so the caller can inspect metadata for turn tagging
        without changing the generator return type.
        """
        llm_config = self.config_store.load_llm_config()
        provider = build_llm_provider(llm_config)
        memory_context = ""
        if self.memory_service is not None:
            try:
                retrieved = self.memory_service.build_interview_context(
                    project.session,
                    recent_user_message=_get_last_user_turn(transcript),
                )
                memory_context = retrieved.prompt_block
                if retrieved.item_count:
                    # Persisted by the caller's save_project after streaming.
                    project.session.record_memory_usage("interview", list(retrieved.memory_ids))
            except Exception:
                memory_context = ""

        # Build the PromptPlan for this turn.  Falls back gracefully when
        # readiness is not supplied (e.g. start_interview before first user reply).
        try:
            effective_readiness = readiness or evaluate_readiness(transcript)
            prompt_plan = build_interview_prompt_plan(
                topic=prompt_input.topic,
                creation_intent=prompt_input.creation_intent,
                transcript=transcript,
                readiness=effective_readiness,
                script_exists=(project.script is not None),
                memory_context=memory_context,
                transcript_text=_transcript_text(transcript),
            )
        except Exception:
            prompt_plan = None

        if plan_out is not None and prompt_plan is not None:
            plan_out.append(prompt_plan)

        request = InterviewQuestionRequest(
            session_id=prompt_input.session_id,
            topic=prompt_input.topic,
            creation_intent=prompt_input.creation_intent,
            transcript_text=_transcript_text(transcript),
            suggested_focus=prompt_input.suggested_focus,
            missing_dimensions=list(prompt_input.missing_dimensions),
            script_exists=(project.script is not None),
            memory_context=memory_context,
            prompt_plan=prompt_plan,
        )
        try:
            yield from provider.stream_interview_question(request)
        except Exception:
            if llm_config.provider != "mock":
                raise
            last_user_turn = _get_last_user_turn(transcript)
            is_zh = _detect_language_is_zh(prompt_input.topic, transcript)
            yield build_question(prompt_input, last_user_turn=last_user_turn, is_zh=is_zh)

    def _collect_streamed_next_question(
        self,
        project: SessionProject,
        prompt_input: InterviewPromptInput,
        transcript: TranscriptRecord,
        readiness: ReadinessReport | None = None,
        plan_out: list | None = None,
    ) -> str:
        question = "".join(
            self._stream_next_question(
                project, prompt_input, transcript,
                readiness=readiness, plan_out=plan_out,
            )
        ).strip()
        if not question:
            last_user_turn = _get_last_user_turn(transcript)
            is_zh = _detect_language_is_zh(prompt_input.topic, transcript)
            question = build_question(prompt_input, last_user_turn=last_user_turn, is_zh=is_zh)
        return question

    def start_interview(self, session_id: str) -> InterviewTurnResult:
        project = self.store.load_project(session_id)
        transcript = project.transcript or TranscriptRecord(session_id=session_id)
        project.transcript = transcript

        if not transcript.turns:
            project.session.transition(SessionState.INTERVIEW_IN_PROGRESS)
            readiness = evaluate_readiness(transcript)
            prompt_input = build_prompt_input(project.session, transcript, readiness)
            plan_out: list = []
            next_question = self._collect_streamed_next_question(
                project, prompt_input, transcript, readiness=readiness, plan_out=plan_out
            )
            # Tag the opening agent turn with interview focus metadata.
            agent_meta = _agent_turn_metadata(plan_out)
            transcript.append(Speaker.AGENT, next_question, metadata=agent_meta)
            self.store.save_project(project)
            return InterviewTurnResult(
                project=project,
                readiness=readiness,
                prompt_input=prompt_input,
                next_question=next_question,
                ai_can_finish=False,
            )

        readiness = evaluate_readiness(transcript)
        prompt_input = build_prompt_input(project.session, transcript, readiness)
        return InterviewTurnResult(
            project=project,
            readiness=readiness,
            prompt_input=prompt_input,
            next_question=None,
            ai_can_finish=readiness.is_ready,
        )

    def submit_user_response_stream(
        self,
        session_id: str,
        content: str,
        *,
        user_requested_finish: bool = False,
    ) -> Iterator[Union[str, InterviewTurnResult]]:
        project = self.store.load_project(session_id)
        transcript = project.transcript or TranscriptRecord(session_id=session_id)
        project.transcript = transcript

        project.session.transition(SessionState.INTERVIEW_IN_PROGRESS)
        # Tag user turn with the interview_focus from the preceding agent turn.
        # This links user answers to the dimension the agent was exploring, enabling
        # deterministic EpisodeBrief construction without post-hoc keyword matching.
        preceding_focus = _get_preceding_agent_focus(transcript)
        user_turn = transcript.append(Speaker.USER, content, metadata={
            "interview_focus": preceding_focus,
            "turn_role": "answer",
        })
        # Persist the user turn before streaming provider output so partial failures
        # still leave the user's message visible when reopening the session.
        self.store.save_project(project)

        # §10.5: Detect and dispatch memory control signals. Never blocks or
        # fails the interview — all exceptions are swallowed here.
        detected_action: str | None = None
        action_candidates: list = []
        if self.memory_service is not None:
            try:
                detected_action, action_candidates = _dispatch_memory_action(
                    self.memory_service,
                    self.config_store,
                    session_id,
                    user_turn.turn_id,
                    content,
                    project.session,
                )
            except Exception:
                pass
            try:
                self.memory_service.enqueue_extraction(project.session)
            except Exception:
                pass

        project.session.transition(SessionState.READINESS_EVALUATION)
        readiness = evaluate_readiness(transcript)
        prompt_input = build_prompt_input(project.session, transcript, readiness)

        if user_requested_finish:
            project.session.transition(SessionState.READY_TO_GENERATE)
            self.store.save_project(project)
            yield InterviewTurnResult(
                project=project,
                readiness=readiness,
                prompt_input=prompt_input,
                next_question=None,
                ai_can_finish=True,
                memory_action=detected_action,
                memory_action_candidates=action_candidates,
            )
            return

        # Deterministic transition when readiness is complete and NO script has been generated yet
        if project.script is None and readiness.is_ready:
            project.session.transition(SessionState.READY_TO_GENERATE)

            is_zh = _detect_language_is_zh(project.session.topic, transcript)

            if is_zh:
                deterministic_message = (
                    "我们已经收集到了本期节目的背景信息、核心观点、具体案例以及总结结论，这些材料已经足够生成一版播客脚本了。我建议现在先生成一版，这样你可以在稿子里继续调整结构和语气。\n\n"
                    "A. 生成播客脚本（推荐）\n"
                    "B. 再补一个具体故事\n"
                    "C. 先调整这一期的核心角度\n\n"
                    "当然，如果你有任何想要补充的内容，也可以直接在这里继续输入。"
                )
            else:
                deterministic_message = (
                    "We have successfully gathered the topic context, core viewpoint, supporting details, and key takeaway for this episode. This is enough material to generate your podcast script. I recommend generating the draft now so you can refine its structure and tone in the editor.\n\n"
                    "A. Generate podcast script (Recommended)\n"
                    "B. Add another concrete story\n"
                    "C. Adjust the core angle of this episode\n\n"
                    "Of course, if you have any additional details to add, feel free to reply directly."
                )

            # Yield chunks of the deterministic message
            chunk_size = 10
            for i in range(0, len(deterministic_message), chunk_size):
                yield deterministic_message[i : i + chunk_size]

            transcript.append(Speaker.AGENT, deterministic_message, metadata={
                "interview_focus": "ready_to_generate",
                "turn_role": "ready_message",
            })
            self.store.save_project(project)

            yield InterviewTurnResult(
                project=project,
                readiness=readiness,
                prompt_input=prompt_input,
                next_question=deterministic_message,
                ai_can_finish=True,
                memory_action=detected_action,
                memory_action_candidates=action_candidates,
            )
            return

        project.session.transition(SessionState.INTERVIEW_IN_PROGRESS)

        plan_out: list = []
        full_question = []
        for chunk in self._stream_next_question(
            project, prompt_input, transcript, readiness=readiness, plan_out=plan_out
        ):
            full_question.append(chunk)
            yield chunk

        next_question = "".join(full_question).strip()
        if not next_question:
            last_user_turn = _get_last_user_turn(transcript)
            is_zh = _detect_language_is_zh(project.session.topic, transcript)
            next_question = build_question(prompt_input, last_user_turn=last_user_turn, is_zh=is_zh)
            yield next_question

        # Tag agent turn with focus metadata from the assembled PromptPlan.
        agent_meta = _agent_turn_metadata(plan_out)
        transcript.append(Speaker.AGENT, next_question, metadata=agent_meta)
        self.store.save_project(project)

        yield InterviewTurnResult(
            project=project,
            readiness=readiness,
            prompt_input=prompt_input,
            next_question=next_question,
            ai_can_finish=readiness.is_ready,
            memory_action=detected_action,
            memory_action_candidates=action_candidates,
        )

    def request_finish(self, session_id: str) -> InterviewTurnResult:
        project = self.store.load_project(session_id)
        transcript = project.transcript or TranscriptRecord(session_id=session_id)
        project.transcript = transcript
        project.session.transition(SessionState.READY_TO_GENERATE)
        readiness = evaluate_readiness(transcript)
        prompt_input = build_prompt_input(project.session, transcript, readiness)
        self.store.save_project(project)
        # Leaving the interview / moving to script generation: flush remaining turns.
        if self.memory_service is not None:
            try:
                self.memory_service.enqueue_extraction_now(project.session)
            except Exception:
                pass
        return InterviewTurnResult(
            project=project,
            readiness=readiness,
            prompt_input=prompt_input,
            next_question=None,
            ai_can_finish=True,
        )
