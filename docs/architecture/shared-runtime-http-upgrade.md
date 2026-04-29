# Shared Runtime HTTP Architecture

## Purpose

This document records the implemented localhost HTTP runtime architecture that replaced the historical subprocess/stdout JSON bridge for business operations. It also captures the extension rules and verification gates that keep desktop and browser flows on one contract.

## Current Ground Truth

The repo now uses `services/python-core/app/api/http_runtime.py` as the canonical business-operation runtime. Tauri may still spawn and supervise that runtime process, but React business calls go through the HTTP bridge rather than a subprocess/stdout JSON bridge.

The current architecture is shaped by these constraints:

- `apps/desktop/src/lib/desktopBridge.ts` is the canonical UI contract and already exposes the full session/script/model/task surface the app depends on.
- `apps/desktop/src/lib/httpBridge.ts` is the shared transport boundary for desktop and same-machine browser flows.
- `apps/desktop/src/lib/requestState.ts` is the normalization boundary for `request_state`, run-token, and cancellation-transition semantics.
- Script Workbench, Voice Studio, and `apps/desktop/src/pages/ModelsPage.tsx` assume the long-task parity contract of immediate ack + later `showTaskState(task_id)` polling.
- `apps/desktop/src/pages/ChatPage.tsx` already assumes incremental streaming deltas plus a final structured envelope.
- the previous browser hard-stop path has been removed; browser flows now target the same localhost HTTP runtime contract.
- `services/python-core/pyproject.toml` keeps the HTTP server path stdlib-only; provider integrations remain isolated behind adapters.

## Review Findings

### 1. The `DesktopBridge` interface is the contract anchor

Preserve the `DesktopBridge` method set when extending runtime behavior. Page components should stay stable while transport details remain inside `httpBridge.ts` and the Python HTTP runtime.

### 2. `request_state` parity is already encoded in UI behavior

Script Workbench, Voice Studio, `ModelsPage`, and the shared request-state helpers already rely on:

- stable `operation`
- progress-bearing `running` updates
- terminal `succeeded` / `failed` / `cancelled` states
- failure recovery through `error.details.request_state`

The HTTP runtime should preserve those semantics exactly instead of teaching the UI a new error model.

LLM-dependent UI actions use the protected `GET /api/v1/config/llm/preflight` route to decide whether interview and script-generation actions can run. Keep provider readiness rules in the Python runtime so new providers do not require duplicated React-side validation.

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

### 5. Browser parity is a runtime/bootstrap contract

The browser path is intentionally contract-compatible with Tauri flows. It depends on:

- a loopback-only runtime that can be started or attached safely
- a same-machine bootstrap/token flow for protected endpoints
- a browser bridge implementation that matches desktop payload shapes

## Current Architecture

### Canonical transport

The canonical transport is a Python-native localhost HTTP runtime hosted from `services/python-core` and implemented with the standard library server stack.

### Ownership boundaries

- **Python runtime owns** orchestration, storage, request/task state, cancellation, and HTTP route semantics.
- **Desktop runtime wrapper owns** start, health-check, port attach/retry, shutdown, and token injection for protected calls.
- **Frontend bridge layer owns** transport adaptation and response normalization, not business logic.

## Extension Notes

### Python core HTTP runtime

Required shape:

- bind loopback only
- expose parity routes under `/api/v1/...`
- preserve existing success/error envelopes
- keep `error.details.request_state` populated on failures
- preserve current long-task `task_id` + `showTaskState` behavior
- provide `GET /healthz`
- provide protected admin/config flows, including shutdown

Implementation guardrails:

- do not add a server framework dependency unless an explicit architecture decision changes the stdlib runtime constraint
- reuse existing orchestration and store modules instead of duplicating logic in a second backend layer
- treat the HTTP handler as a thin facade over the current Python core

### Desktop lifecycle and client boundary

Required shape:

- desktop starts or attaches to the localhost runtime
- desktop injects the runtime token on protected requests
- desktop keeps the current `DesktopBridge` contract stable
- desktop streaming uses HTTP/SSE parsing through the shared bridge layer
- browser uses the same-machine HTTP bridge instead of a desktop-only hard stop

Implementation guardrails:

- keep lifecycle ownership in the desktop layer
- avoid teaching page components about transport differences
- do not reintroduce a compatibility shim for business operations

### Parity, security, and browser verification

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
- parity tests should fail if a new transport-specific shortcut becomes the only passing path

## Migration Pressure Points To Watch

1. **Do not weaken `request_state` validation.** `apps/desktop/src/lib/requestState.ts` already rejects malformed shapes; transport changes must adapt to it instead of loosening it.
2. **Do not collapse long-task responses into terminal responses.** Script Workbench, Voice Studio, and `ModelsPage` depend on immediate acks plus polling.
3. **Do not add browser-only response variants.** Desktop and browser should share one payload contract.
4. **Do not keep two first-class business transports.** New UI business operations must use the HTTP bridge contract.
5. **Do not move business logic into the Tauri layer.** The current layering is a strength and should survive the HTTP cutover.

## Verification Gates

The important repo-level verification interpretation is:

- `services/python-core` must prove envelope, task-state, and security parity
- `apps/desktop` must prove frontend/type/runtime integration still holds
- `apps/desktop/src-tauri` must prove the native shell still builds against the new lifecycle/client boundary
- browser parity must be treated as a first-class gate, not a follow-up cleanup task

These gates are the proof that the HTTP path remains converged after future cleanup or feature work.

## Recommended Documentation Handoff

When implementation changes, keep this document aligned with:

- `docs/architecture/desktop-tauri-bridge.md` for current bridge boundaries
- `README.md` for developer bootstrap and runtime expectations
- parity/security/browser test files for executable proof of the documented contract
