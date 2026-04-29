from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.provider_config import LLMProviderConfig
from app.providers.llm.factory import SUPPORTED_LLM_PROVIDERS

LLM_DEPENDENT_ACTIONS = ("start_interview", "submit_reply", "generate_script")


@dataclass(frozen=True, slots=True)
class LLMConfigPreflight:
    ready: bool
    provider: str
    missing_fields: tuple[str, ...]
    supported_actions: tuple[str, ...]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "provider": self.provider,
            "missing_fields": list(self.missing_fields),
            "supported_actions": list(self.supported_actions),
            "message": self.message,
        }


def check_llm_config(config: LLMProviderConfig) -> LLMConfigPreflight:
    provider = config.provider.strip()
    if provider == "mock":
        return LLMConfigPreflight(
            ready=True,
            provider=provider,
            missing_fields=(),
            supported_actions=LLM_DEPENDENT_ACTIONS,
            message="Language model setup is ready for interview and script generation.",
        )
    if provider != "openai_compatible":
        allowed = ", ".join(SUPPORTED_LLM_PROVIDERS)
        return LLMConfigPreflight(
            ready=False,
            provider=provider,
            missing_fields=("provider",),
            supported_actions=LLM_DEPENDENT_ACTIONS,
            message=f"Unsupported language model provider '{provider}'. Choose one of: {allowed}.",
        )

    missing_fields: list[str] = []
    if not config.base_url.strip():
        missing_fields.append("base_url")
    if not config.model.strip():
        missing_fields.append("model")
    if not config.api_key.strip():
        missing_fields.append("api_key")

    if missing_fields:
        field_labels = {
            "base_url": "Base URL",
            "model": "Model",
            "api_key": "API key",
        }
        missing_labels = ", ".join(field_labels[field] for field in missing_fields)
        return LLMConfigPreflight(
            ready=False,
            provider=provider,
            missing_fields=tuple(missing_fields),
            supported_actions=LLM_DEPENDENT_ACTIONS,
            message=(
                f"Language model setup is incomplete: {missing_labels} required. "
                "Open Settings to configure the interview model, or choose the mock provider for a demo."
            ),
        )

    return LLMConfigPreflight(
        ready=True,
        provider=provider,
        missing_fields=(),
        supported_actions=LLM_DEPENDENT_ACTIONS,
        message="Language model setup is ready for interview and script generation.",
    )
