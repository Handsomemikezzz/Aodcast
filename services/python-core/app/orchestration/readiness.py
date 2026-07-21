from __future__ import annotations

from dataclasses import dataclass

from app.domain.transcript import Speaker, TranscriptRecord

# Interview loops (user answers) required before we soft-offer script generation.
# Content dimensions alone must not cut the conversation short.
MIN_USER_TURNS_FOR_SCRIPT_OFFER = 4


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    topic_context: bool
    core_viewpoint: bool
    example_or_detail: bool
    conclusion: bool
    user_turn_count: int = 0

    @property
    def is_ready(self) -> bool:
        """True when the four content dimensions look covered (keyword heuristics)."""
        return (
            self.topic_context
            and self.core_viewpoint
            and self.example_or_detail
            and self.conclusion
        )

    @property
    def meets_turn_floor(self) -> bool:
        return self.user_turn_count >= MIN_USER_TURNS_FOR_SCRIPT_OFFER

    @property
    def can_offer_script(self) -> bool:
        """Content ready AND enough interview loops — soft-offer only, never a hard stop."""
        return self.is_ready and self.meets_turn_floor

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

    topic_context = len(user_turns) >= 1 and any(_has_enough_topic_context(turn) for turn in user_turns)
    core_viewpoint = _contains_viewpoint(combined)
    example_or_detail = _contains_example_or_detail(combined)
    conclusion = _contains_conclusion(combined)

    return ReadinessReport(
        topic_context=topic_context,
        core_viewpoint=core_viewpoint,
        example_or_detail=example_or_detail,
        conclusion=conclusion,
        user_turn_count=len(user_turns),
    )


def _has_enough_topic_context(text: str) -> bool:
    latin_word_count = len(text.split())
    cjk_char_count = sum(1 for char in text if "\u3400" <= char <= "\u9fff" or "\uf900" <= char <= "\ufaff")
    # CJK languages do not use spaces between words; a short reflective sentence
    # with roughly 16+ Han characters carries enough context for the first pass.
    return latin_word_count >= 8 or cjk_char_count >= 16


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
        "我认为",
        "我覺得",
        "我觉得",
        "我的观点",
        "我的看法",
        "我相信",
        "我意识到",
        "重要",
        "因为",
        "原因是",
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
        "比如",
        "例如",
        "举例",
        "有一次",
        "上周",
        "昨天",
        "具体来说",
        "实际",
        "实践中",
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
        "所以",
        "总之",
        "總之",
        "最后",
        "最後",
        "结论",
        "結論",
        "我的结论",
        "我的結論",
        "我希望大家记住",
        "我希望大家記住",
    )
    return any(keyword in text for keyword in keywords)
