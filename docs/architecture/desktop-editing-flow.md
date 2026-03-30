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
- split sub-flow for script editing and text-to-speech generation
- direct access to `EditPage` and `GeneratePage`

### `Models`

- voice model status listing
- download and delete controls for voice models

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

- native Tauri runtime validation still depends on `cargo`, which is unavailable in the current environment
