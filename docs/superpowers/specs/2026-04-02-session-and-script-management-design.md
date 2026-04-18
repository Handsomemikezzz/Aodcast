# Session and Script Management Design

## 1. Objective

Align chat/script management behavior with mainstream LLM web clients for session-level operations while preserving current MVP interview/generation flow.

This slice adds bounded management capabilities only:

- chat sessions: rename, search, soft delete, restore
- scripts: edit, soft delete, restore, revision history, rollback

Out of scope for this slice:

- message-level edit/regenerate/branch
- multi-branch conversation trees
- permanent hard-delete UI flow

## 2. Product Behavior

### Session Management

- Users can rename a session topic.
- Users can search sessions by topic or creation intent.
- Session deletion is soft delete:
  - normal listing hides deleted sessions
  - deleted sessions are visible in a trash view
  - deleted sessions can be restored within 30 days
- After 30 days, restore is rejected by backend rules.

### Script Management

- **Multiple scripts per session**: Each script generation from the same chat creates a **new** script entity (new `script_id`, new persisted blob). Earlier scripts remain available; generation is **not** modeled as overwriting a single “current script” file.
- Users can continue editing scripts as today.
- Each script save creates a revision snapshot **within that script record**.
- Users can view revision history and rollback to a selected revision.
- Script delete is soft delete for current script content:
  - delete keeps revision history
  - restore recovers the deleted script content within 30 days

## 3. Data Contracts

### Session Record Additions

- `deleted_at: string` (ISO time, empty when active)

### Script Record Additions

- `deleted_at: string` (ISO time, empty when active)
- `revisions: ScriptRevision[]`

### Script Revision Record

- `revision_id: string`
- `source: "save" | "rollback" | "delete" | "restore"`
- `content: string`
- `created_at: string`

## 4. Backend and Bridge Operations

New operations:

- `rename_session`
- `delete_session`
- `restore_session`
- `list_projects` extended with `include_deleted` + `search_query`
- `delete_script`
- `restore_script`
- `list_script_revisions`
- `rollback_script_revision`

All operations return normalized `request_state`.

## 5. UX Constraints

- Default chat/script lists only show active sessions.
- Trash mode explicitly shows soft-deleted sessions.
- Restore availability is governed by backend retention check.
- Rollback is an explicit user action and creates a new revision entry.

## 6. Reliability and Error Handling

- Restore after retention window returns clear, actionable error.
- Rollback to missing revision returns deterministic error.
- Session soft delete does not physically remove persisted data.
- Existing interview, script generation, and render flows remain backward compatible.

## 7. Validation Scope

- Python tests:
  - session soft delete/restore + 30-day rule
  - search/list filters for active/deleted views
  - script revision append and rollback behavior
  - script soft delete/restore behavior
- Bridge and UI checks:
  - new commands invoked through Rust and desktop bridge without protocol drift
  - existing pages remain functional with unchanged flows
