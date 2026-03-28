from __future__ import annotations

from dataclasses import dataclass

from app.domain.project import SessionProject
from app.domain.session import SessionRecord, SessionState
from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.prompts import (
    InterviewPromptInput,
    build_prompt_input,
    build_question,
)
from app.orchestration.readiness import ReadinessReport, evaluate_readiness
from app.storage.project_store import ProjectStore


@dataclass(frozen=True, slots=True)
class InterviewTurnResult:
    project: SessionProject
    readiness: ReadinessReport
    prompt_input: InterviewPromptInput
    next_question: str | None
    ai_can_finish: bool


class InterviewOrchestrator:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def start_interview(self, session_id: str) -> InterviewTurnResult:
        project = self.store.load_project(session_id)
        transcript = project.transcript or TranscriptRecord(session_id=session_id)
        project.transcript = transcript

        if not transcript.turns:
            project.session.transition(SessionState.INTERVIEW_IN_PROGRESS)
            readiness = evaluate_readiness(transcript)
            prompt_input = build_prompt_input(project.session, transcript, readiness)
            next_question = build_question(prompt_input)
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

        project.session.transition(SessionState.READINESS_EVALUATION)
        readiness = evaluate_readiness(transcript)
        prompt_input = build_prompt_input(project.session, transcript, readiness)

        if user_requested_finish or readiness.is_ready:
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
        next_question = build_question(prompt_input)
        transcript.append(Speaker.AGENT, next_question)
        self.store.save_project(project)
        return InterviewTurnResult(
            project=project,
            readiness=readiness,
            prompt_input=prompt_input,
            next_question=next_question,
            ai_can_finish=False,
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
