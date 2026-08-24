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
    if provider == "codex_subscription":
        from app.providers.llm.codex_app_server import codex_provider_status

        status = codex_provider_status()
        missing_fields: list[str] = []
        validation_message = ""
        if not status.installed:
            missing_fields.append("codex_cli")
        elif not status.authenticated:
            missing_fields.append("chatgpt_login")
        available_models = {model.id for model in status.models}
        if status.authenticated and not available_models:
            missing_fields.append("model")
        elif config.model.strip() and config.model.strip() not in available_models:
            missing_fields.append("model")
            validation_message = (
                f"Codex model '{config.model.strip()}' is not available for the signed-in account."
            )
        requested_model = config.model.strip()
        selected_model = (
            next((model for model in status.models if model.id == requested_model), None)
            if requested_model
            else next(
                (model for model in status.models if model.is_default),
                status.models[0] if status.models else None,
            )
        )
        reasoning_effort = config.reasoning_effort.strip().lower() or "auto"
        if (
            reasoning_effort != "auto"
            and selected_model is not None
            and reasoning_effort not in selected_model.supported_reasoning_efforts
        ):
            missing_fields.append("reasoning_effort")
            supported = ", ".join(selected_model.supported_reasoning_efforts)
            validation_message = (
                f"Reasoning effort '{reasoning_effort}' is not supported by Codex model "
                f"'{selected_model.id}'. Choose Auto or one of: {supported}."
            )
        if missing_fields:
            return LLMConfigPreflight(
                ready=False,
                provider=provider,
                missing_fields=tuple(missing_fields),
                supported_actions=LLM_DEPENDENT_ACTIONS,
                message=validation_message or status.message,
            )
        return LLMConfigPreflight(
            ready=True,
            provider=provider,
            missing_fields=(),
            supported_actions=LLM_DEPENDENT_ACTIONS,
            message="ChatGPT subscription is ready for interview and script generation through Codex.",
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
