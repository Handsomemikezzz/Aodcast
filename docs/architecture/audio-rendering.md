# Audio Rendering

## Purpose

This document describes the current audio-rendering path after script generation/editing.

## Flow

The Python core now supports a render-audio path after a session reaches `script_generated` or `script_edited`.

1. Load the persisted session project.
2. Load the active TTS configuration from local config storage.
3. Build the configured TTS provider adapter.
4. Render audio bytes from the final script text.
5. Write transcript and audio artifacts under local export storage.
6. Transition the session to `completed`.

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
