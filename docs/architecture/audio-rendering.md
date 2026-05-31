# Audio Rendering

## Purpose

This document describes the current audio-rendering path after script generation/editing. Script Workbench owns final podcast rendering. Voice Studio owns reusable voice profiles and short preview rendering.

## Flow

The Python core supports a render-audio path for any active script snapshot with non-empty content.

1. Load the persisted session project.
2. Ensure the session has an artifact record. New HTTP sessions create one up front, and audio rendering backfills one for older projects that have a valid script but no artifact metadata.
3. Resolve the script's Voice Studio settings. The render request may pass settings explicitly; otherwise the artifact's saved `voice_settings` are used; if no saved settings exist, the Voice Studio default (`warm_narrator` / `natural` / `1.0x` / `zh` / `wav`) is used.
4. Load the active TTS configuration from local config storage, then apply the resolved Voice Studio provider voice and audio format for this render.
5. Optionally apply a one-shot desktop-side provider override for the current render request.
6. Build the selected TTS provider adapter.
7. If the selected script has a Voice Studio profile reference and the render uses `local_mlx`, validate that profile audio still exists and pass it as the provider request's reference audio and reference text. Profile-first callers can require this reference and fail early if no voice profile is selected.
8. Render audio bytes from the final script text.
9. Write transcript and audio artifacts under local export storage.
10. Transition the session back to its previous interview/script state for historical renders, or to `completed` when rendering from an existing generated/edited script state.

The desktop Script Workbench uses this override path for its engine controls:

- Cloud rendering runs a single render with the configured cloud provider, or the local-capability fallback provider when the saved config currently points at `local_mlx`
- Local MLX rendering runs a single render with `local_mlx`

These buttons do **not** rewrite the global TTS settings saved in `Settings`.
Script Workbench renders use the selected script's saved voice settings, so final audio matches the selected voice profile instead of falling back to the raw Settings voice.

Sessions can contain multiple script snapshots. Artifact playback fields remain backward-compatible at the top level, but the canonical per-script state is also stored under `artifact.script_artifacts[script_id]`. Loading, rendering, selecting, and deleting audio for a script must use the script-scoped project view so one script's voice settings/takes do not overwrite another script snapshot.

## Provider Layer

Current TTS providers:

- `mock_remote`: deterministic local provider that writes a simple WAV tone for validation
- `openai_compatible`: configurable adapter for remote speech endpoints
- `local_mlx`: local MLX-backed adapter for macOS environments that pass capability checks

Local MLX details and capability semantics are documented in `docs/architecture/local-mlx-tts.md`.

## Local Output Layout

Audio artifacts are written under:

```text
.local-data/
└── exports/
    └── <session-id>/
        ├── transcript.txt
        └── audio.wav
```

## Failure Behavior

- rendering failures preserve the script and artifact records
- session state is restored for active interview/readiness states and otherwise moves to `failed`
- the error message is stored in `session.last_error`
- failed sessions can be retried after TTS configuration is fixed

## Audio-only MP4 / M4A scope

The current app can request provider/runtime output formats and serve common audio suffixes, but it does not transcode WAV to AAC/M4A/MP4 itself. `.mp4` means audio-only container support when the selected provider/runtime produces a valid file. True video MP4 and guaranteed WAV → AAC conversion require a separate ffmpeg/afconvert packaging decision.

## Voice Studio preview tasks

Voice Studio preview rendering uses the same localhost HTTP runtime but runs as a pollable background task (`render_voice_preview`) instead of holding the initial POST open. This keeps the Web and Tauri shells responsive while local MLX loads a model or synthesizes the short preview. The final task state carries the preview `audio_path`, provider/model metadata, and normalized settings so the frontend can resolve the artifact through `/api/v1/artifacts/audio`.

When preview requests include a session/script context, the selected Voice Studio settings are saved on that script's artifact as `voice_settings`.

Voice profiles are the canonical voice source for profile-first rendering. The two built-in profiles are packaged app assets under `services/python-core/app/assets/voice-profiles/` and contain the English reference line “Hello, welcome to use Aodcast. What shall we talk about today?”. User-saved profiles are stored under `.local-data/voice-profiles/user-profiles.json`, with profile audio copied into `.local-data/exports/_voice_profiles` so it can be served through the normal artifact audio route.

User profile creation is a two-step HTTP flow: `POST /api/v1/voice-profiles` creates metadata, then `POST /api/v1/voice-profiles/{profile_id}/sample` uploads one multipart audio sample plus manually entered `reference_text`. The desktop UI exposes this as a dialog with upload and microphone recording sources; users should not enter local filesystem paths. System audio capture is shown as unavailable until a macOS/Tauri capture command is implemented. WAV samples longer than 30 seconds are rejected.

Selecting a profile writes the current script's `artifact.voice_reference` with `source: "voice_profile"`, `voice_profile_id`, profile `audio_path`, and reference text. Profile preview and full script render both pass that profile audio as `ref_audio` and the profile reference text as `ref_text` for local MLX/Qwen. Temporary preview-lock endpoints remain for compatibility with existing artifacts, but the stable UI path is `selectVoiceProfile` -> `renderVoicePreview` -> profile-first `renderAudio`.

## Deleting generated audio

Generated audio is managed through the desktop UI; users should not need to inspect `artifact.json` directly.

- Voice Studio preview audio can be deleted from the preview player. This removes the standalone file under `.local-data/exports/_previews`; if that file is currently used by a script's `voice_reference`, the reference lock is cleared so future renders do not point at a missing file.
- User-saved voice profiles can be deleted from the Voice Studio library. This removes the copied profile audio and clears any script `voice_reference` pointing at it. Built-in profiles cannot be deleted.
- Legacy Voice Studio takes can still be deleted through the compatibility bridge method. If the deleted take is the current final take, the artifact's `final_take_id`, `audio_path`, `transcript_path`, and `provider` are cleared.
- Script Workbench exposes deletion for the current generated audio artifact. This removes the audio/transcript export files and clears the selected script's artifact playback fields while preserving the saved Voice Studio `voice_settings` and other script snapshots.
