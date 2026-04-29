from __future__ import annotations

import json
import unittest
from pathlib import Path


class BridgeRequestStateSchemaTests(unittest.TestCase):
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
        for property_name in ["transcript_path", "audio_path", "provider", "takes", "final_take_id", "voice_settings"]:
            self.assertIn(property_name, script_payload["properties"])
        self.assertFalse(script_payload["additionalProperties"])


if __name__ == "__main__":
    unittest.main()
