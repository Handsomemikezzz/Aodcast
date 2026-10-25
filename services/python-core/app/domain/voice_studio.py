from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STANDARD_PREVIEW_TEXT = "欢迎收听今天的节目，我们将用几分钟理清一个复杂但重要的话题。"


@dataclass(frozen=True, slots=True)
class VoicePreset:
    voice_id: str
    name: str
    description: str
    scenario: str
    tags: tuple[str, ...]
    provider_voice: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "voice_id": self.voice_id,
            "name": self.name,
            "description": self.description,
            "scenario": self.scenario,
            "tags": list(self.tags),
            "provider_voice": self.provider_voice,
        }


@dataclass(frozen=True, slots=True)
class VoiceStylePreset:
    style_id: str
    name: str
    prompt: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "style_id": self.style_id,
            "name": self.name,
            "prompt": self.prompt,
        }


VOICE_PRESETS: tuple[VoicePreset, ...] = (
    VoicePreset(
        voice_id="warm_narrator",
        name="Warm narrator",
        description="Steady and friendly; suits explanatory content.",
        scenario="Knowledge and explainer podcasts",
        tags=("warm", "explainer", "long-form"),
        provider_voice="alloy",
    ),
    VoicePreset(
        voice_id="news_anchor",
        name="Clear news anchor",
        description="Crisp pronunciation and a firm pace; suits news and analysis.",
        scenario="News, analysis, formal content",
        tags=("clear", "formal", "news"),
        provider_voice="onyx",
    ),
    VoicePreset(
        voice_id="casual_chat",
        name="Casual chat",
        description="Relaxed and companionable; suits lighter topics.",
        scenario="Lifestyle and easy listening",
        tags=("casual", "companionable", "natural"),
        provider_voice="nova",
    ),
    VoicePreset(
        voice_id="deep_story",
        name="Deep storyteller",
        description="Low and narrative; suits story-driven scripts.",
        scenario="Narrative, history, stories",
        tags=("deep", "narrative", "immersive"),
        provider_voice="echo",
    ),
    VoicePreset(
        voice_id="bright_energy",
        name="Bright and energetic",
        description="Brighter and livelier; suits fast-paced opinion pieces.",
        scenario="Opinion, short-form, fast-paced shows",
        tags=("bright", "energetic", "opinion"),
        provider_voice="shimmer",
    ),
)


STYLE_PRESETS: tuple[VoiceStylePreset, ...] = (
    VoiceStylePreset("natural", "Natural", "Speak naturally, like a thoughtful podcast narrator."),
    VoiceStylePreset("news", "News", "Use a clear, composed, news-broadcast delivery."),
    VoiceStylePreset("casual", "Casual", "Use a relaxed conversational tone."),
    VoiceStylePreset("story", "Storytelling", "Use a slower, immersive storytelling tone."),
)


def resolve_voice_preset(voice_id: str) -> VoicePreset:
    cleaned = voice_id.strip()
    for preset in VOICE_PRESETS:
        if preset.voice_id == cleaned:
            return preset
    return VOICE_PRESETS[0]


def resolve_style_preset(style_id: str) -> VoiceStylePreset:
    cleaned = style_id.strip()
    for preset in STYLE_PRESETS:
        if preset.style_id == cleaned:
            return preset
    return STYLE_PRESETS[0]


def clamp_speed(speed: float) -> float:
    return min(1.2, max(0.8, speed))
