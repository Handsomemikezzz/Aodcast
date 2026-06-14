# Desktop Shell Flow

## Purpose

This document describes the current desktop-side shell, route structure, and the main user flows now exposed in the redesigned app.

## Current Shape

The desktop app now behaves like a small workstation rather than a single session detail page.

Current top-level routes:

- `Chat`
- `Script`
- `Models`
- `Voice Studio`
- `Settings`

The shell is implemented through:

- router-driven navigation in `apps/desktop/src/App.tsx`
- a shared `BridgeProvider` in `apps/desktop/src/lib/BridgeContext.tsx`
- page-level composition under `apps/desktop/src/pages`
- a Tailwind v4-based macOS-inspired design system in `apps/desktop/src/styles.css`

## Current Page Responsibilities

### `Chat`

- session browsing
- session creation
- interview turns
- readiness and prompt-input visualization
- transcript-like conversation workspace

### `Script`

- session selection when no session is open
- unfinished chats are labeled in the Script list and route back to Chat instead of opening an empty script route
- list rows expose a confirmation-backed trash action: generated rows soft-delete the latest script snapshot, while unfinished rows soft-delete the session draft
- single workbench layout that combines editing, voice settings, and generated-audio preview
- the right-side Voice Workspace opens an inline voice-profile dropdown for choosing built-in or user-saved voices, with a small management link into Voice Studio
- prominent top-bar primary action for audio rendering, with secondary preview/save actions
- audio rendering targets the currently open `script_id` snapshot and does not forcibly replace an active interview state when rendering an older snapshot
- explicit save for script edits; the editor does not save on textarea blur
- unsaved-change confirmation before refresh and trash
- in-app confirmation dialogs for destructive actions instead of browser-native `window.confirm`

#### Spoken Script Editor MVP Contract

The next Script editor iteration treats the script body as the exact text sent to text-to-speech. Every visible character in the body should be assumed to be spoken. Non-spoken material such as notes, stage directions, speaker labels, markdown structure, pause hints, or production comments must not be silently mixed into the script body.

Implementation boundary:

- MVP behavior is frontend-owned under `apps/desktop`.
- The backend continues to persist and render the existing plain `draft` / `final` script strings.
- No shared schema change is required for the MVP.
- Render blocking is enforced by the Script Workbench UI before starting audio generation; backend hardening can be added later.

Editor modes:

- Default mode is `Script`, a spoken-script editing surface built on the current plain-text editor path.
- `Script` mode should look and feel like editing a clean narration draft: larger readable type, natural paragraph spacing, and no markdown toolbar or markdown-facing copy.
- A low-priority `Plain text` mode remains available as an escape hatch for precise repair, copy/paste cleanup, and debugging.
- `Script` and `Plain text` show the same real text and edit the same string. They may differ in density, typography, line height, and wrapping, but must not hide, replace, or visually clean characters that will be saved or sent to TTS.
- The editor keeps explicit save behavior. It does not auto-save on blur.

Readability checks:

- Checks run locally in the frontend as lightweight derived state from the current editor text.
- The editor footer shows a persistent status such as `Ready for TTS`, `2 blocking issues`, or `5 suggestions`.
- Expanding the status reveals the issue list and cleanup actions.
- The Generate final audio control uses the same check result and shows only a concise blocking summary near the button.
- Checks should not interrupt typing with modal warnings.

Issue levels:

- `blocking`: prevents final audio generation until fixed.
- `warning`: recommends cleanup but allows rendering.
- `info`: provides read-only context such as estimated length or structure statistics.

Blocking issues:

- Empty or whitespace-only script.
- Speaker labels that would be read aloud, such as `Host:`, `Narrator:`, `主播：`, `旁白：`, or similar line prefixes.
- Stage directions or production notes, such as `[music]`, `[opening music]`, `(pause)`, `（停顿）`, `【音效】`, or similar bracketed directions.
- Markdown structure leftovers, including heading prefixes, list prefixes, block quotes, or horizontal rules, such as line-leading `#`, `- `, `* `, `1. `, `> `, or `---`.

Warnings:

- High-confidence filler words that may sound odd when synthesized, such as standalone `嗯`, `呃`, `那个`, or `you know`.
- Very long Chinese sentences: roughly more than 80 Han characters without a clear pause punctuation mark.
- Very long English sentences: roughly more than 45 words.
- Very long Chinese paragraphs: roughly more than 260 Han characters.
- Very long English paragraphs: roughly more than 160 words.
- Weak pause structure, such as a dense script with too few paragraph breaks for comfortable listening.

Clean all behavior:

- `Clean all` must show a change preview before applying edits.
- Applying cleanup updates the current editor value only. It does not auto-save.
- After cleanup, the editor enters the existing unsaved-edits flow; persistence continues through the existing Save/revision path.
- Cleanup may remove blocking issues and high-confidence filler words.
- Cleanup must not split long sentences, split long paragraphs, rewrite tone, rewrite content, or run AI rewriting.
- Ambiguous conversational particles, especially sentence-final Chinese particles such as `啊`, `呢`, and `吧`, should not be deleted automatically.

Non-goals for the MVP:

- no rich-text editor framework
- no structured paragraph schema
- no hidden text transformation in `Script` mode
- no inline non-spoken chips
- no SSML syntax in the script body
- no provider-aware prosody or pause conversion
- no automatic AI script rewrite or coaching
- no backend render guard unless added in a later hardening pass

Future options:

- inline non-spoken pause/prosody controls that render through provider-aware conversion
- backend validation for blocking render issues
- structured paragraph and section metadata
- AI-assisted script coaching and rewrite suggestions
- richer diff review for cleanup actions

### `Models`

- voice model status listing
- global default local voice-model selection for `local_mlx`
- model storage folder display, open, change/migrate, and reset controls
- inline download progress, cancellation, retry/error recovery, and delete controls for voice models

### `Voice Studio`

- reusable voice-profile library
- built-in and user-created profile listing
- profile sample upload or microphone recording
- profile preview through the pollable `render_voice_preview` task
- script-bound profile selection at `/voice-studio/:sessionId/:scriptId`
- no primary final-audio generation or take-comparison workflow

### `Settings`

- global LLM and TTS provider configuration
- cloud TTS connection/model fields in the default view
- local MLX model switching delegated to `Models`, with raw local overrides kept behind an advanced foldout
- bridge-backed persistence into Python core config files

## Bridge Boundary

The desktop shell now depends on the runtime-selected bridge through `DesktopBridge`.

Current bridge-backed desktop responsibilities:

- session listing and creation
- interview start/reply/finish
- script generation and editing
- audio rendering
- generated-audio deletion/export
- local TTS capability inspection
- model catalog listing and voice-model download/delete actions
- voice-profile listing, creation, sample upload, update, delete, preview, and selection

## Current Limits

- native compile checks can run with local `cargo`, but full macOS packaging still depends on a successful DMG bundle step
