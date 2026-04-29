# Shared Runtime HTTP Upgrade

## Purpose

This document turns the approved plan in `.omx/plans/ralplan-shared-runtime-http-upgrade-2026-04-12.md` into an implementation-facing architecture note for the repo.

It does two things:

1. records the grounded review findings from the current desktop bridge and Python runtime code
2. defines the migration shape for the localhost HTTP runtime, the desktop/browser adapters, and the verification gates that must hold during cutover

## Current Ground Truth

The repo now contains the first HTTP runtime slice under `services/python-core/app/api/http_runtime.py`, but the codebase still contains legacy subprocess bridge paths that must be removed during convergence.

The repo already has a few constraints that strongly shape the migration:

- `apps/desktop/src/lib/desktopBridge.ts` is the canonical UI contract and already exposes the full session/script/model/task surface the app depends on.
- the frontend now converges on `apps/desktop/src/lib/httpBridge.ts` as the shared transport boundary for desktop and same-machine browser flows.
- `apps/desktop/src/lib/requestState.ts` is the normalization boundary for `request_state` semantics and should remain the single frontend validator during the transport swap.
- Script Workbench, Voice Studio, and `apps/desktop/src/pages/ModelsPage.tsx` assume the long-task parity contract of immediate ack + later `showTaskState(task_id)` polling.
- `apps/desktop/src/pages/ChatPage.tsx` already assumes incremental streaming deltas plus a final structured envelope.
- the previous browser hard-stop path has been removed; browser flows now target the same localhost HTTP runtime contract.
- `services/python-core/pyproject.toml` declares no runtime dependencies, so phase 1 must remain stdlib-only on the server side.

## Review Findings

### 1. The `DesktopBridge` interface is the migration anchor

The safest cutover is to preserve the `DesktopBridge` method set and swap transport underneath it. That keeps page components stable while the runtime moves from subprocess CLI calls to localhost HTTP.

### 2. `request_state` parity is already encoded in UI behavior

Script Workbench, Voice Studio, `ModelsPage`, and the shared request-state helpers already rely on:

- stable `operation`
- progress-bearing `running` updates
- terminal `succeeded` / `failed` / `cancelled` states
- failure recovery through `error.details.request_state`

The HTTP runtime should preserve those semantics exactly instead of teaching the UI a new error model.

### 3. Long-running task behavior is already poll-oriented

`renderAudio` and `downloadModel` already work as:

1. invoke action
2. receive immediate response with task metadata
3. poll `showTaskState`
4. resolve UX from the terminal task state

That means HTTP does not need a new push model for long tasks; it needs parity with the current ack + poll contract.

### 4. Streaming reply is the main adapter-sensitive path

`submitReplyStream` is the only Chat reply transport exposed through the desktop bridge. It uses HTTP/SSE while preserving the higher-level `onChunk(delta)` contract consumed by `ChatPage`.

The practical implication is:

- use SSE on the Python side
- add a shared stream parser on the client side
- keep the final event shape compatible with the existing structured `InterviewTurnResult`
- do not reintroduce a parallel Chat reply endpoint

### 5. Browser parity is mostly a runtime/bootstrap problem

The browser path is not blocked on UI contracts. It is blocked on:

- a loopback-only runtime that can be started or attached safely
- a same-machine bootstrap/token flow for protected endpoints
- a browser bridge implementation that matches desktop payload shapes

## Approved Target Architecture

### Canonical transport

The target transport is a Python-native localhost HTTP runtime hosted from `services/python-core`, implemented with the standard library only in phase 1.

### Compatibility window

The repository may temporarily contain partially migrated code while cleanup is in progress, but the intended end state is **no subprocess/stdout JSON bridge and no compatibility shim**.

### Ownership boundaries

- **Python runtime owns** orchestration, storage, request/task state, cancellation, and HTTP route semantics.
- **Desktop runtime wrapper owns** start, health-check, port attach/retry, shutdown, and token injection for protected calls.
- **Frontend bridge layer owns** transport adaptation and response normalization, not business logic.

## Lane-by-Lane Execution Notes

### Lane 1 — Python core HTTP runtime

Required shape:

- bind loopback only
- expose parity routes under `/api/v1/...`
- preserve existing success/error envelopes
- keep `error.details.request_state` populated on failures
- preserve current long-task `task_id` + `showTaskState` behavior
- provide `GET /healthz`
- provide protected admin/config flows, including shutdown

Implementation guardrails:

- no new server dependency in phase 1
- reuse existing orchestration and store modules instead of duplicating logic in a second backend layer
- treat the HTTP handler as a thin facade over the current Python core

### Lane 2 — Desktop lifecycle and client cutover

Required shape:

- desktop starts or attaches to the localhost runtime
- desktop injects the runtime token on protected requests
- desktop keeps the current `DesktopBridge` contract stable
- desktop streaming switches from Tauri `Channel` plumbing to HTTP/SSE parsing
- browser gets the same-machine HTTP bridge instead of a hard failure path

Implementation guardrails:

- keep lifecycle ownership in the desktop layer
- avoid teaching page components about transport differences
- do not leave a compatibility shim behind once HTTP is validated

### Lane 3 — Parity, security, and browser verification

Required coverage:

- route parity against the current bridge contract
- long-task parity for render/download/poll/cancel flows
- stream chunk/final-envelope parity
- browser-vs-desktop payload equivalence
- loopback-only bind and protected endpoint checks
- stale-process and port-conflict lifecycle coverage

Implementation guardrails:

- negative-path tests must verify `error.details.request_state`
- browser parity should compare schemas and behavior, not just HTTP status codes
- the shim should never become the only passing path late in the migration

## Migration Pressure Points To Watch

1. **Do not weaken `request_state` validation.** `apps/desktop/src/lib/requestState.ts` already rejects malformed shapes; transport changes must adapt to it instead of loosening it.
2. **Do not collapse long-task responses into terminal responses.** Script Workbench, Voice Studio, and `ModelsPage` depend on immediate acks plus polling.
3. **Do not add browser-only response variants.** Desktop and browser should share one payload contract.
4. **Do not keep two first-class transports indefinitely.** The subprocess bridge must be deleted, not merely deprioritized.
5. **Do not move business logic into the Tauri layer.** The current layering is a strength and should survive the HTTP cutover.

## Verification Gates

The approved plan already defines the exact verification commands. The important repo-level interpretation is:

- `services/python-core` must prove envelope, task-state, and security parity
- `apps/desktop` must prove frontend/type/runtime integration still holds
- `apps/desktop/src-tauri` must prove the native shell still builds against the new lifecycle/client boundary
- browser parity must be treated as a first-class gate, not a follow-up cleanup task

Until those gates pass, the HTTP path should be treated as incomplete and the repository should not claim convergence is done.

## Recommended Documentation Handoff

As implementation lands, keep this document aligned with:

- `docs/architecture/desktop-tauri-bridge.md` for current-vs-target bridge boundaries
- `README.md` for developer bootstrap and runtime expectations
- parity/security/browser test files for executable proof of the documented contract
