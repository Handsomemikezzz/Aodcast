from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Union

from app.domain.project import SessionProject
from app.domain.session import SessionState
from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.prompts import (
    InterviewPromptInput,
    build_prompt_input,
    build_question,
)
from app.orchestration.readiness import ReadinessReport, evaluate_readiness
from app.providers.llm.base import InterviewQuestionRequest
from app.providers.llm.factory import build_llm_provider
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


def _transcript_text(transcript: TranscriptRecord) -> str:
    return "\n".join(f"{turn.speaker.value}: {turn.content}" for turn in transcript.turns)


@dataclass(frozen=True, slots=True)
class InterviewTurnResult:
    project: SessionProject
    readiness: ReadinessReport
    prompt_input: InterviewPromptInput
    next_question: str | None
    ai_can_finish: bool


class InterviewOrchestrator:
    def __init__(self, store: ProjectStore, config_store: ConfigStore) -> None:
        self.store = store
        self.config_store = config_store

    def _next_question(
        self,
        project: SessionProject,
        prompt_input: InterviewPromptInput,
        transcript: TranscriptRecord,
    ) -> str:
        llm_config = self.config_store.load_llm_config()
        provider = build_llm_provider(llm_config)
        request = InterviewQuestionRequest(
            session_id=prompt_input.session_id,
            topic=prompt_input.topic,
            creation_intent=prompt_input.creation_intent,
            transcript_text=_transcript_text(transcript),
            suggested_focus=prompt_input.suggested_focus,
            missing_dimensions=list(prompt_input.missing_dimensions),
        )
        try:
            response = provider.generate_interview_question(request)
            question = response.question.strip()
            if question:
                return question
        except Exception:
            if llm_config.provider != "mock":
                raise
        return build_question(prompt_input)

    def _stream_next_question(
        self,
        project: SessionProject,
        prompt_input: InterviewPromptInput,
        transcript: TranscriptRecord,
    ) -> Iterator[str]:
        llm_config = self.config_store.load_llm_config()
        provider = build_llm_provider(llm_config)
        request = InterviewQuestionRequest(
            session_id=prompt_input.session_id,
            topic=prompt_input.topic,
            creation_intent=prompt_input.creation_intent,
            transcript_text=_transcript_text(transcript),
            suggested_focus=prompt_input.suggested_focus,
            missing_dimensions=list(prompt_input.missing_dimensions),
        )
        try:
            yield from provider.stream_interview_question(request)
        except Exception:
            if llm_config.provider != "mock":
                raise
            # Fallback to mock behavior if streaming fails and we are in mock mode
            yield self._next_question(project, prompt_input, transcript)

    def start_interview(self, session_id: str) -> InterviewTurnResult:
        project = self.store.load_project(session_id)
        transcript = project.transcript or TranscriptRecord(session_id=session_id)
        project.transcript = transcript

        if not transcript.turns:
            project.session.transition(SessionState.INTERVIEW_IN_PROGRESS)
            readiness = evaluate_readiness(transcript)
            prompt_input = build_prompt_input(project.session, transcript, readiness)
            next_question = self._next_question(project, prompt_input, transcript)
            transcript.append(Speaker.AGENT, next_question)
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

    def submit_user_response(
        self,
        session_id: str,
        content: str,
        *,
        user_requested_finish: bool = False,
    ) -> InterviewTurnResult:
        project = self.store.load_project(session_id)
        transcript = project.transcript or TranscriptRecord(session_id=session_id)
        project.transcript = transcript

        project.session.transition(SessionState.INTERVIEW_IN_PROGRESS)
        transcript.append(Speaker.USER, content)
        # Persist the user turn before any provider work so reopening the session
        # still shows the message if generation hangs, fails, or the client disconnects.
        self.store.save_project(project)

        project.session.transition(SessionState.READINESS_EVALUATION)
        readiness = evaluate_readiness(transcript)
        prompt_input = build_prompt_input(project.session, transcript, readiness)

        if user_requested_finish:
            project.session.transition(SessionState.READY_TO_GENERATE)
            self.store.save_project(project)
            return InterviewTurnResult(
                project=project,
                readiness=readiness,
                prompt_input=prompt_input,
                next_question=None,
                ai_can_finish=True,
            )

        project.session.transition(SessionState.INTERVIEW_IN_PROGRESS)
        next_question = self._next_question(project, prompt_input, transcript)
        transcript.append(Speaker.AGENT, next_question)
        self.store.save_project(project)
        return InterviewTurnResult(
            project=project,
            readiness=readiness,
            prompt_input=prompt_input,
            next_question=next_question,
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
        transcript.append(Speaker.USER, content)
        # Persist the user turn before streaming provider output so partial failures
        # still leave the user's message visible when reopening the session.
        self.store.save_project(project)

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
            )
            return

        project.session.transition(SessionState.INTERVIEW_IN_PROGRESS)
        
        full_question = []
        for chunk in self._stream_next_question(project, prompt_input, transcript):
            full_question.append(chunk)
            yield chunk

        next_question = "".join(full_question).strip()
        transcript.append(Speaker.AGENT, next_question)
        self.store.save_project(project)
        
        yield InterviewTurnResult(
            project=project,
            readiness=readiness,
            prompt_input=prompt_input,
            next_question=next_question,
            ai_can_finish=readiness.is_ready,
        )

    def request_finish(self, session_id: str) -> InterviewTurnResult:
        project = self.store.load_project(session_id)
        transcript = project.transcript or TranscriptRecord(session_id=session_id)
        project.transcript = transcript
        project.session.transition(SessionState.READY_TO_GENERATE)
        readiness = evaluate_readiness(transcript)
        prompt_input = build_prompt_input(project.session, transcript, readiness)
        self.store.save_project(project)
        return InterviewTurnResult(
            project=project,
            readiness=readiness,
            prompt_input=prompt_input,
            next_question=None,
            ai_can_finish=True,
        )
