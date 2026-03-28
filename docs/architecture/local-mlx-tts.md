# Local MLX TTS

## Purpose

This document describes the current local MLX TTS path.

## Current Design

The local provider is isolated under `services/python-core/app/providers/tts_local_mlx`.

It is responsible for:

- checking whether the current runtime is macOS
- checking whether the Python `mlx` and `mlx_audio` packages are installed
- resolving either a local model path or a supported `mlx-community/Qwen3-TTS` repo id
- exposing a capability report before audio rendering is attempted

## Current Behavior

If the local MLX capability check fails:

- the local provider raises a clear runtime error
- the orchestration layer marks the session as `failed`
- the user can switch back to the remote provider path

If the capability check succeeds:

- the provider invokes `mlx_audio.tts.generate`
- the generated audio artifact is read back into the existing provider response shape
- artifact export and failure handling stay inside the existing orchestration flow

## Current Model Strategy

The default model target is:

- `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit`

The runtime also accepts:

- another supported `mlx-community/Qwen3-TTS` repo id
- a local model path via `local_model_path`

## Runtime Requirements

The local MLX path currently expects:

- macOS
- Python `mlx` installed
- Python `mlx_audio` installed
- either a supported `mlx-community/Qwen3-TTS` repo id or a valid local model path

The CLI exposes `--show-local-tts-capability` so the environment can be checked before attempting audio rendering.

## Current Repository Validation Path

In this repository, local MLX validation currently works through:

- `services/python-core/.venv`
- `mlx` and `mlx_audio` installed into that virtual environment
- `examples/sample-models/local-mlx-placeholder`

The placeholder directory is still useful for path-validation tests, but the real local generation path now targets `mlx_audio` and the Qwen3-TTS model family.
