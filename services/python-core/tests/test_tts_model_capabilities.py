from __future__ import annotations

import unittest

from app.providers.tts_api.base import SpeechBreak
from app.providers.tts_local_mlx.capabilities import (
    SupportLevel,
    UnsupportedTTSRequestError,
    capability_contract_for_model,
    capabilities_for_model,
    validate_request_capabilities,
)
from app.providers.tts_local_mlx.model_spec import (
    ModelVariant,
    UnsupportedMLXModelError,
    model_spec_from_loaded_model,
    model_spec_from_config,
    validate_loaded_model_spec,
)


class TTSModelCapabilitiesTests(unittest.TestCase):
    def _validate(self, config: dict[str, object], **overrides: object) -> None:
        values: dict[str, object] = {
            "voice": "",
            "speed": 1.0,
            "style_prompt": "",
            "reference_audio_path": "",
            "reference_text": "",
            "context_audio_path": "",
            "context_text": "",
            "breaks": (),
            "clone_mode": "auto",
        }
        values.update(overrides)
        validate_request_capabilities(model_spec_from_config(config), **values)  # type: ignore[arg-type]

    def test_capability_matrix_distinguishes_model_variants(self) -> None:
        qwen_base = capabilities_for_model(
            model_spec_from_config(
                {"model_type": "qwen3_tts", "tts_model_type": "base"}
            )
        )
        qwen_custom = capabilities_for_model(
            model_spec_from_config(
                {"model_type": "qwen3_tts", "tts_model_type": "custom_voice"}
            )
        )
        vox = capabilities_for_model(
            model_spec_from_config({"model_type": "voxcpm2"})
        )
        moss_spec = model_spec_from_config({"model_type": "moss_tts_local"})
        moss = capabilities_for_model(moss_spec)

        self.assertEqual(qwen_base.speaker_cloning, SupportLevel.NATIVE)
        self.assertEqual(qwen_base.style_instruction, SupportLevel.UNSUPPORTED)
        self.assertEqual(qwen_custom.speaker_cloning, SupportLevel.UNSUPPORTED)
        self.assertEqual(qwen_custom.style_instruction, SupportLevel.NATIVE)
        self.assertEqual(vox.clone_with_style, SupportLevel.NATIVE)
        self.assertEqual(vox.reference_with_context, SupportLevel.NATIVE)
        self.assertEqual(qwen_base.reference_with_context, SupportLevel.UNSUPPORTED)
        self.assertEqual(vox.explicit_breaks, SupportLevel.APPROXIMATED)
        self.assertEqual(moss.explicit_breaks, SupportLevel.NATIVE)
        self.assertEqual(moss.channels, 2)
        self.assertEqual(
            set(moss.feature_levels()),
            {
                "speaker_cloning",
                "style_instruction",
                "emotion",
                "energy",
                "pace",
                "emphasis",
                "explicit_breaks",
                "pronunciation",
                "deterministic_seed",
                "text_context",
                "audio_context",
                "voice_conversion",
            },
        )

        contract = capability_contract_for_model("moss-local", moss_spec).to_dict()
        self.assertEqual(contract["schema_version"], 1)
        self.assertEqual(contract["platforms"], ["macos_apple_silicon"])
        self.assertEqual(contract["output_audio_formats"], ["wav"])

    def test_qwen_base_rejects_style_instead_of_silently_ignoring_it(self) -> None:
        with self.assertRaisesRegex(UnsupportedTTSRequestError, "style instructions"):
            self._validate(
                {"model_type": "qwen3_tts", "tts_model_type": "base"},
                style_prompt="Speak happily.",
            )

    def test_non_default_speed_is_rejected_when_model_cannot_honor_it(self) -> None:
        with self.assertRaisesRegex(UnsupportedTTSRequestError, "speed control"):
            self._validate({"model_type": "voxcpm2"}, speed=0.9)

    def test_voxcpm_ultimate_clone_rejects_style_control(self) -> None:
        with self.assertRaisesRegex(UnsupportedTTSRequestError, "cannot be combined"):
            self._validate(
                {"model_type": "voxcpm2"},
                reference_audio_path="speaker.wav",
                reference_text="Reference transcript.",
                style_prompt="Calm and reflective.",
                clone_mode="ultimate",
            )

    def test_only_voxcpm_combines_speaker_reference_with_audio_context(self) -> None:
        self._validate(
            {"model_type": "voxcpm2"},
            reference_audio_path="speaker.wav",
            reference_text="Speaker transcript.",
            context_audio_path="previous.wav",
            context_text="Previous segment.",
        )
        with self.assertRaisesRegex(
            UnsupportedTTSRequestError,
            "cannot combine a speaker reference with audio context",
        ):
            self._validate(
                {"model_type": "qwen3_tts", "tts_model_type": "base"},
                reference_audio_path="speaker.wav",
                reference_text="Speaker transcript.",
                context_audio_path="previous.wav",
                context_text="Previous segment.",
            )

    def test_moss_accepts_structured_breaks_but_rejects_style(self) -> None:
        self._validate(
            {"model_type": "moss_tts_delay"},
            breaks=(SpeechBreak(offset=2, duration_ms=400),),
        )
        with self.assertRaisesRegex(UnsupportedTTSRequestError, "style instructions"):
            self._validate(
                {"model_type": "moss_tts_delay"},
                style_prompt="Energetic.",
            )

    def test_loaded_model_metadata_must_match_configured_family(self) -> None:
        expected = model_spec_from_config({"model_type": "voxcpm2"})
        actual = model_spec_from_config({"model_type": "moss_tts_delay"})

        with self.assertRaisesRegex(UnsupportedMLXModelError, "does not match"):
            validate_loaded_model_spec(expected, actual)

    def test_qwen_variant_is_read_from_model_config(self) -> None:
        spec = model_spec_from_config(
            {"model_type": "qwen3_tts", "tts_model_type": "voice_design"}
        )
        self.assertEqual(spec.variant, ModelVariant.QWEN_VOICE_DESIGN)

    def test_loaded_voxcpm_uses_model_module_when_args_filter_model_type(self) -> None:
        model_class = type(
            "Model",
            (),
            {"__module__": "mlx_audio.tts.models.voxcpm2.voxcpm2"},
        )
        model = model_class()
        model.args = object()

        spec = model_spec_from_loaded_model(model)

        self.assertEqual(spec.variant, ModelVariant.VOXCPM2)


if __name__ == "__main__":
    unittest.main()
