from __future__ import annotations

from dataclasses import dataclass

from app.domain.transcript import Speaker, TranscriptRecord


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    topic_context: bool
    core_viewpoint: bool
    example_or_detail: bool
    conclusion: bool

    @property
    def is_ready(self) -> bool:
        return (
            self.topic_context
            and self.core_viewpoint
            and self.example_or_detail
            and self.conclusion
        )

    def missing_dimensions(self) -> list[str]:
        missing: list[str] = []
        if not self.topic_context:
            missing.append("topic_context")
        if not self.core_viewpoint:
            missing.append("core_viewpoint")
        if not self.example_or_detail:
            missing.append("example_or_detail")
        if not self.conclusion:
            missing.append("conclusion")
        return missing


def evaluate_readiness(transcript: TranscriptRecord) -> ReadinessReport:
    user_turns = [
        turn.content.strip().lower()
        for turn in transcript.turns
        if turn.speaker == Speaker.USER and turn.content.strip()
    ]
    combined = "\n".join(user_turns)

    topic_context = len(user_turns) >= 1 and any(len(turn.split()) >= 8 for turn in user_turns)
    core_viewpoint = _contains_viewpoint(combined)
    example_or_detail = _contains_example_or_detail(combined)
    conclusion = _contains_conclusion(combined)

    return ReadinessReport(
        topic_context=topic_context,
        core_viewpoint=core_viewpoint,
        example_or_detail=example_or_detail,
        conclusion=conclusion,
    )


def _contains_viewpoint(text: str) -> bool:
    keywords = (
        "i think",
        "i believe",
        "my view",
        "i feel",
        "the point",
        "i learned",
        "i realized",
        "what matters",
        "important",
        "because",
    )
    return any(keyword in text for keyword in keywords)


def _contains_example_or_detail(text: str) -> bool:
    keywords = (
        "for example",
        "for instance",
        "when i",
        "once",
        "last",
        "yesterday",
        "case",
        "example",
        "specifically",
        "in practice",
    )
    return any(keyword in text for keyword in keywords)


def _contains_conclusion(text: str) -> bool:
    keywords = (
        "so",
        "in the end",
        "overall",
        "the takeaway",
        "my conclusion",
        "that means",
        "therefore",
        "what i want people to know",
    )
    return any(keyword in text for keyword in keywords)
