# Repository Layout

## Current Layout

This repository follows a local-first desktop app structure with explicit boundaries between UI, local runtime, shared contracts, documentation, and operations.

- `apps/desktop`: Tauri + React desktop shell.
  - `src/pages`: route-level page composition.
  - `src/pages/script-workbench`: Script Workbench-specific components and hooks.
  - `src/components`: shared presentational React components.
  - `src/lib`: bridge, request-state, audio URL, shell-helper, and reusable frontend utilities.
  - `src-tauri`: Rust desktop lifecycle and Tauri-only shell commands.
- `services/python-core`: local orchestration runtime.
  - `app/api`: localhost HTTP runtime, bridge envelopes, and serializers.
  - `app/cli`: CLI argument parsing and command entrypoint support.
  - `app/domain`: serializable domain records and config models.
  - `app/orchestration`: interview, script-generation, readiness, and audio-render business flows.
  - `app/providers`: LLM, remote TTS, local MLX TTS, and provider-specific helpers.
  - `app/runtime`: long-task state, request-state persistence, and cancellation primitives.
  - `app/storage`: filesystem-backed project/config persistence.
  - `tests`: Python unit and contract tests.
- `packages/shared-schemas`: JSON schemas shared across the frontend/backend contract.
- `docs`: maintained product, architecture, configuration, local MLX, and operations documentation.
- `examples`: tracked lightweight sample placeholders only; real user data and model weights stay out of git.
- `scripts`: development, maintenance, release, and model-download helpers.
- `.agent`: agent-facing checklists, task templates, prompts, and reports.

## Local-only / Generated Paths

These paths are intentionally ignored and must not be used for source files:

- `.local-data/`: local projects, exports, runtime state, and user configuration.
- `.omx/`, `.superpowers/`: local agent/runtime state.
- `.pnpm-store/`, `apps/desktop/node_modules/`, `services/python-core/.venv/`: dependency installs.
- `apps/desktop/dist/`, `apps/desktop/src-tauri/target/`, `__pycache__/`, `.ruff_cache/`: generated build/test/cache outputs.
- `models/`, `voicebox`: downloaded model weights and local experiments.
- `docs-local/`, `temp/`: private scratch notes and experiments.

## Design Intent

- Keep React page components free of orchestration business logic.
- Route all UI business calls through `apps/desktop/src/lib/*Bridge.ts` into the localhost Python HTTP runtime.
- Keep Tauri commands limited to lifecycle and native shell capabilities such as runtime startup, Finder reveal, and directory picking.
- Keep provider-specific code under `services/python-core/app/providers`.
- Keep request/task-state semantics reusable through shared runtime/frontend helpers instead of page-local copies.
- Keep executable contracts in `packages/shared-schemas` and parity tests before changing payload shape.
- Prefer deleting obsolete scaffolding over preserving placeholder files once a directory contains real tracked assets.
