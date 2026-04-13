# Desktop Runtime Bridge

## Purpose

This document defines the current runtime bridge used by the Aodcast desktop shell.

## Current Flow

The current desktop path is:

`React component -> DesktopBridge -> HTTP bridge -> localhost runtime -> python-core services`

The desktop shell still owns lifecycle concerns, but it no longer owns business-operation transport through a subprocess/stdout JSON bridge.

The desktop-owned responsibilities are:

- runtime start
- runtime readiness / attach
- runtime shutdown
- protected token/bootstrap handoff when required

Python core remains the source of truth for orchestration, storage, request-state progression, long-task state, cancellation, and error semantics.

## Frontend Boundary

- `apps/desktop/src/lib/desktopBridge.ts` defines the shared bridge contract
- the concrete bridge implementation must speak the localhost HTTP contract
- `apps/desktop/src/lib/bridgeFactory.ts` selects the runtime-specific bridge
- `apps/desktop/src/lib/BridgeContext.tsx` injects the active bridge into page components

React components should only depend on the `DesktopBridge` interface.

## Python Boundary

`services/python-core/app/api/http_runtime.py` is the HTTP runtime boundary.

Its responsibilities are:

- expose the repo's supported localhost routes
- preserve the existing `request_state` contract
- preserve long-task ack + poll semantics
- preserve structured error envelopes, including `error.details.request_state`
- expose streaming reply via HTTP/SSE instead of Tauri channel forwarding

## Current Command Coverage

The runtime bridge is expected to cover:

- session list and creation
- interview turn commands
- script generation and save flow
- audio rendering
- TTS config load and save for the `Settings` page
- local TTS capability inspection
- model catalog listing
- voice-model download and deletion
- task-state polling through `show_task_state` for long-running operations (`download_model:*`, `render_audio:*`)
- task-state polling now includes incremental `progress_percent` updates (download marker parsing + render heartbeat updates)
- task cancellation through `cancel_task` for long-running operations, with cooperative `cancelling` and `cancelled` task-state phases

The bridge contract must also preserve:

- streamed reply chunks plus a final structured envelope
- same payload shapes for desktop and same-machine browser clients

## Related Document

For the broader migration rationale and verification expectations, see `docs/architecture/shared-runtime-http-upgrade.md`.
