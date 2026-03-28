# Progress Tracker

## Current Phase

Active milestone: `Post-MVP slice - Real Tauri bridge`

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
- remote TTS provider abstraction added
- TTS configuration storage added
- artifact export storage implemented
- remote audio rendering workflow implemented
- desktop workspace now surfaces artifact status and render action
- Milestone 5 exit criteria functionally satisfied
- local MLX TTS provider abstraction added
- local MLX capability detection added
- desktop workspace now surfaces local MLX capability and fallback messaging
- local MLX path is validated through tests and explicit failure-path CLI checks
- workspace-local Python venv created for MLX validation
- local MLX capability is now available through the project venv and placeholder model path
- Milestone 6 exit criteria functionally satisfied
- Milestone 7 hygiene script and hardening report added
- maintenance docs now point to a repeatable local sweep
- high-risk coverage expanded around local MLX capability and draft fallback rendering
- Milestone 7 exit criteria functionally satisfied
- real desktop bridge interface extracted from the mock implementation
- Python CLI now supports machine-readable bridge envelopes plus list/create/save-script actions
- Tauri Rust command gateway added for Python orchestration calls

### In Progress

- real Tauri bridge validation handoff
- native runtime compile blocked on missing Rust toolchain

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

## Milestone 5 Tasks

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Define TTS provider interface | `provider-integrator` | done | Remote TTS base, factory, mock adapter, and OpenAI-compatible adapter are in place |
| Add TTS configuration storage | `provider-integrator` | done | TTS config persists under `.local-data/config/tts.json` and is editable through CLI |
| Implement audio rendering workflow | `orchestration-builder` | done | Sessions now move through `audio_rendering` into `completed` with local artifact exports |
| Surface audio status in desktop shell | `desktop-builder` | done | Desktop workspace shows artifact paths and supports mock-backed audio rendering |
| Validate remote TTS flow | `quality-runner` | done | Python tests, CLI flow, frontend typecheck, and web build all pass |

## Milestone 6 Tasks

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Define local MLX provider path | `provider-integrator` | done | Local MLX provider, runtime detector, and capability report are implemented |
| Add local provider config fields | `provider-integrator` | done | TTS config now includes local runtime and model path fields |
| Integrate local provider into render flow | `orchestration-builder` | done | Audio rendering can select `local_mlx` and fails cleanly with preserved session state |
| Surface local capability in desktop shell | `desktop-builder` | done | Desktop workspace shows local MLX availability and fallback reasons |
| Validate local path and fallback | `quality-runner` | done | Tests pass; failure and success paths were both validated through the project venv and placeholder model path |

## Milestone 7 Tasks

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Add high-risk regression coverage | `quality-runner` | done | Audio rendering and local MLX capability coverage now include draft fallback and available-runtime success cases |
| Add repeatable repo hygiene script | `repo-curator` | done | Maintenance sweep now runs through `scripts/maintenance/run-repo-hygiene-check.sh` |
| Sync maintenance docs with implemented workflow | `doc-syncer` | done | README and maintenance playbook now point to the maintenance sweep and report location |
| Publish hardening report | `spec-keeper` | done | Report stored at `.agent/reports/2026-03-28-milestone-7-hardening-pass.md` |

## Post-MVP Slice: Real Tauri Bridge

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Extract frontend bridge contract from mock implementation | `desktop-builder` | done | `desktopBridge.ts`, `bridgeFactory.ts`, and `tauriBridge.ts` now own the bridge boundary |
| Add machine-readable Python CLI bridge mode | `orchestration-builder` | done | `--bridge-json`, `--list-projects`, `--create-session`, and `--save-script` are implemented |
| Add Rust command gateway | `desktop-builder` | done | Tauri commands now call the Python runner through `python_bridge.rs` |
| Validate bridge protocol and desktop types | `quality-runner` | in_progress | Python bridge tests and `pnpm check` pass; native Tauri compile still blocked by missing `cargo` |

## Update Rules

- Update this file when a task changes status.
- If a blocker or recurring mistake is discovered, add the short operational note to `AGENTS.md` and summarize the impact here.
- Keep entries short and incremental; do not rewrite the full history on every update.
