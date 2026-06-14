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


def _detect_language_is_zh(topic: str, transcript: TranscriptRecord) -> bool:
    text_to_check = topic + "".join(turn.content for turn in transcript.turns)
    return any("\u3400" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff" for char in text_to_check)


def _get_last_user_turn(transcript: TranscriptRecord) -> str:
    user_turns = [turn.content for turn in transcript.turns if turn.speaker == Speaker.USER]
    return user_turns[-1] if user_turns else ""


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
            script_exists=(project.script is not None),
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
    ) -> str:
        question = "".join(self._stream_next_question(project, prompt_input, transcript)).strip()
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
            next_question = self._collect_streamed_next_question(project, prompt_input, transcript)
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

            transcript.append(Speaker.AGENT, deterministic_message)
            self.store.save_project(project)

            yield InterviewTurnResult(
                project=project,
                readiness=readiness,
                prompt_input=prompt_input,
                next_question=deterministic_message,
                ai_can_finish=True,
            )
            return

        project.session.transition(SessionState.INTERVIEW_IN_PROGRESS)

        full_question = []
        for chunk in self._stream_next_question(project, prompt_input, transcript):
            full_question.append(chunk)
            yield chunk

        next_question = "".join(full_question).strip()
        if not next_question:
            last_user_turn = _get_last_user_turn(transcript)
            is_zh = _detect_language_is_zh(project.session.topic, transcript)
            next_question = build_question(prompt_input, last_user_turn=last_user_turn, is_zh=is_zh)
            yield next_question
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
