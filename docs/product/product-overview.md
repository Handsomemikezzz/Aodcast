# Product Overview

Aodcast is an AI-guided podcast creation app focused on turning user ideas into polished solo podcast content through interview-driven sampling and automated production.

The first release targets a minimal local-first macOS workflow with a Tauri frontend and a Python orchestration core.

## Script snapshots (one chat, many scripts)

- **Model**: A single interview session can contain **multiple independent script snapshots**. Each time you run script generation from that chat, the app **adds** a new snapshot; it does **not** replace earlier snapshots on disk.
- **Naming**: New snapshots are titled with the session topic plus a local timestamp, with **second-level** precision (for example `…-2026-04-18 09:04:32`) so back-to-back generations remain distinguishable.
- **Navigation**: Deep link shape is `/script/:sessionId/:scriptId`. If only the session is specified, the UI resolves to the **latest** snapshot for that session.
- **Editing**: Direct edits apply to the **currently open** `script_id` only; they do not rewrite chat history or other snapshots.
- **Audio rendering**: TTS uses the currently open `script_id` snapshot. Rendering an older snapshot does not force the active interview session out of its current conversation state.
- **Voice Studio**: `/voice-studio/:sessionId/:scriptId` is the dedicated audio production space. It packages provider voices into user-facing cards, supports fixed-sentence preview, speed/style settings, full-audio take generation, and a two-take retention model (final take + latest candidate).
- **Script handoff**: Script remains the project hub. When a Voice Studio take is marked as final, the artifact compatibility fields (`audio_path`, `transcript_path`, `provider`) point at that take so the Script audio sidebar can play, download, and reveal the final audio.
- **UI**: The script route focuses on editing and final-audio review; Voice Studio owns expressive rendering controls and take comparison.
