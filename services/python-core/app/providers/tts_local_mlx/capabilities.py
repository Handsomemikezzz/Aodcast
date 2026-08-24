from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from app.providers.tts_api.base import SpeechBreak
from app.providers.tts_local_mlx.model_spec import (
    ModelFamily,
    ModelSpec,
    ModelVariant,
)
from app.providers.tts_local_mlx.version import LOCAL_MLX_ADAPTER_VERSION


class SupportLevel(StrEnum):
    NATIVE = "native"
    APPROXIMATED = "approximated"
    UNSUPPORTED = "unsupported"


class CloneMode(StrEnum):
    AUTO = "auto"
    NONE = "none"
    SPEAKER = "speaker"
    CONTROLLABLE = "controllable"
    ULTIMATE = "ultimate"
    CONTINUATION = "continuation"


class UnsupportedTTSRequestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    family: ModelFamily
    variant: ModelVariant
    speaker_cloning: SupportLevel
    style_instruction: SupportLevel
    emotion: SupportLevel
    energy: SupportLevel
    pace: SupportLevel
    emphasis: SupportLevel
    explicit_breaks: SupportLevel
    pronunciation: SupportLevel
    deterministic_seed: SupportLevel
    text_context: SupportLevel
    audio_context: SupportLevel
    voice_conversion: SupportLevel
    clone_with_style: SupportLevel
    reference_with_context: SupportLevel
    speed_control: SupportLevel
    continuation: SupportLevel
    streaming: SupportLevel
    requires_reference_text: bool
    sample_rate_hz: int
    channels: int

    def feature_levels(self) -> dict[str, str]:
        """Return the capability fields defined by the shared contract."""

        return {
            "speaker_cloning": self.speaker_cloning.value,
            "style_instruction": self.style_instruction.value,
            "emotion": self.emotion.value,
            "energy": self.energy.value,
            "pace": self.pace.value,
            "emphasis": self.emphasis.value,
            "explicit_breaks": self.explicit_breaks.value,
            "pronunciation": self.pronunciation.value,
            "deterministic_seed": self.deterministic_seed.value,
            "text_context": self.text_context.value,
            "audio_context": self.audio_context.value,
            "voice_conversion": self.voice_conversion.value,
        }


@dataclass(frozen=True, slots=True)
class TTSModelCapabilityContract:
    model: str
    capabilities: ModelCapabilities
    schema_version: int = 1
    provider: str = "local_mlx"
    runtime: str = "mlx"
    adapter_version: str = LOCAL_MLX_ADAPTER_VERSION
    platforms: tuple[str, ...] = ("macos_apple_silicon",)
    languages: tuple[str, ...] = ("zh",)
    reference_audio_formats: tuple[str, ...] = ("wav", "mp3", "m4a", "flac")
    output_audio_formats: tuple[str, ...] = ("wav",)
    max_reference_duration_ms: int | None = 600_000
    max_segment_characters: int | None = 320

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "model": self.model,
            "runtime": self.runtime,
            "adapter_version": self.adapter_version,
            "platforms": list(self.platforms),
            "languages": list(self.languages),
            "reference_audio_formats": list(self.reference_audio_formats),
            "output_audio_formats": list(self.output_audio_formats),
            "capabilities": self.capabilities.feature_levels(),
            "limits": {
                "max_reference_duration_ms": self.max_reference_duration_ms,
                "max_segment_characters": self.max_segment_characters,
            },
        }


def capability_contract_for_model(
    model: str,
    spec: ModelSpec,
) -> TTSModelCapabilityContract:
    return TTSModelCapabilityContract(
        model=model,
        capabilities=capabilities_for_model(spec),
    )


