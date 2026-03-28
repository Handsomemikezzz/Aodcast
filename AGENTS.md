# AGENTS.md

## Purpose

This file is the root collaboration contract for Aodcast. It exists to keep multi-agent development coherent as the repository, architecture, and workflows evolve.

`AGENTS.md` is a living governance file. It must be updated whenever one of the following changes:

- repository structure or ownership boundaries
- shared contracts between frontend and backend
- core product flow or state machine
- maintenance and cleanup workflow
- subagent roles, responsibilities, or triggers

If implementation changes invalidate this file, update `AGENTS.md` in the same change set.

## Product Scope

Current source of truth: [docs/superpowers/specs/2026-03-28-echomind-podcast-mvp-design.md](/Users/chuhaonan/codeMIni-hn/github/Aodcast/docs/superpowers/specs/2026-03-28-echomind-podcast-mvp-design.md)
Implementation plan: [docs/superpowers/plans/2026-03-28-echomind-podcast-mvp-implementation-plan.md](/Users/chuhaonan/codeMIni-hn/github/Aodcast/docs/superpowers/plans/2026-03-28-echomind-podcast-mvp-implementation-plan.md)

Current MVP:

- platform: macOS desktop app
- frontend: Tauri app shell
- backend: local Python orchestration core
- input: text topic only
- output: solo podcast script plus final audio
- LLM: user-configured API provider
- TTS: remote API provider or local MLX-backed provider

Out of scope for the current MVP:

- speech-to-text input
- long-term user memory
- multi-host podcast formats
- cloud backend dependency
- voice cloning

## Repository Map

- `apps/desktop`: Tauri UI and app shell
- `services/python-core`: interview orchestration, script generation, provider dispatch, storage
- `packages/shared-schemas`: shared data contracts and schemas
- `docs/product`: product-facing docs
- `docs/architecture`: architecture and repository layout docs
- `docs/operations`: agent governance, maintenance playbooks, subagent definitions
- `.agent`: prompts, checklists, templates, and reports used by agents

## Ownership Rules

- UI-focused agents should work inside `apps/desktop` unless a schema change is required.
- backend-focused agents should work inside `services/python-core` unless a schema change is required.
- cross-boundary changes must update shared contracts first in `packages/shared-schemas`.
- provider-specific logic belongs only under `services/python-core/app/providers`.
- interview state logic belongs only under `services/python-core/app/orchestration`.
- operational rules belong in `docs/operations` and `AGENTS.md`, not in scattered ad hoc notes.
- desktop bridge calls must flow through `apps/desktop/src/lib/*Bridge.ts -> src-tauri commands -> python_bridge`, not from React components directly to shell commands.
- machine-readable Python bridge calls must keep stdout as a single JSON envelope when `--bridge-json` is set.
- model-specific runtime logic belongs inside provider runner/runtime modules, not in orchestration or desktop files.

## Change Protocol

Before substantial implementation work:

1. confirm the relevant source-of-truth doc
2. identify the owned directory boundary
3. update shared schema or governance docs first if the change crosses boundaries
4. implement the smallest complete change set
5. update affected docs before closing the task

When a change affects the product flow, architecture, or repo governance, update:

- [AGENTS.md](/Users/chuhaonan/codeMIni-hn/github/Aodcast/AGENTS.md)
- the active spec or architecture doc under `docs/`

## Code Generation Rules

- Prefer small, single-purpose files.
- Do not duplicate provider logic across orchestration or UI layers.
- Avoid adding framework glue where a simple interface will do.
- Keep internal domain models separate from external provider payloads.
- Favor explicit interfaces and replaceable adapters over vendor-coupled logic.

## Documentation Rules

- Treat docs as maintained assets, not one-time output.
- If code changes behavior, state shape, directory ownership, or operator workflow, update the related docs in the same task.
- Add new operational conventions to `docs/operations` and summarize cross-cutting ones here.

## Maintenance Subagents

The repository should be maintained continuously by specialized cleanup-oriented subagents. Their definitions live in [docs/operations/subagents.md](/Users/chuhaonan/codeMIni-hn/github/Aodcast/docs/operations/subagents.md).

Minimum maintenance roles:

- `spec-keeper`
- `code-pruner`
- `contract-guard`
- `doc-syncer`
- `repo-curator`

Maintenance cadence and triggers live in [docs/operations/maintenance-playbook.md](/Users/chuhaonan/codeMIni-hn/github/Aodcast/docs/operations/maintenance-playbook.md).

## Delivery Workflow

Feature delivery should follow the staged plan in [docs/superpowers/plans/2026-03-28-echomind-podcast-mvp-implementation-plan.md](/Users/chuhaonan/codeMIni-hn/github/Aodcast/docs/superpowers/plans/2026-03-28-echomind-podcast-mvp-implementation-plan.md).

When using multiple agents:

- assign one bounded area per agent
- treat schema and governance updates as first-class tasks
- merge contract changes before dependent implementation work
- run maintenance agents after structural or cross-boundary changes
- if teammate spawning is unavailable in the current runtime, the lead agent must still follow the same task boundaries and keep status updates in `docs/operations/progress-tracker.md`

Feature and maintenance role definitions live in [docs/operations/subagents.md](/Users/chuhaonan/codeMIni-hn/github/Aodcast/docs/operations/subagents.md).

## Known Execution Notes

- 2026-03-28: Do not assume the Rust toolchain is installed. Check `command -v cargo` before attempting to run or validate Tauri commands. In the current environment, `pnpm`, `node`, and `uv` are available, but `cargo` and `rustup` are not on `PATH`.
- 2026-03-28: Do not run a newly created script in parallel with its `chmod +x` step. Apply permissions first, then execute the script sequentially, otherwise permission races can produce false negatives.
- 2026-03-28: Frontend dependency installation may fail inside the sandbox with npm registry `EPERM` network errors. If `pnpm install` is required for validation, rerun it with escalated permissions instead of assuming the lockfile or package manager is broken.
- 2026-03-28: Do not run state-dependent CLI workflow commands for the same session in parallel. Operations like `start-interview`, `reply-session`, `generate-script`, and `render-audio` must be sequenced, or later steps may observe stale session state and fail for the wrong reason.
- 2026-03-28: The local MLX TTS path is runtime-gated. Before trying `local_mlx`, check `--show-local-tts-capability`. The project now uses `services/python-core/.venv` for local MLX validation, and `./scripts/dev/run-python-core.sh` prefers that interpreter automatically. Do not assume bare system `python3` has the same MLX availability as the project venv.
- 2026-03-28: Git writes may be sandbox-restricted even when normal file edits succeed. If `git commit` fails with `.git/index.lock: Operation not permitted`, rerun the commit with escalated permissions instead of treating it as a repository corruption issue.
- 2026-03-28: Transcript exports intentionally normalize to a trailing newline. When validating `transcript.txt`, compare normalized content or include the newline in expectations; this is storage behavior, not an audio-rendering regression.
- 2026-03-28: `git add .` may appear to succeed in the sandbox without actually staging changes. If `git status --short` still shows unstaged files after `git add .`, rerun the staging step with escalated permissions before assuming git is inconsistent.
