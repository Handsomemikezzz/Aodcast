from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class LLMProviderConfig:
    provider: str = "openai_compatible"
    model: str = ""
    base_url: str = ""
    api_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LLMProviderConfig":
        return cls(
            provider=str(payload.get("provider", "openai_compatible")),
            model=str(payload.get("model", "")),
            base_url=str(payload.get("base_url", "")),
            api_key=str(payload.get("api_key", "")),
        )
