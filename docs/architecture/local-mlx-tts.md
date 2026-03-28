# Local MLX TTS

## Purpose

This document describes the current Milestone 6 local MLX TTS path.

## Current Design

The local provider is isolated under `services/python-core/app/providers/tts_local_mlx`.

It is responsible for:

- checking whether the current runtime is macOS
- checking whether the Python `mlx` package is installed
- checking whether a local model path is configured and exists
- exposing a capability report before audio rendering is attempted

## Current Behavior

If the local MLX capability check fails:

- the local provider raises a clear runtime error
- the orchestration layer marks the session as `failed`
- the user can switch back to the remote provider path

If the capability check succeeds:

- the current bootstrap implementation renders a deterministic local WAV artifact
- this validates the local execution path, artifact flow, and failure handling
- the repository's sample placeholder model directory can be used for capability and workflow validation only

## Why This Is Still Useful

The exact MLX speech model runner is not locked in yet. The current implementation deliberately proves:

- provider selection
- capability detection
- model-path validation
- local artifact generation path
- fallback messaging

without forcing premature lock-in to a specific model invocation contract.

## Runtime Requirements

The local MLX path currently expects:

- macOS
- Python `mlx` installed
- a configured local model path

The CLI exposes `--show-local-tts-capability` so the environment can be checked before attempting audio rendering.

## Current Repository Validation Path

In this repository, local MLX validation currently works through:

- `services/python-core/.venv`
- `mlx` installed into that virtual environment
- `examples/sample-models/local-mlx-placeholder`

This is sufficient to validate the local provider workflow, capability checks, and artifact output path without committing to a final speech-model invocation contract.
