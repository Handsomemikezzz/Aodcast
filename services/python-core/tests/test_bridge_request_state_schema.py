from __future__ import annotations

import json
import unittest
from pathlib import Path


class BridgeRequestStateSchemaTests(unittest.TestCase):
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
        self.assertIn("voice_reference", schema["properties"])
        for property_name in ["transcript_path", "audio_path", "provider", "takes", "final_take_id", "voice_settings", "voice_reference"]:
            self.assertIn(property_name, script_payload["properties"])
        voice_reference = schema["$defs"]["voiceReference"]
        for property_name in ["lock_id", "audio_path", "preview_text", "provider", "model", "voice_id", "style_id", "created_at"]:
            self.assertIn(property_name, voice_reference["properties"])
        self.assertFalse(script_payload["additionalProperties"])

    def test_voice_profile_schema_matches_reusable_profile_contract(self) -> None:
        schema_path = Path(__file__).resolve().parents[3] / "packages/shared-schemas/voice-profile.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        for property_name in ["voice_profile_id", "name", "source", "audio_path", "preview_text", "reference_text", "provider", "model"]:
            self.assertIn(property_name, schema["properties"])
            self.assertIn(property_name, schema["required"])
        self.assertEqual(schema["properties"]["source"]["enum"], ["built_in", "user_saved"])
        self.assertFalse(schema["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
