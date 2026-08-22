from __future__ import annotations

import unittest

from tests.http_contract_helpers import APP_PATH, REPO_ROOT


STUDIO_PAGE_PATH = REPO_ROOT / "apps/desktop/src/pages/studio/StudioPage.tsx"
STUDIO_HEADER_PATH = REPO_ROOT / "apps/desktop/src/pages/studio/StudioHeader.tsx"
EPISODE_INSPECTOR_PATH = REPO_ROOT / "apps/desktop/src/pages/studio/EpisodeInspector.tsx"
EPISODE_AUDIO_DOCK_PATH = REPO_ROOT / "apps/desktop/src/pages/studio/EpisodeAudioDock.tsx"
SCRIPT_WORKBENCH_DATA_PATH = REPO_ROOT / "apps/desktop/src/pages/script-workbench/useScriptWorkbenchData.ts"
SCRIPT_WORKBENCH_AUDIO_PATH = REPO_ROOT / "apps/desktop/src/pages/script-workbench/useScriptWorkbenchAudio.ts"


class EpisodeWorkspaceSourceTests(unittest.TestCase):
    def test_app_routes_episodes_into_workspace_without_top_level_studio_navigation(self) -> None:
        app_source = APP_PATH.read_text(encoding="utf-8")

        self.assertIn('path="/studio/:sessionId/:scriptId"', app_source)
        self.assertNotIn('to="/studio"', app_source)
        self.assertNotIn('>Studio</span>', app_source)
        self.assertNotIn("session.state.replace", app_source)

    def test_workspace_header_uses_product_status_without_stepper(self) -> None:
        source = STUDIO_HEADER_PATH.read_text(encoding="utf-8")

        self.assertIn("EpisodeProductStatus", source)
        self.assertIn("Back to Episodes", source)
        self.assertIn("Conversation", source)
        self.assertNotIn("WorkflowStepper", source)
        self.assertNotIn("sessionStateLabel", source)

    def test_episode_inspector_selects_speaker_references_and_models_inline(self) -> None:
        source = EPISODE_INSPECTOR_PATH.read_text(encoding="utf-8")
        data_source = SCRIPT_WORKBENCH_DATA_PATH.read_text(encoding="utf-8")

        self.assertIn("Change voice", source)
        self.assertIn("filterActiveSpeakerReferences", source)
        self.assertIn("handleSelectSpeakerReference", source)
        self.assertIn("episode-render-model", source)
        self.assertIn("Advanced audio settings", source)
        self.assertIn("listSpeakerReferences", data_source)
        self.assertIn("selectSpeakerReference", data_source)

    def test_audio_dock_keeps_preview_full_render_and_export_together(self) -> None:
        source = EPISODE_AUDIO_DOCK_PATH.read_text(encoding="utf-8")

        self.assertIn("Preview", source)
        self.assertIn("Generate Audio", source)
        self.assertIn("Update Audio", source)
        self.assertIn("AudioPlayer", source)
        self.assertIn("handleExportMp3", source)

    def test_workspace_preview_uses_the_existing_disposable_preview_bridge(self) -> None:
        workspace_source = STUDIO_PAGE_PATH.read_text(encoding="utf-8")
        audio_source = SCRIPT_WORKBENCH_AUDIO_PATH.read_text(encoding="utf-8")

        self.assertIn("buildPreviewExcerpt", workspace_source)
        self.assertIn("bridge.renderVoicePreview", audio_source)
        self.assertIn("preview_text: text", audio_source)
        self.assertIn("speakerReferenceId", audio_source)

    def test_audio_generation_refreshes_selected_speaker_reference(self) -> None:
        source = SCRIPT_WORKBENCH_AUDIO_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "bridge.selectSpeakerReference(sessionId, scriptId, renderSpeakerReference.speaker_reference_id)",
            source,
        )

    def test_audio_generation_keeps_internal_context_window_regeneration_contract(self) -> None:
        source = SCRIPT_WORKBENCH_AUDIO_PATH.read_text(encoding="utf-8")

        self.assertIn("bridge.regenerateAudioWindow", source)
        self.assertIn("speechPlanId", source)
        self.assertIn("renderManifestId", source)

    def test_audio_generation_refreshes_workspace_after_polled_success(self) -> None:
        source = SCRIPT_WORKBENCH_AUDIO_PATH.read_text(encoding="utf-8")

        self.assertIn("refreshRenderedAudio", source)
        self.assertIn('state.phase === "succeeded"', source)
        self.assertIn("void refreshRenderedAudio()", source)


if __name__ == "__main__":
    unittest.main()
