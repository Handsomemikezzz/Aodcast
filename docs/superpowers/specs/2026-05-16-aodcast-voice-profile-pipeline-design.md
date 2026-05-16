# Design: Aodcast Voice Profile Pipeline

**Status:** Approved for implementation planning  
**Date:** 2026-05-16  
**Scope:** Profile-first v1 simplification for stable local MLX/Qwen voice conditioning.

---

## 1. Purpose

Aodcast's current Voice Studio flow has too many ways to express "the selected voice": preset sliders, temporary preview locks, reusable profiles, Voice Studio takes, and Script Workbench render settings. That makes the product hard to reason about and allows formal podcast generation to drift away from the voice the user thought they selected.

This v1 simplifies the product around one rule:

> A generated podcast uses exactly one selected voice profile as its voice source.

The voice profile contains the reference audio and the matching reference text. Preview and full render both read that same profile and both pass the same `ref_audio` / `ref_text` conditioning package to the local MLX/Qwen provider.

---

## 2. Goals

- **Profile-first generation:** A script's current voice is a selected `VoiceProfileRecord`, not a temporary preview lock or a loose preset combination.
- **Explicit user voice library:** Users can add their own voice profile with a name, reference audio, and the exact text spoken in that reference audio.
- **5-second preview:** Users can select a profile and generate a short preview before rendering the full podcast.
- **Preview/full parity:** Preview and full render use the same profile reference audio and reference text.
- **Stable first release:** Remove or hide workflows that create competing voice state, especially temporary preview locking and Voice Studio take comparison.
- **Backwards compatibility:** Existing `artifact.voice_reference` payloads continue to load, but new selection writes `source: "voice_profile"` and `voice_profile_id`.

---

## 3. Non-Goals

- Deterministic seeding and exact waveform repeatability.
- Crossfade or other chunk-boundary audio post-processing.
- Multi-sample voice profile merging.
- Voicebox-style effect chains, version trees, or streaming APIs.
- Full removal of backend legacy endpoints in one pass. Legacy endpoints may remain callable for compatibility, but the UI and primary render path should stop depending on them.
- Pixel-perfect redesign of the desktop shell.

---

## 4. Product Model

### 4.1 Voice Profile

A voice profile is the user-facing voice identity.

Required conceptual fields:

- `voice_profile_id`
- `name`
- `source`: `built_in` or `user_saved`
- `audio_path`
- `reference_text`
- `provider`
- `model`
- `language`
- `audio_format`
- timestamps

Implementation note: the existing persisted field is `preview_text`. For v1, treat `preview_text` as the stored reference text and expose it in code/UI as "reference text" where possible. Schema may add `reference_text` as an alias only if that does not create duplicated truth.

### 4.2 Script Voice Selection

Each script snapshot may select one voice profile.

Selection persists into the script-scoped artifact as:

```json
{
  "source": "voice_profile",
  "voice_profile_id": "profile-id",
  "audio_path": "/path/to/profile.wav",
  "preview_text": "The exact text spoken in the profile audio.",
  "provider": "local_mlx",
  "model": "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit"
}
```

The selected profile's audio/text are the canonical voice anchor. Preset voice/style settings may remain as compatibility metadata, but they are not the primary identity source.

### 4.3 Preview

The preview action renders a short utterance using the selected profile. It does not create a temporary lock. It does not alter the profile. It does not create a Voice Studio take.

Preview text policy:

- Default to a short app-provided sentence intended to produce about 5 seconds of audio.
- If previewing from a script page, optionally use the beginning of the current script only if the UI already has it available.
- Always condition the preview with the selected profile's `ref_audio` and reference text.

### 4.4 Full Podcast Render

Full render resolves the selected profile from the script artifact, compiles the local MLX request with:

- `reference_audio_path = profile.audio_path`
- `reference_text = profile.preview_text`

If no profile is selected, the UI should block profile-first rendering and ask the user to choose a voice.

### 4.5 Remote Provider Degradation

If the user forces a provider that cannot honor reference conditioning, the app may proceed, but it must show explicit copy that the selected profile cannot be used by that provider and timbre may diverge.

---

## 5. UX Shape

Voice Studio v1 should be three practical panels:

1. **Current voice profile**
   - Shows selected profile name and source.
   - Offers "Preview voice" and "Generate podcast".
   - Shows a warning when no profile is selected.

2. **Voice library**
   - Lists built-in and user-saved profiles.
   - Lets the user select one profile for the current script.
   - Lets the user delete user-saved profiles.

3. **Add voice**
   - Accepts a reference audio path, profile name, and exact reference text.
   - Saves the profile into the voice library.
   - Optionally selects it for the current script after save.

Hide or remove from the primary UI:

- temporary "lock preview" controls
- "save preview as my voice"
- Voice Studio take comparison
- advanced preset/style/speed controls unless needed for compatibility

---

## 6. Data And API Changes

### 6.1 Keep

- `listVoiceProfiles`
- `createVoiceProfile`
- `updateVoiceProfile`
- `deleteVoiceProfile`
- `selectVoiceProfile`
- `renderVoicePreview`
- `renderAudio`

### 6.2 Add Or Adjust

- `createVoiceProfile` must accept direct profile creation from reference audio plus reference text, not only from a generated preview artifact.
- `renderVoicePreview` should accept `voice_profile_id` or resolve the selected script profile when session/script are provided.
- `renderAudio` should use the selected profile anchor by default and should not require the caller to send voice settings for the common path.
- Bridge types should expose reference-text semantics clearly even if the backend persistence field remains `preview_text`.

### 6.3 De-emphasize

The following may remain in backend compatibility code, but should not be used by the simplified UI:

- `lockVoicePreview`
- `renderVoiceTake`
- `setFinalVoiceTake`
- `deleteVoiceTake`

---

## 7. Acceptance Criteria

- Creating a user voice profile requires a non-empty name, audio path, and reference text.
- Selecting a profile writes script-scoped `artifact.voice_reference.source === "voice_profile"` and `voice_profile_id`.
- Preview for a selected profile passes the profile audio and reference text into the local MLX/Qwen request.
- Full podcast render for the same script passes the same profile audio and reference text into the local MLX/Qwen request.
- Voice Studio UI no longer presents temporary preview locking or take comparison as primary workflows.
- A script without a selected profile cannot accidentally render through the simplified profile-first UI.
- Existing built-in profiles still list and serve their packaged audio.
- Existing tests for HTTP bridge parity and script-scoped artifact isolation remain green.

---

## 8. Deferred Work

- Deterministic seeds.
- Crossfade between long-form chunks.
- Multi-reference profile blending.
- Full deletion of compatibility routes and domain fields after migration evidence shows they are no longer used.
- Remote-provider profile conditioning beyond honest degradation copy.

---

## 9. References

- `AGENTS.md`
- `docs/product/product-overview.md`
- `docs/architecture/audio-rendering.md`
- `docs/architecture/tts-pipeline.md`
- `services/python-core/app/storage/voice_profile_store.py`
- `services/python-core/app/orchestration/audio_rendering.py`
- `apps/desktop/src/pages/VoiceStudioPage.tsx`

---

## Document History

| Date | Change |
|------|--------|
| 2026-05-16 | Re-scoped from hybrid Voicebox-style pipeline to profile-first v1 simplification. |
