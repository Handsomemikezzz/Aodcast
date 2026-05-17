from __future__ import annotations

import unittest

from tests.http_contract_helpers import REPO_ROOT


SCRIPT_PAGE_PATH = REPO_ROOT / "apps/desktop/src/pages/ScriptPage.tsx"
SCRIPT_WORKBENCH_HEADER_PATH = REPO_ROOT / "apps/desktop/src/pages/script-workbench/ScriptWorkbenchHeader.tsx"
SCRIPT_AUDIO_SIDEBAR_PATH = REPO_ROOT / "apps/desktop/src/pages/script-workbench/ScriptAudioSidebar.tsx"
SCRIPT_WORKBENCH_DATA_PATH = REPO_ROOT / "apps/desktop/src/pages/script-workbench/useScriptWorkbenchData.ts"
SCRIPT_WORKBENCH_AUDIO_PATH = REPO_ROOT / "apps/desktop/src/pages/script-workbench/useScriptWorkbenchAudio.ts"


class ScriptPageSourceTests(unittest.TestCase):
    def test_script_list_keeps_unfinished_sessions_out_of_empty_script_route(self) -> None:
        source = SCRIPT_PAGE_PATH.read_text(encoding="utf-8")

        self.assertIn('navigate(`/chat/${targetSessionId}`)', source)
        self.assertIn("deleteSession", source)
        self.assertIn("deleteScript", source)
        self.assertIn("ConfirmDialog", source)

    def test_script_header_keeps_audio_generation_without_extra_voice_cta(self) -> None:
        source = SCRIPT_WORKBENCH_HEADER_PATH.read_text(encoding="utf-8")

        self.assertNotIn("Change voice:", source)
        self.assertNotIn("Choose voice", source)
        self.assertIn("Generate final audio", source)

    def test_script_audio_sidebar_selects_voice_profiles_inline(self) -> None:
        source = SCRIPT_AUDIO_SIDEBAR_PATH.read_text(encoding="utf-8")
        data_source = SCRIPT_WORKBENCH_DATA_PATH.read_text(encoding="utf-8")

        self.assertIn("voiceMenuOpen", source)
        self.assertIn("filterActiveVoiceProfiles", source)
        self.assertIn("handleSelectVoiceProfile", source)
        self.assertNotIn("Change voice", source)
        self.assertIn("listVoiceProfiles", data_source)
        self.assertIn("selectVoiceProfile", data_source)

    def test_script_audio_sidebar_only_shows_progress_for_active_audio_tasks(self) -> None:
        source = SCRIPT_AUDIO_SIDEBAR_PATH.read_text(encoding="utf-8")

        self.assertIn("isActiveRequestState", source)
        self.assertNotIn('workbench.audioRequestState.phase !== "succeeded" && workbench.audioRequestState.phase !== "failed"', source)

    def test_audio_generation_refreshes_selected_profile_reference(self) -> None:
        source = SCRIPT_WORKBENCH_AUDIO_PATH.read_text(encoding="utf-8")

        self.assertIn("bridge.selectVoiceProfile(sessionId, scriptId, voiceReference.voice_profile_id)", source)

    def test_audio_generation_refreshes_workspace_after_polled_success(self) -> None:
        source = SCRIPT_WORKBENCH_AUDIO_PATH.read_text(encoding="utf-8")

        self.assertIn("refreshRenderedAudio", source)
        self.assertIn('state.phase === "succeeded"', source)
        self.assertIn("void refreshRenderedAudio()", source)


if __name__ == "__main__":
    unittest.main()
