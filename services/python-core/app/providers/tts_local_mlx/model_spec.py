from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping

from app.providers.tts_local_mlx.presets import SUPPORTED_LOCAL_TTS_MODELS


class ModelFamily(StrEnum):
    QWEN3 = "qwen3_tts"
    VOXCPM2 = "voxcpm2"
    MOSS = "moss_tts"


class ModelVariant(StrEnum):
    QWEN_BASE = "base"
    QWEN_CUSTOM_VOICE = "custom_voice"
    QWEN_VOICE_DESIGN = "voice_design"
    VOXCPM2 = "voxcpm2"
    MOSS_DELAY = "delay"
    MOSS_LOCAL = "local"


class UnsupportedMLXModelError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ModelSpec:
    family: ModelFamily
    variant: ModelVariant
    model_type: str
    sample_rate_hz: int
    channels: int


_MODEL_TYPE_TO_SPEC: dict[str, ModelSpec] = {
    "voxcpm2": ModelSpec(
        family=ModelFamily.VOXCPM2,
        variant=ModelVariant.VOXCPM2,
        model_type="voxcpm2",
        sample_rate_hz=48_000,
        channels=1,
    ),
    "moss_tts_delay": ModelSpec(
        family=ModelFamily.MOSS,
        variant=ModelVariant.MOSS_DELAY,
        model_type="moss_tts_delay",
        sample_rate_hz=24_000,
        channels=1,
    ),
    "moss_tts_local": ModelSpec(
        family=ModelFamily.MOSS,
        variant=ModelVariant.MOSS_LOCAL,
        model_type="moss_tts_local",
        sample_rate_hz=48_000,
        channels=2,
    ),
}


def _qwen_spec(variant: str) -> ModelSpec:
    normalized = variant.strip().lower() or ModelVariant.QWEN_BASE
    try:
        resolved_variant = ModelVariant(normalized)
    except ValueError as exc:
        raise UnsupportedMLXModelError(
            f"Unsupported Qwen3-TTS variant '{variant}'."
        ) from exc
    if resolved_variant not in {
        ModelVariant.QWEN_BASE,
        ModelVariant.QWEN_CUSTOM_VOICE,
        ModelVariant.QWEN_VOICE_DESIGN,
    }:
        raise UnsupportedMLXModelError(
            f"Unsupported Qwen3-TTS variant '{variant}'."
        )
    return ModelSpec(
        family=ModelFamily.QWEN3,
        variant=resolved_variant,
        model_type="qwen3_tts",
        sample_rate_hz=24_000,
        channels=1,
    )


def model_spec_from_config(config: Mapping[str, Any]) -> ModelSpec:
    model_type = str(config.get("model_type") or "").strip().lower()
    if model_type == "qwen3_tts":
        return _qwen_spec(str(config.get("tts_model_type") or "base"))
    spec = _MODEL_TYPE_TO_SPEC.get(model_type)
    if spec is None:
        shown = model_type or "<missing>"
        raise UnsupportedMLXModelError(
            f"Unsupported local MLX TTS model_type '{shown}'."
        )

    sampling_rate = config.get("sampling_rate")
    if isinstance(sampling_rate, int) and sampling_rate > 0:
        spec = ModelSpec(
            family=spec.family,
            variant=spec.variant,
            model_type=spec.model_type,
            sample_rate_hz=sampling_rate,
            channels=spec.channels,
        )
    return spec


def read_local_model_config(model_path: Path) -> dict[str, Any]:
    config_path = model_path / "config.json"
    if not config_path.is_file():
        raise UnsupportedMLXModelError(
            f"Local MLX model is missing config.json: {model_path}"
        )
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UnsupportedMLXModelError(
            f"Local MLX model has an unreadable config.json: {model_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise UnsupportedMLXModelError(
            f"Local MLX model config.json must contain an object: {model_path}"
        )
    return payload


def _remote_model_spec(model_id: str) -> ModelSpec:
    normalized = model_id.rstrip("/")
    if normalized not in SUPPORTED_LOCAL_TTS_MODELS:
        raise UnsupportedMLXModelError(
            f"Unsupported local MLX TTS repository '{model_id}'."
        )
    tail = normalized.rsplit("/", 1)[-1].lower()
    if "qwen3-tts" in tail:
        if "customvoice" in tail:
            return _qwen_spec(ModelVariant.QWEN_CUSTOM_VOICE)
        if "voicedesign" in tail:
            return _qwen_spec(ModelVariant.QWEN_VOICE_DESIGN)
        return _qwen_spec(ModelVariant.QWEN_BASE)
    if tail.startswith("voxcpm2"):
        return _MODEL_TYPE_TO_SPEC["voxcpm2"]
    if "moss-tts-local-transformer" in tail:
        return _MODEL_TYPE_TO_SPEC["moss_tts_local"]
    if "moss-tts" in tail:
        return _MODEL_TYPE_TO_SPEC["moss_tts_delay"]
    raise UnsupportedMLXModelError(
        f"No model specification is registered for '{model_id}'."
    )


def resolve_model_spec(model_target: str) -> ModelSpec:
    path = Path(model_target).expanduser()
    if path.is_dir():
        return model_spec_from_config(read_local_model_config(path))
    return _remote_model_spec(model_target.strip())


def model_spec_from_loaded_model(model: Any) -> ModelSpec:
    config = getattr(model, "config", None)
    if config is None:
        config = getattr(model, "args", None)
    if config is None:
        raise UnsupportedMLXModelError(
            "Loaded MLX TTS model does not expose config metadata."
        )
    if isinstance(config, Mapping):
        payload = dict(config)
    else:
        payload = {
            "model_type": getattr(config, "model_type", ""),
            "tts_model_type": getattr(config, "tts_model_type", ""),
            "sampling_rate": getattr(config, "sampling_rate", None),
        }
    if not str(payload.get("model_type") or "").strip():
        # mlx-audio's VoxCPM2 ModelArgs intentionally filters model_type out of
        # config.json. The loaded class module is therefore the remaining
        # authoritative family discriminator.
        module_name = type(model).__module__.lower()
        if ".voxcpm2." in module_name:
            return _MODEL_TYPE_TO_SPEC["voxcpm2"]
    return model_spec_from_config(payload)


def validate_loaded_model_spec(expected: ModelSpec, actual: ModelSpec) -> None:
    if expected.family != actual.family or expected.variant != actual.variant:
        raise UnsupportedMLXModelError(
            "Loaded MLX model metadata does not match the configured model: "
            f"expected {expected.family.value}/{expected.variant.value}, got "
            f"{actual.family.value}/{actual.variant.value}."
        )
