# Maintenance Subagents

## Purpose

These subagents exist to keep the repository maintainable under long-term agent-driven development.

## Roles

### `spec-keeper`

Mission:
Keep product, architecture, and governance documents aligned with actual repository state and implementation behavior.

Outputs:

- drift reports
- targeted doc updates
- missing-spec warnings

### `code-pruner`

Mission:
Reduce codebase entropy by identifying dead code, duplicate paths, obsolete scaffolding, and oversized files.

Outputs:

- cleanup proposals
- stale file lists
- refactor candidates

### `contract-guard`

Mission:
Protect the boundary between frontend and backend by checking schema consistency, state naming, and contract drift.

Outputs:

- contract mismatch reports
- schema update requirements
- interface review notes

### `doc-syncer`

Mission:
Keep README, operational docs, example configs, and onboarding docs synchronized with the codebase.

Outputs:

- doc refresh changes
- stale documentation alerts
- example update requests

### `repo-curator`

Mission:
Keep the repository structurally healthy by policing temporary files, misplaced assets, and directory sprawl.

Outputs:

- repository hygiene reports
- relocation recommendations
- archive or deletion candidates

## Invocation Guidance

- Use these roles as maintenance agents, not feature agents.
- Trigger them after major structural or contract changes.
- Run them periodically to prevent silent repository decay.

