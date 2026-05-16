# Product Overview

Aodcast is an AI-guided podcast creation app focused on turning user ideas into polished solo podcast content through interview-driven sampling and automated production.

The first release targets a minimal local-first macOS workflow with a Tauri frontend and a Python orchestration core.

## Script snapshots (one chat, many scripts)

- **Model**: A single interview session can contain **multiple independent script snapshots**. Each time you run script generation from that chat, the app **adds** a new snapshot; it does **not** replace earlier snapshots on disk.
- **Naming**: New snapshots are titled with the session topic plus a local timestamp, with **second-level** precision (for example `…-2026-04-18 09:04:32`) so back-to-back generations remain distinguishable.
- **Navigation**: Deep link shape is `/script/:sessionId/:scriptId`. If only the session is specified, the UI resolves to the **latest** snapshot for that session.
- **Editing**: Direct edits apply to the **currently open** `script_id` only; they do not rewrite chat history or other snapshots.
- **Audio rendering**: TTS uses the currently open `script_id` snapshot. Rendering an older snapshot does not force the active interview session out of its current conversation state.
- **Voice Studio**: `/voice-studio` is the global reusable voice library, and `/voice-studio/:sessionId/:scriptId` is the script-bound voice selection entry point. Voice Studio creates, previews, deletes, and selects voice profiles. It does not generate or manage final podcast audio.
- **Local models**: `/models` is the local model management center. It shows the active model storage folder, supports desktop open/change/migrate/reset actions for Aodcast model files, lets users choose the global default local voice model, explains the 0.6B/1.7B tradeoff, and surfaces inline download progress plus recoverable next-step/error details. Settings links back to this center instead of exposing local model switching as a primary text field; its TTS provider chooser is product-facing with only Local MLX and Remote API options.
- **Script handoff**: Selecting a profile from script-bound Voice Studio writes the current script's `artifact.voice_reference` with `source: "voice_profile"` and `voice_profile_id`. Script Workbench then uses that profile for final podcast rendering.
- **UI**: The script route focuses on editing and final-audio production/review; Voice Studio owns voice-profile selection, reference-audio preview, and profile creation.

## Audio-only MP4 / M4A scope

The current app can request provider/runtime output formats and serve common audio suffixes, but it does not transcode WAV to AAC/M4A/MP4 itself. `.mp4` means audio-only container support when the selected provider/runtime produces a valid file. True video MP4 and guaranteed WAV → AAC conversion require a separate ffmpeg/afconvert packaging decision.
