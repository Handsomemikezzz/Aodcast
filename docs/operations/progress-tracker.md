# Progress Tracker

## Current Phase

Active milestone: `Post-MVP slice - Desktop UI / backend integration`

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
- local MLX dependency and model-path checks are available through the project venv; runtime availability remains host-dependent
- Milestone 6 exit criteria functionally satisfied
- Milestone 7 hygiene script and hardening report added
- maintenance docs now point to a repeatable local sweep
- high-risk coverage expanded around local MLX capability and draft fallback rendering
- Milestone 7 exit criteria functionally satisfied
- real desktop bridge interface extracted from the mock implementation
- Python CLI now supports machine-readable bridge envelopes plus list/create/save-script actions
- Tauri Rust command gateway added for Python orchestration calls
- local MLX provider now uses a real `mlx-audio` runner shape instead of placeholder waveform generation
- default macOS model target is now `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit`
- project `.venv` now has `mlx_audio` installed and capability checks can resolve the Hugging Face repo-id path
- desktop shell has been redesigned into route-based `Chat / Script / Models / Settings` workspaces
- model catalog actions are exposed from the UI and already mapped onto bridge commands
- desktop `Settings` now reads/writes global TTS config through the real Tauri bridge
- Python config contracts now use local `api_key` values (the `api_key_env` path has been removed)
- model catalog is now explicitly TTS-only for the current MVP slice
- Python bridge success/failure envelopes now carry a shared `request_state` contract
- `Chat` / `Edit` / `Generate` pages now use unified loading-error-action request-state handling
- Python bridge now persists long-task states and exposes `show_task_state` polling for `download_model` and `render_audio`
- `Models` and `Settings` pages now follow the same request-state handling style used by `Chat`/`Script`
- long-running tasks now report incremental `progress_percent` updates in UI (download marker parsing + render heartbeat)
- long-running tasks now support cooperative cancellation through `cancel_task` with `cancelling` and `cancelled` phases
- local MLX capability checks now include a subprocess runtime-bootstrap probe so `import mlx.core` crashes are reported as unavailable capability reasons instead of hard render-time aborts
- session management now supports rename/search/soft-delete/restore with a 30-day restore window
- script management now supports soft-delete/restore plus revision history and rollback
- DMG packaging now succeeds in this environment by running desktop build with `CI=true` (bundler `--skip-jenkins` path), avoiding Finder AppleScript timeout `-1712`

### In Progress

- no active packaging regressions tracked in this slice

### Blockers

- real `local_mlx` rendering can still be host-limited when MLX fails native Metal bootstrap (`NSRangeException`) before Python can recover

## Historical Snapshot Notice

The milestone tables below are preserved as historical snapshots captured at the time each milestone was active.
Current execution constraints and environment notes should be read from `AGENTS.md` first.

## Milestone 0 Tasks

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Probe toolchain and repo state | lead/coordinator | done | `pnpm`, `node`, `uv`, `python3`, and `cargo` are available in the current environment |
| Add persistent progress tracking | lead/coordinator | done | This file is the active bootstrap tracker |
| Scaffold desktop workspace | `desktop-builder` | done | Vite/Tauri file layout created; compile checks run locally, DMG bundling remains the current packaging blocker |
| Scaffold Python core | `orchestration-builder` | done | App config, session model, storage, and boot entrypoint created |
| Add dev scripts | lead/coordinator | done | Toolchain check, Python boot, and desktop boot scripts added |
| Verify local boot paths | `quality-runner` | done | Python, frontend typecheck, and native compile checks are repeatably runnable in this environment |

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
| Validate bridge protocol and desktop types | `quality-runner` | done | Python bridge tests, `pnpm check`, `cargo check`, and `pnpm --dir apps/desktop tauri:build` now pass in this environment (DMG build uses `CI=true` to skip Finder styling AppleScript) |

## Post-MVP Slice: MLX Qwen3 Runner

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Replace placeholder local waveform generation | `provider-integrator` | done | Local MLX now routes through `runner.py` and `mlx_audio.tts.generate` |
| Add model preset and capability resolution | `provider-integrator` | done | Default repo-id target is `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit` |
| Validate capability and mocked runner flow | `quality-runner` | done | Python tests pass and capability now resolves the repo-id path with `mlx_audio` installed |
| Run first real model render | `quality-runner` | pending | Not executed yet because it would require pulling the actual model weights |

## Post-MVP Slice: Desktop UI / Backend Integration

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Reflect redesigned shell in docs | `doc-syncer` | done | Desktop architecture docs now describe the route-based shell and new page responsibilities |
| Keep `Chat` and `Script` on the real bridge | `desktop-builder` | done | Main workflow pages already call the bridge-backed session commands |
| Wire model management end to end | `provider-integrator` | done | Models page commands are present across frontend, Rust, and Python |
| Persist settings through the bridge | `desktop-builder` | done | `SettingsPage` now calls `show_tts_config` / `configure_tts_provider` via Tauri and Python config store |
| Remove `api_key_env` contract path | `provider-integrator` | done | Domain models, CLI args, providers, and tests now use local `api_key` fields |
| Normalize loading, error, and long-task progress states | `orchestration-builder` | done | Shared request-state contract + task-state polling landed across Chat/Edit/Generate/Models/Settings, including incremental progress percentages |
| Add long-task cancellation semantics | `orchestration-builder` | done | `cancel_task` now marks task-state `cancelling`, tasks cooperatively stop into `cancelled`, and Generate/Models pages expose cancel actions |

## Post-MVP Slice: Session and Script Management

| Task | Owner Role | Status | Notes |
| --- | --- | --- | --- |
| Extend shared contracts for soft-delete and script revisions | `schema-steward` | done | Session/script schemas now include deletion metadata and revision fields |
| Add backend operations for session/script lifecycle management | `orchestration-builder` | done | Python core now supports rename/search/list filtering, soft-delete/restore, revision listing, and rollback |
| Wire Rust and desktop bridge commands | `desktop-builder` | done | New commands are exposed in Tauri and desktop bridge interfaces |
| Add desktop chat/script management UX | `desktop-builder` | done | Chat history now supports search/trash/restore/rename; script editor supports trash, revisions, and rollback |
| Validate behavior and retain cleanup discipline | `quality-runner` | done | Python tests, TS check, and Cargo check all pass after cleanup and integration |

## Next-Step Plan

1. Add task history/retention policy for `.local-data/runtime/request-state` entries.
2. Add optional notarization/signing validation for release-ready DMG distribution.

## Update Rules

- Update this file when a task changes status.
- If a blocker or recurring mistake is discovered, add the short operational note to `AGENTS.md` and summarize the impact here.
- Keep entries short and incremental; do not rewrite the full history on every update.
