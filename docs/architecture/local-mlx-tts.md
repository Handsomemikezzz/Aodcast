# Local MLX TTS

## Purpose

This document describes the current local MLX TTS path.

## Current Design

The local provider is isolated under `services/python-core/app/providers/tts_local_mlx`.

It is responsible for:

- checking whether the current runtime is macOS
- checking whether the Python `mlx` and `mlx_audio` packages are installed
- resolving either a local model path or a supported `mlx-community/Qwen3-TTS` repo id
- probing `mlx` runtime bootstrap in a subprocess before render attempts
- exposing a capability report before audio rendering is attempted

## Current Behavior

If the local MLX capability check fails:

- the local provider raises a clear runtime error
- the orchestration layer marks the session as `failed`
- the user can switch back to the remote provider path
- native `mlx` bootstrap crashes are surfaced in capability reasons instead of taking down the parent process

If the capability check succeeds:

- the provider routes through `MLXAudioQwenRunner`
- the runner submits chunked jobs to a persistent `WorkerClient`
- `WorkerClient` launches `python -m app.providers.tts_local_mlx.mlx_worker`
- the worker loads the model once per worker lifetime and writes the joined audio output
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
- successful `mlx` runtime bootstrap probe (`import mlx.core`)
- either a supported `mlx-community/Qwen3-TTS` repo id or a valid local model path

The CLI exposes `--show-local-tts-capability` so the environment can be checked before attempting audio rendering.

## Repository Validation Path

Use `./scripts/dev/run-python-core.sh --show-local-tts-capability` from the repository root. The script prefers `services/python-core/.venv` when present, so do not assume a bare system Python has the same MLX availability.

The placeholder under `examples/sample-models/local-mlx-placeholder` is only for path-validation tests. It is not an executable model bundle.
