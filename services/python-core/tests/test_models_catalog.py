from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models_catalog import (
    CATALOG,
    build_models_status,
    expected_voice_model_dir,
    migrate_model_storage,
    model_storage_status,
    reset_model_storage,
    save_custom_model_storage_base,
)
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

    @patch.dict("os.environ", {"AODCAST_HF_MODEL_BASE": "", "HF_HUB_CACHE": ""}, clear=False)
    def test_storage_status_reports_custom_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            store = ConfigStore(cwd / "config")
            store.bootstrap()
            custom = cwd / "external-models"
            save_custom_model_storage_base(store, custom)

            status = model_storage_status(store, cwd)

            self.assertEqual(status["current_base"], str(custom.resolve()))
            self.assertEqual(status["custom_base"], str(custom.resolve()))
            self.assertTrue(status["is_custom"])

    @patch.dict("os.environ", {"AODCAST_HF_MODEL_BASE": "", "HF_HUB_CACHE": ""}, clear=False)
    def test_reset_storage_clears_custom_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            store = ConfigStore(cwd / "config")
            store.bootstrap()
            save_custom_model_storage_base(store, cwd / "custom")

            status = reset_model_storage(store, cwd)

            self.assertFalse(status["is_custom"])
            self.assertEqual(status["custom_base"], "")

    @patch.dict("os.environ", {"AODCAST_HF_MODEL_BASE": "", "HF_HUB_CACHE": ""}, clear=False)
    def test_migrate_model_storage_moves_catalog_dirs_and_sets_custom_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            store = ConfigStore(cwd / "config")
            store.bootstrap()
            source_base = cwd / "source-models"
            save_custom_model_storage_base(store, source_base)
            entry = CATALOG[0]
            source_dir = expected_voice_model_dir(cwd, entry.hf_repo_id or "", store)
            source_dir.mkdir(parents=True)
            (source_dir / "model.safetensors").write_text("weights", encoding="utf-8")
            destination = cwd / "new-models"

            result = migrate_model_storage(store, cwd, destination)

            moved_path = destination / source_dir.name / "model.safetensors"
            self.assertTrue(moved_path.exists())
            self.assertFalse(source_dir.exists())
            self.assertEqual(result["moved"], 1)
            self.assertEqual(model_storage_status(store, cwd)["current_base"], str(destination.resolve()))

    @patch.dict("os.environ", {"AODCAST_HF_MODEL_BASE": "", "HF_HUB_CACHE": ""}, clear=False)
    def test_migrate_model_storage_rejects_destination_inside_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            store = ConfigStore(cwd / "config")
            store.bootstrap()
            save_custom_model_storage_base(store, cwd / "source-models")
            source = Path(str(model_storage_status(store, cwd)["current_base"]))

            with self.assertRaises(ValueError):
                migrate_model_storage(store, cwd, source / "nested")


if __name__ == "__main__":
    unittest.main()
