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


if __name__ == "__main__":
    unittest.main()
