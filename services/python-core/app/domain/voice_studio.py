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
        name="温和叙述者",
        description="语气稳定、亲和，适合解释型内容。",
        scenario="知识类、解释型播客",
        tags=("温和", "知识", "长听"),
        provider_voice="alloy",
    ),
    VoicePreset(
        voice_id="news_anchor",
        name="清晰新闻播报",
        description="发音清楚、节奏明确，适合资讯和分析。",
        scenario="资讯、分析、正式内容",
        tags=("清晰", "正式", "资讯"),
        provider_voice="onyx",
    ),
    VoicePreset(
        voice_id="casual_chat",
        name="轻松聊天",
        description="更轻松的陪伴感表达，适合轻量主题。",
        scenario="生活方式、轻量陪伴",
        tags=("轻松", "陪伴", "自然"),
        provider_voice="nova",
    ),
    VoicePreset(
        voice_id="deep_story",
        name="低沉故事感",
        description="低沉、有叙事感，适合故事类脚本。",
        scenario="叙事、历史、故事",
        tags=("低沉", "叙事", "沉浸"),
        provider_voice="echo",
    ),
    VoicePreset(
        voice_id="bright_energy",
        name="明亮活力型",
        description="更明亮、更有能量，适合节奏较快的观点表达。",
        scenario="观点、短内容、快节奏节目",
        tags=("明亮", "活力", "观点"),
        provider_voice="shimmer",
    ),
)


STYLE_PRESETS: tuple[VoiceStylePreset, ...] = (
    VoiceStylePreset("natural", "自然讲述", "Speak naturally, like a thoughtful podcast narrator."),
    VoiceStylePreset("news", "新闻播报", "Use a clear, composed, news-broadcast delivery."),
    VoiceStylePreset("casual", "轻松聊天", "Use a relaxed conversational tone."),
    VoiceStylePreset("story", "故事感", "Use a slower, immersive storytelling tone."),
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
