# Progress Tracker

## Current Phase

Active milestone: `Milestone 5 - Remote TTS Path`

## Status Summary

### Completed

- MVP design spec written and committed
- repository governance docs written and committed
- implementation plan written and committed
- multi-agent workflow and subagent roles defined
- root `AGENTS.md` established as a living governance file
- repository initialized under git
- local environment toolchain probed
- desktop scaffold file layout created
- Python core scaffold created
- shared schema stubs created
- Python bootstrap path verified
- Python storage tests passing
- bootstrap scripts added
- README bootstrap notes added
- desktop bootstrap script fail-fast path verified
- Milestone 0 repository bootstrap is functionally complete
- full project persistence for transcript, script, and artifact records
- recovery loading path for interrupted sessions
- shared schema contracts documented
- Milestone 1 exit criteria functionally satisfied
- Milestone 1 documentation closeout complete
- interview state machine implemented in Python core
- readiness evaluation implemented for the four MVP dimensions
- prompt assembly inputs defined for interview turns
- CLI command handlers added for interview start, reply, and finish
- Milestone 2 exit criteria functionally satisfied
- LLM provider abstraction added
- local LLM configuration storage added
- draft script generation workflow implemented
- script generation failure path preserves session data and records an error
- Milestone 3 exit criteria functionally satisfied
- desktop session list and detail workspace implemented
- desktop interview actions wired through a bounded bridge interface
- direct draft editing flow implemented in the desktop shell
- desktop bridge contract documented
- frontend dependency install, typecheck, and web build validation completed
- Milestone 4 exit criteria functionally satisfied

### In Progress

- Milestone 5 TTS provider interface planning
- remote TTS configuration and generation workflow design
- desktop integration planning for final audio status

### Blockers

- Rust toolchain is not currently available on `PATH`, so native Tauri boot verification cannot run yet

## Milestone 0 Tasks

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Probe toolchain and repo state | lead/coordinator | done | `pnpm`, `node`, `uv`, `python3` available; `cargo` missing |
| Add persistent progress tracking | lead/coordinator | done | This file is the active bootstrap tracker |
| Scaffold desktop workspace | `desktop-builder` | done | Vite/Tauri file layout created; native runtime still blocked by missing Rust toolchain |
| Scaffold Python core | `orchestration-builder` | done | App config, session model, storage, and boot entrypoint created |
| Add dev scripts | lead/coordinator | done | Toolchain check, Python boot, and desktop boot scripts added |
| Verify local boot paths | `quality-runner` | in_progress | Python verified and tested; desktop script now fails fast with a clear Rust toolchain message |

## Milestone 1 Tasks

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Harden shared schemas | `schema-steward` | done | Session, Transcript, Script, and Artifact contracts are aligned with current Python models |
| Persist full project records | `orchestration-builder` | done | Session, transcript, script, and artifact records now persist under each session directory |
| Add recovery loading path | `orchestration-builder` | done | Store can rebuild a full `SessionProject` from disk |
| Validate storage round trips | `quality-runner` | done | Python tests now cover full project recovery and session listing |

## Milestone 2 Tasks

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Implement interview state machine | `orchestration-builder` | done | Sessions now move between `interview_in_progress`, `readiness_evaluation`, and `ready_to_generate` |
| Add readiness evaluation | `orchestration-builder` | done | Heuristic covers topic context, viewpoint, detail, and conclusion |
| Define prompt assembly inputs | `schema-steward` | done | Prompt input object includes topic, intent, missing dimensions, and strategy layers |
| Expose orchestration interface | `orchestration-builder` | done | CLI handlers exist for start, reply, finish, and session inspection |
| Validate interview loop | `quality-runner` | done | Tests and CLI validation confirm looped questioning and ready-to-generate transitions |

## Milestone 3 Tasks

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Define LLM provider interface | `provider-integrator` | done | Provider base, factory, mock adapter, and OpenAI-compatible adapter are in place |
| Add local provider configuration | `provider-integrator` | done | LLM config persists under `.local-data/config/llm.json` and is editable through CLI |
| Implement draft generation workflow | `orchestration-builder` | done | Sessions now move from `ready_to_generate` to `script_generated` through the generation service |
| Preserve failure state and retry path | `orchestration-builder` | done | Generation failures mark the session as `failed` and preserve transcript/script data |
| Validate script generation flow | `quality-runner` | done | Tests cover success, failure, and invalid-state paths; CLI flow produces a draft |

## Milestone 4 Tasks

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Build session list and detail screens | `desktop-builder` | done | Sidebar and detail workspace are implemented in the desktop shell |
| Add interview interaction flow | `desktop-builder` | done | The desktop shell can start interviews, submit replies, and request finish through the bridge |
| Add direct draft editing flow | `desktop-builder` | done | The workspace supports draft generation and direct script editing |
| Review backend-to-desktop contract | `schema-steward` | done | Desktop types and bridge interface are aligned with the current backend shapes |
| Validate desktop implementation | `quality-runner` | done | `pnpm check` and `pnpm build:web` both pass after installing desktop dependencies |

## Update Rules

- Update this file when a task changes status.
- If a blocker or recurring mistake is discovered, add the short operational note to `AGENTS.md` and summarize the impact here.
- Keep entries short and incremental; do not rewrite the full history on every update.
