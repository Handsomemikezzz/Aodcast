# Audio Rendering

## Purpose

This document describes the current audio-rendering path after script generation/editing.

## Flow

The Python core now supports a render-audio path after a session reaches `script_generated` or `script_edited`.

1. Load the persisted session project.
2. Ensure the session has an artifact record. New HTTP sessions create one up front, and audio rendering backfills one for older projects that have a valid script but no artifact metadata.
3. Resolve the script's Voice Studio settings. The render request may pass settings explicitly; otherwise the artifact's saved `voice_settings` are used; if no saved settings exist, the Voice Studio default (`warm_narrator` / `natural` / `1.0x` / `zh` / `wav`) is used.
4. Load the active TTS configuration from local config storage, then apply the resolved Voice Studio provider voice and audio format for this render.
5. Optionally apply a one-shot desktop-side provider override for the current render request.
6. Build the selected TTS provider adapter.
7. Render audio bytes from the final script text.
8. Write transcript and audio artifacts under local export storage.
9. Transition the session to `completed`.

The desktop `GeneratePage` uses this override path for its engine buttons:

- `Cloud Synthesis` runs a single render with the configured cloud provider, or the local-capability fallback provider when the saved config currently points at `local_mlx`
- `Local MLX Engine` runs a single render with `local_mlx`

These buttons do **not** rewrite the global TTS settings saved in `Settings`.
Both Generate and Script-page renders use the same saved Voice Studio settings for the selected script, so the audio generated from these pages matches the voice selected in Voice Studio instead of falling back to the raw Settings voice.

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
- session state moves to `failed`
- the error message is stored in `session.last_error`
- failed sessions can be retried after TTS configuration is fixed

## Audio-only MP4 / M4A scope

The current app can request provider/runtime output formats and serve common audio suffixes, but it does not transcode WAV to AAC/M4A/MP4 itself. `.mp4` means audio-only container support when the selected provider/runtime produces a valid file. True video MP4 and guaranteed WAV → AAC conversion require a separate ffmpeg/afconvert packaging decision.

## Voice Studio preview tasks

Voice Studio preview rendering uses the same localhost HTTP runtime but runs as a pollable background task (`render_voice_preview`) instead of holding the initial POST open. This keeps the Web and Tauri shells responsive while local MLX loads a model or synthesizes the short preview. The final task state carries the preview `audio_path`, provider/model metadata, and normalized settings so the frontend can resolve the artifact through `/api/v1/artifacts/audio`.

When preview requests include a session/script context, the selected Voice Studio settings are saved on that script's artifact as `voice_settings`. Rendering a Voice Studio take also saves the settings and promotes the take to the final script audio by updating `final_take_id`, `audio_path`, `transcript_path`, and `provider`. This keeps Script-page playback and subsequent Generate-page renders aligned with the most recent Voice Studio choice.

## Deleting generated audio

Generated audio is managed through the desktop UI; users should not need to inspect `artifact.json` directly.

- Voice Studio preview audio can be deleted from the preview player. This removes the standalone file under `.local-data/exports/_previews`.
- Voice Studio takes can be deleted from the take card. If the deleted take is the current final take, the artifact's `final_take_id`, `audio_path`, `transcript_path`, and `provider` are cleared.
- Script and Generate pages expose deletion for the current generated audio artifact. This removes the audio/transcript export files and clears the selected script's artifact playback fields while preserving the saved Voice Studio `voice_settings` and other script snapshots.
