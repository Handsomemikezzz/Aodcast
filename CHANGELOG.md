# Changelog

All notable changes to Aodcast will be documented in this file.

## [0.1.0-alpha] - Unreleased

### Added

- Local-first macOS desktop workflow for AI-guided solo podcast creation.
- Interview-driven session flow, Podcast Editor rhythm guidance, script generation, script snapshots, and script editing.
- Versioned, provider-neutral Speech Plans with stable segments, structured breaks, emphasis, pronunciation, delivery metadata, and exact script-hash binding.
- Voice Studio for provider-neutral Speaker References, sample upload/recording up to 10 minutes, preview rendering, and reference management.
- Script Workbench model and Speaker Reference selection, read-only Speech Plan inspection, per-segment playback, and B/C/D context-window regeneration.
- Immutable segment WAV assets and Render Manifests that record script, plan, reference, model pipeline, regeneration, assembly, and final-output lineage.
- VoxCPM2 and MOSS-TTS Local v1.5 MLX adapters alongside the Qwen3-TTS Base baseline, with explicit `native` / `approximated` / `unsupported` capability negotiation.
- Generic `scripts/model-download/download_tts_model.py` model downloader, defaulting to VoxCPM2 8-bit.
- Localhost HTTP runtime bridge between the Tauri/web UI and Python orchestration core.
- Mock provider paths for smoke tests and development fallback.
- Shared request-state contracts for long-running operations, script-scoped audio task ids, run-token-safe cancellation, and stale-poll rejection.

### Changed

- Local MLX now defaults to `mlx-community/VoxCPM2-8bit`; MOSS-TTS Local v1.5 is the long-form/explicit-pause comparison and Qwen3-TTS Base remains the cloning baseline.
- Local MLX dependencies now pin `mlx-audio[tts]` to `0.4.6`.
- Final `podcast.wav` is assembled from the Render Manifest with explicit pauses, format normalization, one edge fade per segment, audible-sample RMS matching, and a sample-peak ceiling.

### Removed

- Legacy voice-profile, preview-lock, and voice-take bridge/API flows. Persistent speaker identity now uses Speaker References, while final audio comes from manifest-driven rendering.

### Notes

- This release is intended as a GitHub source-code alpha, not a polished packaged desktop app distribution.
- Local MLX is the primary first-release TTS path and requires compatible macOS hardware/software plus model weights.
- API keys are stored and managed locally by users at their own risk.
