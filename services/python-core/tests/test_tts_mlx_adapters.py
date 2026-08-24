from __future__ import annotations

import unittest

from app.providers.tts_api.base import SpeechBreak
from app.providers.tts_local_mlx.adapters.base import AdapterRequest
from app.providers.tts_local_mlx.adapters.moss import MossTTSAdapter
from app.providers.tts_local_mlx.adapters.qwen3 import Qwen3TTSAdapter
from app.providers.tts_local_mlx.adapters.voxcpm2 import VoxCPM2Adapter
from app.providers.tts_local_mlx.chunker import split_script_into_chunks
from app.providers.tts_local_mlx.model_spec import model_spec_from_config


class MLXTTSAdapterTests(unittest.TestCase):
    def test_qwen_base_selects_xvector_or_icl_clone_from_clone_mode(self) -> None:
        adapter = Qwen3TTSAdapter(
            model_spec_from_config(
                {"model_type": "qwen3_tts", "tts_model_type": "base"}
            )
        )
        speaker_kwargs = adapter.generation_kwargs(
            "Target text.",
            AdapterRequest(
                reference_audio_path="speaker.wav",
                reference_text="Reference text.",
                clone_mode="speaker",
            ),
        )
        ultimate_kwargs = adapter.generation_kwargs(
            "Target text.",
            AdapterRequest(
                reference_audio_path="speaker.wav",
                reference_text="Reference text.",
                clone_mode="ultimate",
            ),
        )

        self.assertEqual(speaker_kwargs["ref_audio"], "speaker.wav")
        self.assertNotIn("ref_text", speaker_kwargs)
        self.assertEqual(ultimate_kwargs["ref_text"], "Reference text.")
        self.assertEqual(ultimate_kwargs["lang_code"], "chinese")

    def test_voxcpm_auto_uses_controllable_clone_when_style_is_present(self) -> None:
        adapter = VoxCPM2Adapter(model_spec_from_config({"model_type": "voxcpm2"}))
        kwargs = adapter.generation_kwargs(
            "Target text.",
            AdapterRequest(
                reference_audio_path="speaker.wav",
                reference_text="Reference text.",
                style_prompt="Calm and warm.",
            ),
        )

        self.assertEqual(kwargs["ref_audio"], "speaker.wav")
        self.assertEqual(kwargs["instruct"], "Calm and warm.")
        self.assertNotIn("prompt_audio", kwargs)
        self.assertNotIn("prompt_text", kwargs)

    def test_voxcpm_uses_bounded_generation_defaults(self) -> None:
        adapter = VoxCPM2Adapter(model_spec_from_config({"model_type": "voxcpm2"}))

        short_kwargs = adapter.generation_kwargs("短句。", AdapterRequest())
        long_kwargs = adapter.generation_kwargs("长" * 300, AdapterRequest())

        self.assertEqual(short_kwargs["inference_timesteps"], 7)
        self.assertEqual(short_kwargs["cfg_value"], 2.0)
        self.assertEqual(short_kwargs["max_tokens"], 64)
        self.assertEqual(long_kwargs["max_tokens"], 600)

    def test_voxcpm_further_bounds_provider_chunks(self) -> None:
        adapter = VoxCPM2Adapter(model_spec_from_config({"model_type": "voxcpm2"}))
        text = "长" * 280

        prepared = adapter.prepare_synthesis(text, (), split_script_into_chunks)

        self.assertGreater(len(prepared.segments), 1)
        self.assertTrue(all(len(segment.text) <= 120 for segment in prepared.segments))
        self.assertEqual("".join(segment.text for segment in prepared.segments), text)

    def test_voxcpm_ultimate_uses_same_audio_for_prompt_and_reference(self) -> None:
        adapter = VoxCPM2Adapter(model_spec_from_config({"model_type": "voxcpm2"}))
        kwargs = adapter.generation_kwargs(
            "Target text.",
            AdapterRequest(
                reference_audio_path="speaker.wav",
                reference_text="Exact transcript.",
                clone_mode="ultimate",
            ),
        )

        self.assertEqual(kwargs["ref_audio"], "speaker.wav")
        self.assertEqual(kwargs["prompt_audio"], "speaker.wav")
        self.assertEqual(kwargs["prompt_text"], "Exact transcript.")
        self.assertNotIn("ref_text", kwargs)

    def test_voxcpm_keeps_original_reference_when_using_previous_context(self) -> None:
        adapter = VoxCPM2Adapter(model_spec_from_config({"model_type": "voxcpm2"}))
        request = AdapterRequest(
            reference_audio_path="speaker.wav",
            reference_text="Speaker transcript.",
            context_audio_path="previous.wav",
            context_text="Previous segment.",
            style_prompt="Calm and natural.",
        )

        adapter.validate_request(request, ())
        kwargs = adapter.generation_kwargs("Target text.", request)

        self.assertEqual(kwargs["ref_audio"], "speaker.wav")
        self.assertEqual(kwargs["prompt_audio"], "previous.wav")
        self.assertEqual(kwargs["prompt_text"], "Previous segment.")
        self.assertEqual(kwargs["instruct"], "Calm and natural.")

    def test_context_only_conditioning_maps_to_qwen_and_moss(self) -> None:
        qwen = Qwen3TTSAdapter(
            model_spec_from_config(
                {"model_type": "qwen3_tts", "tts_model_type": "base"}
            )
        )
        moss = MossTTSAdapter(
            model_spec_from_config({"model_type": "moss_tts_delay"})
        )
        request = AdapterRequest(
            context_audio_path="previous.wav",
            context_text="Previous segment.",
        )

        qwen.validate_request(request, ())
        moss.validate_request(request, ())
        qwen_kwargs = qwen.generation_kwargs("Target text.", request)
        moss_kwargs = moss.generation_kwargs("Target text.", request)

        self.assertEqual(qwen_kwargs["ref_audio"], "previous.wav")
        self.assertEqual(qwen_kwargs["ref_text"], "Previous segment.")
        self.assertEqual(moss_kwargs["ref_audio"], "previous.wav")
        self.assertEqual(moss_kwargs["ref_text"], "Previous segment.")
        self.assertEqual(moss_kwargs["mode"], "continuation")

    def test_moss_expands_structured_break_without_mutating_script(self) -> None:
        adapter = MossTTSAdapter(
            model_spec_from_config({"model_type": "moss_tts_delay"})
        )
        script = "前半句，后半句。"
        prepared = adapter.prepare_synthesis(
            script,
            (SpeechBreak(offset=4, duration_ms=400),),
            split_script_into_chunks,
        )

        provider_text = "".join(segment.text for segment in prepared.segments)
        self.assertEqual(script, "前半句，后半句。")
        self.assertIn("[pause 0.4s]", provider_text)
        self.assertTrue(all(segment.pause_after_ms == 0 for segment in prepared.segments))

    def test_non_moss_breaks_become_deterministic_pcm_pause(self) -> None:
        adapter = VoxCPM2Adapter(model_spec_from_config({"model_type": "voxcpm2"}))
        prepared = adapter.prepare_synthesis(
            "第一句。第二句。",
            (SpeechBreak(offset=4, duration_ms=650),),
            split_script_into_chunks,
        )

        self.assertEqual(prepared.segments[0].pause_after_ms, 650)
        self.assertNotIn("pause", "".join(item.text for item in prepared.segments))

    def test_moss_rejects_provider_markup_in_source_text(self) -> None:
        adapter = MossTTSAdapter(
            model_spec_from_config({"model_type": "moss_tts_delay"})
        )
        with self.assertRaisesRegex(ValueError, "Raw MOSS pause markers"):
            adapter.prepare_synthesis(
                "正文[pause 1.0s]正文",
                (),
                split_script_into_chunks,
            )


if __name__ == "__main__":
    unittest.main()
