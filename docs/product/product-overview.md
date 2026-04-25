# Product Overview

Aodcast is an AI-guided podcast creation app focused on turning user ideas into polished solo podcast content through interview-driven sampling and automated production.

The first release targets a minimal local-first macOS workflow with a Tauri frontend and a Python orchestration core.

## Script snapshots (one chat, many scripts)

- **Model**: A single interview session can contain **multiple independent script snapshots**. Each time you run script generation from that chat, the app **adds** a new snapshot; it does **not** replace earlier snapshots on disk.
- **Naming**: New snapshots are titled with the session topic plus a local timestamp, with **second-level** precision (for example `…-2026-04-18 09:04:32`) so back-to-back generations remain distinguishable.
- **Navigation**: Deep link shape is `/script/:sessionId/:scriptId`. If only the session is specified, the UI resolves to the **latest** snapshot for that session.
- **Editing**: Direct edits and revision history apply to the **currently open** `script_id` only; they do not rewrite chat history or other snapshots.
- **UI**: The script route is a single workbench that combines script editing, TTS engine selection, and audio output preview. Snapshot switching and revision rollback stay in secondary panels so the main editing canvas remains focused.
