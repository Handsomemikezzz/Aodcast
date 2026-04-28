# Audio Rendering

## Purpose

This document describes the current audio-rendering path after script generation/editing.

## Flow

The Python core now supports a render-audio path after a session reaches `script_generated` or `script_edited`.

1. Load the persisted session project.
2. Ensure the session has an artifact record. New HTTP sessions create one up front, and audio rendering backfills one for older projects that have a valid script but no artifact metadata.
3. Load the active TTS configuration from local config storage.
4. Optionally apply a one-shot desktop-side provider override for the current render request.
5. Build the selected TTS provider adapter.
6. Render audio bytes from the final script text.
7. Write transcript and audio artifacts under local export storage.
8. Transition the session to `completed`.

The desktop `GeneratePage` uses this override path for its engine buttons:

- `Cloud Synthesis` runs a single render with the configured cloud provider, or the local-capability fallback provider when the saved config currently points at `local_mlx`
- `Local MLX Engine` runs a single render with `local_mlx`

These buttons do **not** rewrite the global TTS settings saved in `Settings`.

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
