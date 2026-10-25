from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.domain.tts_config import (
    DEFAULT_LOCAL_CLONE_MODEL,
    DEFAULT_LOCAL_TTS_MODEL,
    KOKORO_TTS_MODEL,
    LOCAL_CLONE_MODELS,
    TTSProviderConfig,
)
from app.models_catalog import CATALOG, build_models_status, resolve_voice_model_id
from app.storage.config_store import ConfigStore


class ModelsCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.cwd = Path(self.directory.name)
        self.store = ConfigStore(self.cwd / "config")
        self.store.bootstrap()
        self.store.save_tts_config(TTSProviderConfig(provider="local_http"))

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_catalog_lists_only_service_models(self) -> None:
        self.assertEqual(
            [entry.hf_repo_id for entry in CATALOG],
            [DEFAULT_LOCAL_TTS_MODEL, *LOCAL_CLONE_MODELS, KOKORO_TTS_MODEL],
        )
        self.assertEqual(
            [entry.hf_repo_id for entry in CATALOG if entry.hf_repo_id in LOCAL_CLONE_MODELS and entry.default_for_mode],
            [DEFAULT_LOCAL_CLONE_MODEL],
        )
        self.assertEqual(resolve_voice_model_id(DEFAULT_LOCAL_TTS_MODEL), DEFAULT_LOCAL_TTS_MODEL)
        with self.assertRaises(ValueError):
            resolve_voice_model_id("unknown-model")

    def status(
        self, available: bool, current_model: str, clone_models: tuple[str, ...] = LOCAL_CLONE_MODELS
    ) -> list[dict[str, object]]:
        capability = SimpleNamespace(to_dict=lambda: {
            "available": available,
            "current_model": current_model,
            "clone_models": list(clone_models) if available else [],
            "max_reference_duration_ms": 30000 if available else None,
            "reasons": [] if available else ["Start the speech service."],
        })
        with patch("app.models_catalog.detect_local_speech_capability", return_value=capability):
            return {row["hf_repo_id"]: row for row in build_models_status(self.store, self.cwd)}

    def test_ready_tracks_service_health_and_configured_model(self) -> None:
        rows = self.status(True, DEFAULT_LOCAL_TTS_MODEL)
        self.assertTrue(rows[DEFAULT_LOCAL_TTS_MODEL]["ready"])
        self.assertTrue(rows[DEFAULT_LOCAL_TTS_MODEL]["active"])
        self.assertFalse(rows[KOKORO_TTS_MODEL]["ready"])
        self.assertTrue(all(row["provider"] == "local_http" and "capabilities" in row for row in rows.values()))
        self.assertTrue(all(not {"downloaded", "downloading", "path", "size_mb"}.intersection(row) for row in rows.values()))
        self.assertFalse((self.cwd / "models").exists())

    def test_unreachable_service_has_no_ready_models(self) -> None:
        rows = self.status(False, DEFAULT_LOCAL_TTS_MODEL)
        self.assertTrue(all(not row["ready"] for row in rows.values()))
        self.assertIn("Start the speech service", str(rows[DEFAULT_LOCAL_TTS_MODEL]["unavailable_reason"]))

    def test_service_model_change_does_not_claim_other_model_is_ready(self) -> None:
        rows = self.status(True, KOKORO_TTS_MODEL)
        self.assertFalse(rows[DEFAULT_LOCAL_TTS_MODEL]["ready"])
        self.assertTrue(rows[KOKORO_TTS_MODEL]["ready"])

    def test_clone_models_are_ready_alongside_the_preset_model(self) -> None:
        rows = self.status(True, DEFAULT_LOCAL_TTS_MODEL)
        for model in LOCAL_CLONE_MODELS:
            self.assertTrue(rows[model]["ready"])
            contract = rows[model]["capabilities"]
            self.assertEqual(contract["capabilities"]["speaker_cloning"], "native")
            self.assertEqual(contract["capabilities"]["audio_context"], "unsupported")
            self.assertEqual(contract["limits"]["max_reference_duration_ms"], 30000)
        preset = rows[DEFAULT_LOCAL_TTS_MODEL]
        self.assertEqual(preset["capabilities"]["capabilities"]["speaker_cloning"], "unsupported")
        self.assertIsNone(preset["capabilities"]["limits"]["max_reference_duration_ms"])

    def test_service_without_clone_models_does_not_claim_cloning(self) -> None:
        rows = self.status(True, DEFAULT_LOCAL_TTS_MODEL, clone_models=())
        for model in LOCAL_CLONE_MODELS:
            self.assertFalse(rows[model]["ready"])
            self.assertIn("Restart the speech service", str(rows[model]["unavailable_reason"]))


if __name__ == "__main__":
    unittest.main()