def capabilities_for_model(spec: ModelSpec) -> ModelCapabilities:
    shared = {
        "family": spec.family,
        "variant": spec.variant,
        "speed_control": SupportLevel.UNSUPPORTED,
        "sample_rate_hz": spec.sample_rate_hz,
        "channels": spec.channels,
    }
    if spec.variant == ModelVariant.QWEN_BASE:
        return ModelCapabilities(
            **shared,
            speaker_cloning=SupportLevel.NATIVE,
            style_instruction=SupportLevel.UNSUPPORTED,
            emotion=SupportLevel.UNSUPPORTED,
            energy=SupportLevel.UNSUPPORTED,
            pace=SupportLevel.UNSUPPORTED,
            emphasis=SupportLevel.UNSUPPORTED,
            explicit_breaks=SupportLevel.APPROXIMATED,
            pronunciation=SupportLevel.UNSUPPORTED,
            deterministic_seed=SupportLevel.UNSUPPORTED,
            text_context=SupportLevel.NATIVE,
            audio_context=SupportLevel.NATIVE,
            voice_conversion=SupportLevel.UNSUPPORTED,
            clone_with_style=SupportLevel.UNSUPPORTED,
            reference_with_context=SupportLevel.UNSUPPORTED,
            continuation=SupportLevel.UNSUPPORTED,
            streaming=SupportLevel.NATIVE,
            requires_reference_text=False,
        )
    if spec.variant in {
        ModelVariant.QWEN_CUSTOM_VOICE,
        ModelVariant.QWEN_VOICE_DESIGN,
    }:
        return ModelCapabilities(
            **shared,
            speaker_cloning=SupportLevel.UNSUPPORTED,
            style_instruction=SupportLevel.NATIVE,
            emotion=SupportLevel.NATIVE,
            energy=SupportLevel.APPROXIMATED,
            pace=SupportLevel.APPROXIMATED,
            emphasis=SupportLevel.APPROXIMATED,
            explicit_breaks=SupportLevel.APPROXIMATED,
            pronunciation=SupportLevel.UNSUPPORTED,
            deterministic_seed=SupportLevel.UNSUPPORTED,
            text_context=SupportLevel.UNSUPPORTED,
            audio_context=SupportLevel.UNSUPPORTED,
            voice_conversion=SupportLevel.UNSUPPORTED,
            clone_with_style=SupportLevel.UNSUPPORTED,
            reference_with_context=SupportLevel.UNSUPPORTED,
            continuation=SupportLevel.UNSUPPORTED,
            streaming=SupportLevel.NATIVE,
            requires_reference_text=False,
        )
    if spec.family == ModelFamily.VOXCPM2:
        return ModelCapabilities(
            **shared,
            speaker_cloning=SupportLevel.NATIVE,
            style_instruction=SupportLevel.NATIVE,
            emotion=SupportLevel.NATIVE,
            energy=SupportLevel.APPROXIMATED,
            pace=SupportLevel.NATIVE,
            emphasis=SupportLevel.APPROXIMATED,
            explicit_breaks=SupportLevel.APPROXIMATED,
            pronunciation=SupportLevel.UNSUPPORTED,
            deterministic_seed=SupportLevel.UNSUPPORTED,
            text_context=SupportLevel.NATIVE,
            audio_context=SupportLevel.NATIVE,
            voice_conversion=SupportLevel.UNSUPPORTED,
            clone_with_style=SupportLevel.NATIVE,
            reference_with_context=SupportLevel.NATIVE,
            continuation=SupportLevel.NATIVE,
            streaming=SupportLevel.UNSUPPORTED,
            requires_reference_text=False,
        )
    if spec.family == ModelFamily.MOSS:
        return ModelCapabilities(
            **shared,
            speaker_cloning=SupportLevel.NATIVE,
            style_instruction=SupportLevel.UNSUPPORTED,
            emotion=SupportLevel.UNSUPPORTED,
            energy=SupportLevel.UNSUPPORTED,
            pace=SupportLevel.UNSUPPORTED,
            emphasis=SupportLevel.UNSUPPORTED,
            explicit_breaks=SupportLevel.NATIVE,
            pronunciation=SupportLevel.NATIVE,
            deterministic_seed=SupportLevel.UNSUPPORTED,
            text_context=SupportLevel.NATIVE,
            audio_context=SupportLevel.NATIVE,
            voice_conversion=SupportLevel.UNSUPPORTED,
            clone_with_style=SupportLevel.UNSUPPORTED,
            reference_with_context=SupportLevel.UNSUPPORTED,
            continuation=SupportLevel.NATIVE,
            streaming=(
                SupportLevel.NATIVE
                if spec.variant == ModelVariant.MOSS_LOCAL
                else SupportLevel.UNSUPPORTED
            ),
            requires_reference_text=False,
        )
    raise AssertionError(f"Unhandled MLX model specification: {spec}")


def normalize_clone_mode(value: str) -> CloneMode:
    normalized = str(value or CloneMode.AUTO).strip().lower()
    try:
        return CloneMode(normalized)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in CloneMode)
        raise UnsupportedTTSRequestError(
            f"Unknown clone_mode '{value}'. Allowed values: {allowed}."
        ) from exc


