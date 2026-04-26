# Changelog

All notable changes to Aodcast will be documented in this file.

## [0.1.0-alpha] - Unreleased

### Added

- Local-first macOS desktop workflow for AI-guided solo podcast creation.
- Interview-driven session flow, script generation, script snapshots, and script editing.
- Voice Studio for local MLX-oriented preview and take generation workflows.
- Localhost HTTP runtime bridge between the Tauri/web UI and Python orchestration core.
- Mock provider paths for smoke tests and development fallback.
- Shared request-state contracts for long-running operations and cancellation.

### Notes

- This release is intended as a GitHub source-code alpha, not a polished packaged desktop app distribution.
- Local MLX is the primary first-release TTS path and requires compatible macOS hardware/software plus model weights.
- API keys are stored and managed locally by users at their own risk.
