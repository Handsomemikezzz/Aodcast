from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from app.domain.artifact import ArtifactRecord


class BridgeRequestStateSchemaTests(unittest.TestCase):
    def test_llm_provider_schemas_cover_codex_subscription_without_tokens(self) -> None:
        schemas_dir = Path(__file__).resolve().parents[3] / "packages/shared-schemas"
        config_schema = json.loads(
            (schemas_dir / "llm-provider-config.schema.json").read_text(encoding="utf-8")
        )
        status_schema = json.loads(
            (schemas_dir / "llm-provider-status.schema.json").read_text(encoding="utf-8")
        )
        auth_schema = json.loads(
            (schemas_dir / "llm-auth-start.schema.json").read_text(encoding="utf-8")
        )

        Draft202012Validator(config_schema).validate(
            {
                "provider": "codex_subscription",
                "model": "gpt-test",
                "reasoning_effort": "high",
                "base_url": "",
                "api_key": "",
            }
        )
        self.assertNotIn("access_token", status_schema["properties"])
        self.assertNotIn("refresh_token", status_schema["properties"])
        self.assertEqual(status_schema["properties"]["provider"]["const"], "codex_subscription")
        Draft202012Validator(auth_schema).validate(
            {
                "provider": "codex_subscription",
                "login_id": "login-1",
                "auth_url": "https://chatgpt.com/auth/codex?state=test",
            }
        )

    def test_episode_source_schema_covers_markdown_lineage(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "packages/shared-schemas/episode-source.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        for property_name in ["raw_markdown", "normalized_text", "content_hash", "version", "conversion_mode", "target_length"]:
            self.assertIn(property_name, schema["properties"])
            self.assertIn(property_name, schema["required"])
        self.assertEqual(schema["properties"]["conversion_mode"]["enum"], ["adapt", "narrate"])
        self.assertFalse(schema["additionalProperties"])

    def test_script_schema_constrains_optional_source_lineage(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "packages/shared-schemas/script.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        lineage = schema["$defs"]["sourceLineage"]

        self.assertEqual(
            set(lineage["required"]),
            {"source_id", "source_kind", "version", "content_hash", "conversion_mode", "target_length"},
        )
        self.assertEqual(schema["properties"]["generation_metadata"]["properties"]["source"]["$ref"], "#/$defs/sourceLineage")
        self.assertFalse(lineage["additionalProperties"])

    def test_bridge_request_state_schema_includes_run_token(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "packages/shared-schemas/bridge-request-state.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertIn("run_token", schema["properties"])
        self.assertEqual(schema["properties"]["run_token"]["type"], "string")
        self.assertEqual(schema["properties"]["run_token"]["minLength"], 1)
        self.assertFalse(schema["additionalProperties"])

    def test_bridge_request_state_schema_allows_voice_preview_result_fields(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "packages/shared-schemas/bridge-request-state.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        for property_name in ["task_id", "audio_path", "provider", "model", "settings"]:
            self.assertIn(property_name, schema["properties"])
        self.assertEqual(schema["properties"]["settings"]["type"], "object")
        self.assertIn("voice_id", schema["properties"]["settings"]["properties"])
        self.assertIn("preview_text", schema["properties"]["settings"]["properties"])

    def test_artifact_schema_allows_per_script_artifacts(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "packages/shared-schemas/artifact.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertIn("script_artifacts", schema["properties"])
        script_artifacts = schema["properties"]["script_artifacts"]
        self.assertEqual(script_artifacts["type"], "object")
        script_payload = schema["$defs"]["scriptArtifact"]
        self.assertIn("speaker_reference", schema["properties"])
        self.assertNotIn("voice_reference", schema["properties"])
        for property_name in ["transcript_path", "audio_path", "provider", "takes", "final_take_id", "voice_settings", "speaker_reference"]:
            self.assertIn(property_name, script_payload["properties"])
        self.assertNotIn("voice_reference", script_payload["properties"])
        speaker_reference_options = schema["properties"]["speaker_reference"]["oneOf"]
        self.assertIn({"type": "null"}, speaker_reference_options)
        self.assertIn(
            {"$ref": "https://aodcast.dev/schemas/speaker-reference.schema.json"},
            speaker_reference_options,
        )
        audio_take = schema["$defs"]["audioTake"]
        for property_name in ["speech_plan_id", "render_id"]:
            self.assertIn(property_name, audio_take["properties"])
            self.assertIn(property_name, audio_take["required"])
        self.assertFalse(script_payload["additionalProperties"])

    def test_default_artifact_record_round_trips_through_json_schema(self) -> None:
        schemas_dir = Path(__file__).resolve().parents[3] / "packages/shared-schemas"
        artifact_schema = json.loads(
            (schemas_dir / "artifact.schema.json").read_text(encoding="utf-8")
        )
        speaker_reference_schema = json.loads(
            (schemas_dir / "speaker-reference.schema.json").read_text(encoding="utf-8")
        )
        registry = Registry().with_resource(
            speaker_reference_schema["$id"],
            Resource.from_contents(speaker_reference_schema),
        )
        artifact = ArtifactRecord(
            session_id="session-schema-test",
            active_script_id="script-schema-test",
        )

        Draft202012Validator(artifact_schema, registry=registry).validate(
            artifact.to_dict()
        )
        self.assertIsNone(artifact.to_dict()["speaker_reference"])
        self.assertIsNone(
            artifact.to_dict()["script_artifacts"]["script-schema-test"][
                "speaker_reference"
            ]
        )

    def test_speaker_reference_schema_is_provider_neutral(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "packages/shared-schemas/speaker-reference.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        for property_name in ["speaker_reference_id", "name", "source", "audio_path", "audio_hash", "reference_text", "reference_hash"]:
            self.assertIn(property_name, schema["properties"])
            self.assertIn(property_name, schema["required"])
        for forbidden in ["provider", "model", "voice_id", "style_id", "speed", "preview_text"]:
            self.assertNotIn(forbidden, schema["properties"])
        self.assertEqual(schema["properties"]["source"]["enum"], ["built_in", "user_saved"])
        self.assertFalse(schema["additionalProperties"])

    def test_speech_plan_schema_has_versioned_positional_delivery_contract(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "packages/shared-schemas/speech-plan.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        for property_name in ["schema_version", "plan_id", "version", "script_hash", "plan_hash", "segments"]:
            self.assertIn(property_name, schema["required"])
        segment = schema["$defs"]["segment"]
        for property_name in ["source_span", "delivery", "breaks", "emphasis", "pronunciations", "pause_after_ms", "segment_hash"]:
            self.assertIn(property_name, segment["required"])
        for definition in ["directorMetadata", "sourceSpan", "delivery", "break", "emphasis", "pronunciation", "segment"]:
            self.assertFalse(schema["$defs"][definition]["additionalProperties"])
        self.assertFalse(schema["additionalProperties"])

    def test_render_manifest_schema_tracks_lineage_segments_and_assembly(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "packages/shared-schemas/render-manifest.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        for property_name in ["script_hash", "speech_plan", "speaker_reference", "pipeline", "parent_render_id", "regeneration", "segments", "assembly", "output"]:
            self.assertIn(property_name, schema["required"])
        segment = schema["$defs"]["segmentArtifact"]
        for property_name in ["segment_artifact_id", "segment_id", "segment_hash", "audio_hash", "generated_by_render_id"]:
            self.assertIn(property_name, segment["required"])
        self.assertEqual(schema["$defs"]["regeneration"]["properties"]["mode"]["const"], "context_window")
        self.assertEqual(
            schema["$defs"]["regeneration"]["properties"]["window_segment_ids"]["minItems"],
            1,
        )
        assembly = schema["$defs"]["assembly"]
        for property_name in ["target_rms_dbfs", "peak_ceiling_dbfs", "edge_fade_ms"]:
            self.assertIn(property_name, assembly["required"])
            self.assertIn(property_name, assembly["properties"])
        for removed_name in ["target_lufs", "true_peak_dbfs", "crossfade_ms"]:
            self.assertNotIn(removed_name, assembly["properties"])
        for definition in ["speechPlanReference", "speakerReferenceSnapshot", "pipelineStage", "regeneration", "segmentArtifact", "assembly", "output"]:
            self.assertFalse(schema["$defs"][definition]["additionalProperties"])
        self.assertFalse(schema["additionalProperties"])

    def test_tts_model_capability_schema_requires_explicit_support_levels(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "packages/shared-schemas/tts-model-capability.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        self.assertEqual(
            schema["$defs"]["supportLevel"]["enum"],
            ["native", "approximated", "unsupported"],
        )
        capabilities = schema["$defs"]["capabilities"]
        for property_name in ["speaker_cloning", "emotion", "pace", "explicit_breaks", "text_context", "audio_context", "voice_conversion"]:
            self.assertIn(property_name, capabilities["required"])
        self.assertFalse(capabilities["additionalProperties"])
        self.assertFalse(schema["$defs"]["limits"]["additionalProperties"])
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
