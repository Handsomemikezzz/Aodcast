# Product Overview

Aodcast is an AI-guided podcast creation app focused on turning user ideas into polished solo podcast content through interview-driven sampling and automated production.

The first release targets a minimal local-first macOS workflow with a Tauri frontend and a Python orchestration core.

## Script snapshots (one chat, many scripts)

- **Model**: A single interview session can contain **multiple independent script snapshots**. Each time you run script generation from that chat, the app **adds** a new snapshot; it does **not** replace earlier snapshots on disk.
- **Naming**: New snapshots are titled with the session topic plus a local timestamp, with **second-level** precision (for example `…-2026-04-18 09:04:32`) so back-to-back generations remain distinguishable.
- **Navigation**: Deep link shape is `/script/:sessionId/:scriptId`. If only the session is specified, the UI resolves to the **latest** snapshot for that session.
- **Editing**: Direct edits apply to the **currently open** `script_id` only; they do not rewrite chat history or other snapshots.
- **Audio rendering**: TTS uses the currently open `script_id` snapshot. Rendering an older snapshot does not force the active interview session out of its current conversation state.
- **Voice Studio**: `/voice-studio/:sessionId/:scriptId` is the dedicated audio production space. It defaults to a simple workflow with current engine/model status, a voice recipe summary, preview, full-audio take generation, and a two-take retention model (final take + latest candidate). Advanced voice controls expose voice/style/speed/language/output overrides only when expanded, and preview can use the standard sentence, the current script opening, or custom text.
- **Local models**: `/models` is the local model management center. It shows the active model storage folder, supports desktop open/change/migrate/reset actions for Aodcast model files, lets users choose the global default local voice model, explains the 0.6B/1.7B tradeoff, and surfaces inline download progress plus recoverable next-step/error details. Settings links back to this center instead of exposing local model switching as a primary text field.
- **Script handoff**: Script remains the project hub. When a Voice Studio take is marked as final, the artifact compatibility fields (`audio_path`, `transcript_path`, `provider`) point at that take so the Script audio sidebar can play, download, and reveal the final audio.
- **UI**: The script route focuses on editing and final-audio review; Voice Studio owns expressive rendering controls and take comparison.

## Audio-only MP4 / M4A scope

The current app can request provider/runtime output formats and serve common audio suffixes, but it does not transcode WAV to AAC/M4A/MP4 itself. `.mp4` means audio-only container support when the selected provider/runtime produces a valid file. True video MP4 and guaranteed WAV → AAC conversion require a separate ffmpeg/afconvert packaging decision.
