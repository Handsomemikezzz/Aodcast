from __future__ import annotations

from dataclasses import dataclass

from app.domain.session import SessionRecord
from app.domain.transcript import TranscriptRecord
from app.orchestration.readiness import ReadinessReport


@dataclass(frozen=True, slots=True)
class InterviewPromptInput:
    session_id: str
    topic: str
    creation_intent: str
    state: str
    transcript_turn_count: int
    missing_dimensions: list[str]
    suggested_focus: str
    role_instruction: str
    goal_instruction: str
    strategy_instruction: str
    boundary_instruction: str

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "topic": self.topic,
            "creation_intent": self.creation_intent,
            "state": self.state,
            "transcript_turn_count": self.transcript_turn_count,
            "missing_dimensions": self.missing_dimensions,
            "suggested_focus": self.suggested_focus,
            "role_instruction": self.role_instruction,
            "goal_instruction": self.goal_instruction,
            "strategy_instruction": self.strategy_instruction,
            "boundary_instruction": self.boundary_instruction,
        }


def build_prompt_input(
    session: SessionRecord,
    transcript: TranscriptRecord,
    readiness: ReadinessReport,
) -> InterviewPromptInput:
    missing = readiness.missing_dimensions()
    focus = missing[0] if missing else "ready_to_generate"

    return InterviewPromptInput(
        session_id=session.session_id,
        topic=session.topic,
        creation_intent=session.creation_intent,
        state=session.state.value,
        transcript_turn_count=len(transcript.turns),
        missing_dimensions=missing,
        suggested_focus=focus,
        role_instruction=(
            "You are a perceptive podcast interviewer helping the user clarify a "
            "real point of view."
        ),
        goal_instruction=(
            "Gather enough material for a solo podcast script with a hook, a "
            "clear argument, supporting detail, and a conclusion."
        ),
        strategy_instruction=(
            "Ask one high-value follow-up that fills the most important missing "
            "dimension first."
        ),
        boundary_instruction=(
            "Do not invent user details, ask multiple unrelated questions at once, "
            "or switch into long-form script writing."
        ),
    )


def build_question(prompt_input: InterviewPromptInput) -> str:
    focus = prompt_input.suggested_focus
    if focus == "topic_context":
        return (
            f"You want to turn '{prompt_input.topic}' into a podcast. "
            "What happened or what prompted this topic for you right now?"
        )
    if focus == "core_viewpoint":
        return (
            "What is the main thing you believe or want to argue about this topic?"
        )
    if focus == "example_or_detail":
        return (
            "Can you give me one concrete example, story, or detail that makes this "
            "point feel real?"
        )
    if focus == "conclusion":
        return (
            "If listeners remember one takeaway or conclusion from this episode, "
            "what should it be?"
        )
    return (
        "I have enough material to draft the episode. If you want, we can stop "
        "the interview and move to script generation."
    )
