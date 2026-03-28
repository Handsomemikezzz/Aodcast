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

## Current Limitation

The repository still cannot validate native Tauri compilation in the current environment because `cargo` is not available on `PATH`.
