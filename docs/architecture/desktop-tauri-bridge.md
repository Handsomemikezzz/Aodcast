# Desktop Tauri Bridge

## Purpose

This document defines the current desktop bridge used by the Aodcast app shell.

## Current Flow

The real desktop path is:

`React component -> DesktopBridge -> Tauri invoke -> Rust command -> python_bridge -> scripts/dev/run-python-core.sh -> app.main`

This keeps UI code unaware of Python CLI details and keeps Rust free of podcast business logic.

## Frontend Boundary

- `apps/desktop/src/lib/desktopBridge.ts` defines the shared bridge contract
- `apps/desktop/src/lib/tauriBridge.ts` implements the real bridge
- `apps/desktop/src/lib/mockBridge.ts` remains available for browser-only UI work
- `apps/desktop/src/lib/bridgeFactory.ts` selects the runtime-specific bridge
- `apps/desktop/src/lib/BridgeContext.tsx` injects the active bridge into page components

React components should only depend on the `DesktopBridge` interface.

## Rust Boundary

The Tauri layer should:

- register invoke commands
- convert UI payloads into Python CLI arguments
- execute the Python runner
- parse a single JSON envelope from stdout
- return structured bridge errors to the frontend

The Tauri layer should not implement interview logic, script generation logic, or provider selection logic.

## Python Boundary

`services/python-core/app/main.py` now supports a desktop bridge mode through `--bridge-json`.

In bridge mode:

- stdout must contain exactly one JSON envelope
- success responses must look like `{ "ok": true, "data": ... }`
- failure responses must look like `{ "ok": false, "error": ... }`

This contract exists specifically so Rust can parse Python responses deterministically.

## Current Command Coverage

The bridge is currently wired for:

- session list and creation
- interview turn commands
- script generation and save flow
- audio rendering
- TTS config load and save for the `Settings` page
- local TTS capability inspection
- model catalog listing
- voice-model download and deletion

The bridge is not yet wired for:

- richer progress events for long-running downloads or model renders

## Current Limitation

Native compile checks can now run, but macOS DMG packaging still fails at the bundling stage (`bundle_dmg.sh`) in the current environment.
