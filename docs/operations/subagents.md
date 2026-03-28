# Subagents

## Purpose

These subagents exist to make Aodcast sustainable under long-term agent-driven development. They are split into delivery roles and maintenance roles.

## Delivery Roles

### `desktop-builder`

Mission:
Implement and evolve the Tauri app shell, screen flow, configuration UI, script editor, and desktop-facing interaction states.

Owned areas:

- `apps/desktop`

Outputs:

- UI implementation changes
- frontend state wiring
- desktop interaction refinements

### `orchestration-builder`

Mission:
Implement the Python interview workflow, readiness evaluation, script generation flow, task lifecycle, and failure recovery.

Owned areas:

- `services/python-core/app/orchestration`
- `services/python-core/app/domain`
- `services/python-core/app/storage`

Outputs:

- orchestration logic
- domain state changes
- persistence flow updates

### `provider-integrator`

Mission:
Implement and maintain external model and audio adapters without leaking vendor-specific logic into orchestration.

Owned areas:

- `services/python-core/app/providers`

Outputs:

- provider adapters
- provider configuration support
- provider capability notes

### `schema-steward`

Mission:
Define and update shared contracts between the desktop shell and Python core.

Owned areas:

- `packages/shared-schemas`

Outputs:

- schema definitions
- contract changes
- compatibility notes

### `quality-runner`

Mission:
Own test coverage for orchestration, persistence, adapter boundaries, and critical user flows.

Owned areas:

- `services/python-core/tests`
- frontend test areas when introduced

Outputs:

- test plans
- regression checks
- risk reports

## Maintenance Roles

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

- Use delivery agents for bounded implementation work.
- Use maintenance agents to control repository entropy.
- Trigger maintenance agents after major structural or contract changes.
- Run maintenance agents periodically to prevent silent repository decay.
