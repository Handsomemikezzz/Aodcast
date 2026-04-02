# Session and Script Management Implementation Plan

## 1. Plan Goal

Implement session/script lifecycle management aligned with the approved design:

- session rename/search/soft delete/restore
- script soft delete/restore
- script revision history and rollback
- 30-day restore window enforcement

Primary references:

- [Session and script management design](/Users/chuhaonan/codeMIni-hn/github/Aodcast/docs/superpowers/specs/2026-04-02-session-and-script-management-design.md)
- [AGENTS.md](/Users/chuhaonan/codeMIni-hn/github/Aodcast/AGENTS.md)

## 2. Delivery Slices

1. contracts and domain model extensions
2. storage + Python CLI operation handlers
3. Tauri/Rust + desktop bridge command wiring
4. desktop UI behaviors (chat and script pages)
5. tests, cleanup pass, and docs synchronization

## 3. Work Breakdown

### Slice A: Contracts and Domain Extensions

Tasks:

- extend shared schemas:
  - `session.schema.json`: add `deleted_at`
  - `script.schema.json`: add `deleted_at` and `revisions`
- extend Python domain models:
  - session soft-delete metadata and helpers
  - script revision model and mutation helpers

Exit criteria:

- schema and domain models compile and remain backward compatible with existing persisted records

### Slice B: Storage and Python CLI

Tasks:

- add filtered listing in `ProjectStore`:
  - include/exclude deleted sessions
  - search query filter
- add session operations:
  - rename
  - soft delete
  - restore with retention validation
- add script operations:
  - soft delete/restore
  - list revisions
  - rollback by revision id
- add corresponding CLI args and handlers in `app/main.py`
- keep `request_state` envelope consistent

Exit criteria:

- commands behave deterministically via `--bridge-json`
- restore after retention window fails with explicit error

### Slice C: Desktop Bridge and Tauri Commands

Tasks:

- add Rust command functions for all new backend operations
- register commands in `src-tauri/main.rs`
- add TypeScript bridge methods in:
  - `desktopBridge.ts`
  - `tauriBridge.ts`
  - `mockBridge.ts`
- extend related TS types for revisions/deletion metadata

Exit criteria:

- frontend can invoke all new operations through the real bridge
- mock bridge retains parity for development fallback

### Slice D: Desktop UI

Tasks:

- Chat page:
  - search input
  - rename action
  - soft delete action
  - trash toggle and restore action
- Script/Edit page:
  - script soft delete/restore
  - revision list panel
  - rollback action

Exit criteria:

- default view hides deleted sessions
- trash view supports restore
- rollback visibly updates editor content

### Slice E: Quality, Cleanup, Docs

Tasks:

- extend Python tests:
  - `test_project_store.py`
  - `test_cli_bridge.py`
- run targeted checks:
  - python tests for store/bridge flows
  - desktop type check (if dependency state allows)
- run subagent cleanup pass for redundant/legacy logic
- update governance/progress docs in same change set:
  - `AGENTS.md` (if ownership/contracts changed)
  - `docs/operations/progress-tracker.md`

Exit criteria:

- all relevant tests pass
- no redundant code introduced by this slice
- docs reflect shipped behavior

## 4. Dependency Rules

- schemas/domain changes land before bridge/UI usage
- CLI operations land before Rust/TypeScript command wiring
- backend restore semantics are source of truth; UI must not duplicate retention logic

## 5. Definition of Done

This plan is done only when:

- backend supports all approved operations
- frontend exposes and uses those operations in chat/script flows
- restore retention is enforced at 30 days
- script revisions support list and rollback
- tests pass and docs are updated in the same branch