def validate_request_capabilities(
    spec: ModelSpec,
    *,
    voice: str,
    speed: float,
    style_prompt: str,
    reference_audio_path: str,
    reference_text: str,
    context_audio_path: str,
    context_text: str,
    breaks: tuple[SpeechBreak, ...],
    clone_mode: str,
) -> CloneMode:
    capabilities = capabilities_for_model(spec)
    mode = normalize_clone_mode(clone_mode)
    has_reference = bool(reference_audio_path.strip())
    has_context = bool(context_audio_path.strip())
    has_style = bool(style_prompt.strip())

    if reference_text.strip() and not has_reference:
        raise UnsupportedTTSRequestError(
            "reference_text requires reference_audio_path."
        )
    if context_text.strip() and not has_context:
        raise UnsupportedTTSRequestError(
            "context_text requires context_audio_path."
        )
    if has_context and not context_text.strip():
        raise UnsupportedTTSRequestError(
            "context_audio_path requires the exact context transcript."
        )
    if has_context and capabilities.audio_context == SupportLevel.UNSUPPORTED:
        raise UnsupportedTTSRequestError(
            f"{spec.family.value}/{spec.variant.value} does not support audio context."
        )
    if (
        has_reference
        and has_context
        and capabilities.reference_with_context == SupportLevel.UNSUPPORTED
    ):
        raise UnsupportedTTSRequestError(
            f"{spec.family.value}/{spec.variant.value} cannot combine a speaker reference with audio context."
        )
    if not math.isclose(float(speed), 1.0, rel_tol=0.0, abs_tol=1e-6):
        if capabilities.speed_control == SupportLevel.UNSUPPORTED:
            raise UnsupportedTTSRequestError(
                f"{spec.family.value}/{spec.variant.value} does not support speed control."
            )
    if has_style and capabilities.style_instruction == SupportLevel.UNSUPPORTED:
        raise UnsupportedTTSRequestError(
            f"{spec.family.value}/{spec.variant.value} does not support style instructions."
        )
    if has_reference and capabilities.speaker_cloning == SupportLevel.UNSUPPORTED:
        raise UnsupportedTTSRequestError(
            f"{spec.family.value}/{spec.variant.value} does not support voice cloning."
        )
    if has_reference and has_style and capabilities.clone_with_style == SupportLevel.UNSUPPORTED:
        raise UnsupportedTTSRequestError(
            f"{spec.family.value}/{spec.variant.value} cannot combine voice cloning with style control."
        )
    if breaks and capabilities.explicit_breaks == SupportLevel.UNSUPPORTED:
        raise UnsupportedTTSRequestError(
            f"{spec.family.value}/{spec.variant.value} does not support planned pauses."
        )

    has_conditioning = has_reference or has_context
    conditioning_text = reference_text.strip() if has_reference else context_text.strip()
    if mode == CloneMode.NONE and has_conditioning:
        raise UnsupportedTTSRequestError(
            "clone_mode 'none' cannot be used with reference or context audio."
        )
    if mode not in {CloneMode.AUTO, CloneMode.NONE} and not has_conditioning:
        raise UnsupportedTTSRequestError(
            f"clone_mode '{mode.value}' requires reference or context audio."
        )

    if spec.variant == ModelVariant.QWEN_BASE:
        if mode not in {
            CloneMode.AUTO,
            CloneMode.NONE,
            CloneMode.SPEAKER,
            CloneMode.ULTIMATE,
        }:
            raise UnsupportedTTSRequestError(
                f"Qwen3-TTS Base does not support clone_mode '{mode.value}'."
            )
        if mode == CloneMode.ULTIMATE and not conditioning_text:
            raise UnsupportedTTSRequestError(
                "Qwen3-TTS ultimate cloning requires the exact reference transcript."
            )
    elif spec.variant == ModelVariant.QWEN_CUSTOM_VOICE:
        if mode not in {CloneMode.AUTO, CloneMode.NONE}:
            raise UnsupportedTTSRequestError(
                "Qwen3-TTS CustomVoice does not accept clone modes."
            )
        if not voice.strip():
            raise UnsupportedTTSRequestError(
                "Qwen3-TTS CustomVoice requires a preset voice name."
            )
    elif spec.variant == ModelVariant.QWEN_VOICE_DESIGN:
        if mode not in {CloneMode.AUTO, CloneMode.NONE}:
            raise UnsupportedTTSRequestError(
                "Qwen3-TTS VoiceDesign does not accept clone modes."
            )
        if not has_style:
            raise UnsupportedTTSRequestError(
                "Qwen3-TTS VoiceDesign requires a voice description in style_prompt."
            )
    elif spec.family == ModelFamily.VOXCPM2:
        if mode not in {
            CloneMode.AUTO,
            CloneMode.NONE,
            CloneMode.SPEAKER,
            CloneMode.CONTROLLABLE,
            CloneMode.ULTIMATE,
            CloneMode.CONTINUATION,
        }:
            raise UnsupportedTTSRequestError(
                f"VoxCPM2 does not support clone_mode '{mode.value}'."
            )
        if mode in {CloneMode.ULTIMATE, CloneMode.CONTINUATION}:
            if not conditioning_text:
                raise UnsupportedTTSRequestError(
                    f"VoxCPM2 {mode.value} cloning requires the exact reference transcript."
                )
            if has_style:
                raise UnsupportedTTSRequestError(
                    f"VoxCPM2 {mode.value} cloning cannot be combined with style control."
                )
        if mode == CloneMode.CONTROLLABLE and not has_style:
            raise UnsupportedTTSRequestError(
                "VoxCPM2 controllable cloning requires a style instruction."
            )
    elif spec.family == ModelFamily.MOSS:
        if mode not in {
            CloneMode.AUTO,
            CloneMode.NONE,
            CloneMode.SPEAKER,
            CloneMode.CONTINUATION,
        }:
            raise UnsupportedTTSRequestError(
                f"MOSS-TTS does not support clone_mode '{mode.value}'."
            )
        if mode == CloneMode.CONTINUATION and not conditioning_text:
            raise UnsupportedTTSRequestError(
                "MOSS-TTS continuation requires the exact reference transcript."
            )
    return mode
