# Desktop Shell Flow

## Purpose

This document describes the current desktop-side shell, route structure, and the main user flows now exposed in the redesigned app.

## Current Shape

The desktop app now behaves like a small workstation rather than a single session detail page.

Current top-level routes:

- `Chat`
- `Script`
- `Models`
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
- single workbench layout that combines editing, voice settings, and generated-audio preview
- prominent top-bar primary action for audio rendering, with secondary preview/save actions
- audio rendering targets the currently open `script_id` snapshot and does not forcibly replace an active interview state when rendering an older snapshot
- explicit save for script edits; the editor does not save on textarea blur
- unsaved-change confirmation before refresh and trash
- in-app confirmation dialogs for destructive actions instead of browser-native `window.confirm`

### `Models`

- voice model status listing
- global default local voice-model selection for `local_mlx`
- model storage folder display, open, change/migrate, and reset controls
- inline download progress, cancellation, retry/error recovery, and delete controls for voice models

### `Voice Studio`

- simple-default audio production workspace with current engine/model status
- script summary, voice recipe summary, preview, full-audio take generation, and final/candidate take comparison
- advanced controls for voice/style/speed/language/output/provider override; local model switching remains in `Models`

### `Settings`

- global TTS provider configuration
- bridge-backed persistence into Python core config files

## Bridge Boundary

The desktop shell now depends on the runtime-selected bridge through `DesktopBridge`.

Current bridge-backed desktop responsibilities:

- session listing and creation
- interview start/reply/finish
- script generation and editing
- audio rendering
- local TTS capability inspection
- model catalog listing and voice-model download/delete actions

## Current Limits

- native compile checks can run with local `cargo`, but full macOS packaging still depends on a successful DMG bundle step
