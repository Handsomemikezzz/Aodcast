# EchoMind Podcast MVP Implementation Plan

## 1. Plan Goal

This plan turns the approved MVP design into a staged implementation roadmap for a local-first macOS desktop application built with Tauri and a Python orchestration core.

Primary sources of truth:

- [MVP design spec](/Users/chuhaonan/codeMIni-hn/github/Aodcast/docs/superpowers/specs/2026-03-28-echomind-podcast-mvp-design.md)
- [AGENTS.md](/Users/chuhaonan/codeMIni-hn/github/Aodcast/AGENTS.md)
- [Multi-agent workflow](/Users/chuhaonan/codeMIni-hn/github/Aodcast/docs/operations/multi-agent-workflow.md)

## 2. Delivery Strategy

Build the MVP in thin vertical slices, but do not start with UI polish. The first milestone should establish contracts, persistence, and the interview state machine because those are the hardest parts to retrofit later.

Recommended order:

1. contracts and project scaffolding
2. persistence and session model
3. interview orchestration
4. script generation flow
5. remote TTS provider flow
6. local MLX TTS provider flow
7. desktop UI integration
8. recovery, testing, and maintenance hardening

## 3. Milestones

### Milestone 0: Repository Bootstrap

Goal:
Turn the current documentation skeleton into a runnable project workspace.

Tasks:

- initialize Tauri app skeleton in `apps/desktop`
- initialize Python project skeleton in `services/python-core`
- set up local dev scripts in `scripts/dev`
- add basic contributor setup notes to `README.md`

Primary agents:

- `desktop-builder`
- `orchestration-builder`
- `repo-curator`

Exit criteria:

- desktop app boots
- Python core boots
- local development commands are documented

### Milestone 1: Shared Contracts and Session Persistence

Goal:
Define the core session, transcript, script, and artifact contracts, then persist them locally.

Tasks:

- define JSON schemas for `Session`, `Transcript`, `Script`, and `Artifact`
- define state enum and transition metadata
- implement project/session storage layout in Python core
- add recovery loading path for interrupted sessions

Primary agents:

- `schema-steward`
- `orchestration-builder`
- `quality-runner`

Exit criteria:

- contracts exist in `packages/shared-schemas`
- Python core can create and reload sessions from disk
- session state survives restart

### Milestone 2: Interview Orchestration Core

Goal:
Implement the guided interview loop and readiness evaluation.

Tasks:

- implement interview state transitions
- implement readiness heuristic checks
- define prompt assembly inputs
- expose interview-turn endpoints or command handlers for the desktop app

Primary agents:

- `orchestration-builder`
- `schema-steward`
- `quality-runner`

Exit criteria:

- the system can accept a topic and continue through multiple interview turns
- readiness checks can loop back to interview mode
- user-triggered stop and AI-suggested stop both work

### Milestone 3: Script Generation

Goal:
Generate a structured solo podcast draft from the interview transcript.

Tasks:

- define LLM provider interface
- implement configurable remote LLM adapter
- implement script generation workflow in orchestration core
- persist draft script separately from user-edited script

Primary agents:

- `provider-integrator`
- `orchestration-builder`
- `quality-runner`

Exit criteria:

- a transcript can produce a draft script
- provider configuration is local and user-editable
- failures preserve the transcript and session state

### Milestone 4: Desktop Editing Flow

Goal:
Allow the user to review and directly edit the generated draft.

Tasks:

- build session list and session detail screens
- build interview view and draft view
- add direct text editing and save flow
- surface session states and failure messages

Primary agents:

- `desktop-builder`
- `schema-steward`
- `quality-runner`

Exit criteria:

- user can complete the interview loop from the app
- user can edit and save a script draft
- UI reflects backend state transitions accurately

### Milestone 5: Remote TTS Path

Goal:
Render final audio from the user-approved script through a remote TTS provider.

Tasks:

- define TTS provider interface
- implement remote TTS adapter
- support provider selection and configuration
- persist audio artifacts and metadata

Primary agents:

- `provider-integrator`
- `orchestration-builder`
- `desktop-builder`

Exit criteria:

- edited script can be rendered to audio through a remote provider
- final transcript and audio file are persisted
- TTS failure allows retry without losing script data

### Milestone 6: Local MLX TTS Path

Goal:
Add the local macOS-native TTS path without changing the main workflow.

Tasks:

- implement MLX-backed local TTS adapter
- support local model path and runtime checks
- add capability detection and fallback messaging
- document local setup and limitations

Primary agents:

- `provider-integrator`
- `desktop-builder`
- `doc-syncer`

Exit criteria:

- local TTS can render the same final script artifact flow
- missing model or runtime errors are recoverable
- users can fall back to remote TTS cleanly

### Milestone 7: Hardening and Repository Hygiene

Goal:
Stabilize the MVP for open source usage and future agent-driven iteration.

Tasks:

- add test coverage for high-risk orchestration paths
- review repo layout for misplaced files
- update docs to match implemented behavior
- run cleanup and contract checks

Primary agents:

- `quality-runner`
- `spec-keeper`
- `doc-syncer`
- `code-pruner`
- `repo-curator`

Exit criteria:

- critical flow tests exist
- docs match the shipped workflow
- no obvious contract drift or stale bootstrap artifacts remain

## 4. Task Dependencies

### Must Happen First

- Milestone 1 before Milestones 2 through 6
- schema changes before dependent frontend or provider work

### Can Overlap Safely

- Milestone 4 can begin once Milestone 1 contracts stabilize
- provider implementation can overlap with UI work once orchestration interfaces are stable
- documentation updates can be prepared in parallel but should land with the related feature changes

## 5. Multi-Agent Assignment Model

Use one coordinator and bounded specialist agents.

### Suggested Core Team

- lead/coordinator
- `schema-steward`
- `orchestration-builder`
- `provider-integrator`
- `desktop-builder`
- `quality-runner`

### Suggested Hygiene Team

- `spec-keeper`
- `doc-syncer`
- `code-pruner`
- `contract-guard`
- `repo-curator`

## 6. Definition of Done Per Task

Each task should be considered complete only if all are true:

- implementation fits the owned directory boundary
- docs were updated if behavior or workflow changed
- contracts were updated first if boundaries changed
- failure cases were considered
- cleanup follow-up is not silently deferred

## 7. First Implementation Slice

The best first slice is:

1. scaffold Tauri and Python projects
2. define shared schemas
3. implement local session persistence
4. implement the interview state machine without real provider calls
5. connect a minimal desktop screen to create a session and step through mocked interview turns

This slice reduces the highest-risk unknowns before spending effort on provider integration or audio rendering.

