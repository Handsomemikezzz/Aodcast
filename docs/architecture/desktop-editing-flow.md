# Desktop Editing Flow

## Purpose

This document describes the current Milestone 4 desktop-side flow for session browsing, interview interaction, and direct script editing.

## Current Shape

The desktop app now has four UI responsibilities:

- create a new session from topic and creation intent
- browse tracked sessions from a sidebar
- run interview turns from a session detail workspace
- review and directly edit a generated draft

## Bridge Boundary

The current desktop flow is backed by a local mock bridge under `apps/desktop/src/lib/mockBridge.ts`.

That bridge is intentional. It lets the UI stabilize before the real Tauri-to-Python command bridge is available.

The bridge currently exposes:

- `listProjects`
- `createSession`
- `startInterview`
- `submitReply`
- `requestFinish`
- `generateScript`
- `saveEditedScript`

## Replacement Plan

When the native desktop bridge is ready, the mock bridge should be replaced behind the same interface rather than rewriting the UI.

The target replacement path is:

1. keep the view and state model stable
2. swap the mock bridge with a Tauri command adapter
3. preserve the same session project shapes used by the UI

## Current Limits

- data is in-memory in the desktop shell
- no native Tauri command calls are wired yet
- no frontend runtime validation has been completed in this environment because dependencies are not installed and the Rust toolchain is not available
