from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.models_catalog import CATALOG, build_models_status, expected_voice_model_dir
from app.storage.config_store import ConfigStore


class ModelsCatalogTests(unittest.TestCase):
    def test_catalog_voicebox_ids(self) -> None:
        names = [e.model_name for e in CATALOG]
        self.assertIn("qwen-tts-1.7B", names)
        self.assertIn("qwen-tts-0.6B", names)
        self.assertTrue(all(name.startswith("qwen-tts-") for name in names))

    def test_list_models_status_returns_all_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config_dir = cwd / "config"
            config_dir.mkdir()
            store = ConfigStore(config_dir)
            store.bootstrap()
            rows = build_models_status(store, cwd)
            self.assertEqual(len(rows), len(CATALOG))
            self.assertTrue(all("model_name" in r and "downloaded" in r for r in rows))

    def test_expected_voice_dir_naming(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            d = expected_voice_model_dir(cwd, "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit")
            self.assertTrue(str(d).endswith("Qwen3-TTS-12Hz-0.6B-Base-8bit"))


if __name__ == "__main__":
    unittest.main()
