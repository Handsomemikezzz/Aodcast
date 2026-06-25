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

Current source of truth: code, tests, configuration, and launch scripts.

Current MVP:

- platform: macOS desktop app
- frontend: Tauri app shell
- backend: local Python orchestration core
- input: text topic only
- output: solo podcast script plus final audio rendered from Script Workbench
- LLM: user-configured API provider
- TTS: local MLX-backed provider as the primary first-release path, plus remote API provider support
- memory: file-native, local-only long-term user memory across episodes (Memory v1)

Out of scope for the current MVP:

- speech-to-text input
- multi-host podcast formats
- cloud backend dependency
- voice cloning

## Repository Map

- `apps/desktop`: Tauri UI and app shell
- `services/python-core`: interview orchestration, script generation, provider dispatch, storage
- `packages/shared-schemas`: shared data contracts and schemas
- `docs/`: gitignored local scratch for personal notes such as `tmp.md` or `plan.md`; not a documentation source of truth
- `.agent`: prompts, checklists, templates, and reports used by agents

## Setup And Configuration

Human-facing setup lives in `README.md` and `README.zh-CN.md`. Agent-relevant constraints:

- local data defaults to `.local-data/` during development; it is gitignored and holds provider config, sessions, artifacts, and request-state files
- API keys are local user-managed configuration; macOS Keychain and dedicated secrets vault support do not exist yet
- normal development does not require `.env`; optional helper variables include `AODCAST_HF_MODEL_BASE`, `HF_HUB_CACHE`, and `HF_TOKEN`
- development smoke providers are `mock` for LLM and `mock_remote` for TTS; use `--check-llm-config` before interview/script flows
- local MLX is runtime-gated; always run `--show-local-tts-capability` before selecting `local_mlx`
- default MLX model target is `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit`
- local model directories must contain real MLX exports with `.safetensors` weights; placeholder directories are not executable bundles
- Models page owns app-managed model storage, migration, reset, and downloads; app-managed Hugging Face downloads disable Xet (`HF_HUB_DISABLE_XET=1`)

## Ownership Rules

- UI-focused agents should work inside `apps/desktop` unless a schema change is required.
- backend-focused agents should work inside `services/python-core` unless a schema change is required.
- cross-boundary changes must update shared contracts first in `packages/shared-schemas`.
- provider-specific logic belongs only under `services/python-core/app/providers`.
- interview state logic belongs only under `services/python-core/app/orchestration`.
- long-term memory logic belongs only under `services/python-core/app`: domain model in `domain/memory.py`, file-native persistence in `storage/memory_file_store.py`, extraction/retrieval/validation/service in `orchestration/memory_*.py` and `orchestration/sensitive.py`, and the background worker in `workers/memory_worker.py`. Memory must stay file-native (`.local-data/memory/`); do not reintroduce SQLite, FTS5, vector stores, or embeddings. `entries/*.md` is the only source of truth; `catalog.json` and `MEMORY.md` are rebuildable indexes. Long-term memory is evidence-first: only user turns may become memories, and the main interview/script flow uses read-only retrieval that must never block on memory work.
- operational rules belong in `AGENTS.md`, not in scattered ad hoc notes.
- desktop bridge calls must flow through `apps/desktop/src/lib/*Bridge.ts -> localhost HTTP runtime -> services/python-core`, not from React components directly to shell commands.
- the desktop shell may own lifecycle helpers for starting, attaching, health-checking, and shutting down the localhost runtime, but it must not own podcast business logic or per-operation payload translation.
- bridge success payloads and bridge failures must include a normalized `request_state` contract (`operation`, `phase`, `progress_percent`, `message`) so frontend pages can render consistent loading/error/task-state UX.
- long-running HTTP bridge operations must persist pollable task states and surface incremental `progress_percent` through `show_task_state` before adding new UI long-task flows.
- long-running HTTP bridge operations that expose `show_task_state` must also support `cancel_task` with cooperative phase transitions (`running -> cancelling -> cancelled`) for desktop-triggered cancellation.
- Script Workbench owns final podcast rendering and generated-audio management. Voice Studio owns reusable voice profiles, preview, and script voice selection; legacy take endpoints remain compatibility surfaces only.
- model-specific runtime logic belongs inside provider runner/runtime modules, not in orchestration or desktop files.

## Change Protocol

Before substantial implementation work:

1. read the relevant code, tests, and configuration first
2. identify the owned directory boundary
3. update shared schema or `AGENTS.md` first if the change crosses boundaries
4. implement the smallest complete change set
5. update `AGENTS.md`, README, or human setup docs when behavior or workflow changes

When a change affects the product flow, architecture, or repo governance, update [AGENTS.md](AGENTS.md).

## Code Generation Rules

- Prefer small, single-purpose files.
- Do not duplicate provider logic across orchestration or UI layers.
- Avoid adding framework glue where a simple interface will do.
- Keep internal domain models separate from external provider payloads.
- Favor explicit interfaces and replaceable adapters over vendor-coupled logic.

## Documentation Rules

- Code is the primary architecture reference.
- Human setup belongs in `README.md` and `README.zh-CN.md`; agent rules belong in `AGENTS.md`.
- Do not add tracked documentation under `docs/`; that directory is gitignored local scratch.
- If code changes behavior, state shape, directory ownership, or operator workflow, update `AGENTS.md` or README in the same task.
- Add new operational conventions to `AGENTS.md`.

## Maintenance Subagents

Run maintenance-oriented subagents after structural or contract changes, and periodically to control repository entropy.

Maintenance roles:

- `spec-keeper`: keep `AGENTS.md` and README aligned with code
- `code-pruner`: identify dead code and duplicate paths
- `contract-guard`: check schema and bridge contract drift
- `doc-syncer`: refresh README and human setup docs
- `repo-curator`: police temporary files and directory sprawl

Event triggers: new provider, directory moves, shared schema changes, session state machine changes, or `AGENTS.md` changes.

Default local sweep before a maintenance report: `./scripts/maintenance/run-repo-hygiene-check.sh`.

## Delivery Workflow

Feature delivery should follow the active code contracts plus `AGENTS.md`.

Delivery roles:

- `schema-steward`: `packages/shared-schemas`
- `orchestration-builder`: `services/python-core/app/orchestration`, `domain`, `storage`
- `provider-integrator`: `services/python-core/app/providers`
- `desktop-builder`: `apps/desktop`
- `quality-runner`: `services/python-core/tests` and frontend tests when present

Default sequence: schema -> orchestration -> providers -> desktop -> tests -> maintenance pass.

When using multiple agents:

- assign one bounded area per agent
- treat schema and governance updates as first-class tasks
- merge contract changes before dependent implementation work
- run maintenance agents after structural or cross-boundary changes
- if teammate spawning is unavailable in the current runtime, the lead agent must still follow the same task boundaries and report status in the active conversation or task artifact

## Known Execution Notes

- 2026-03-29: Rust tooling is now available in this environment (`cargo 1.94.1` on `PATH`). Native compile checks can run locally (`cargo check` under `apps/desktop/src-tauri`) and should be used in integration validation.
- 2026-03-29: Avoid calling `pnpm --dir apps/desktop tauri:build -- ...` with extra `--` cargo-style flags (`--debug`, `--no-bundle`). They are forwarded to `cargo build` and fail as unexpected args. Use plain `pnpm --dir apps/desktop tauri:build` for shell validation.
- 2026-04-02: DMG packaging can fail in non-interactive environments when Finder AppleScript times out (`-1712`) inside `bundle_dmg.sh`. The desktop build script now runs `CI=true tauri build`, which makes bundler pass `--skip-jenkins` and avoids Finder-dependent styling during DMG creation.
- 2026-04-02: Local MLX long-text synthesis can appear truncated unless audio chunks are joined. The runner now passes `--join_audio` (plus a larger token budget) to `mlx_audio.tts.generate`; use the project runner (`./scripts/dev/run-python-core.sh`) when validating this behavior.
- 2026-04-02: Request-state compare-and-write guards are now protected by per-task cross-process file locks in addition to in-process locks. Keep stateful long-task operations (`render_audio`, `cancel_task`, `show_task_state`) sequenced unless explicitly testing concurrency behavior.
- 2026-04-20: Local MLX TTS now runs inside a persistent worker subprocess (`app.providers.tts_local_mlx.mlx_worker`) managed by `WorkerClient`. The model is loaded once per worker lifetime; do not replace the worker architecture with one-off CLI invocations, and do not call `mlx_audio.tts.generate` directly from orchestration. Chunk-level progress is delivered via `ChunkProgressEvent` -> `AudioRenderProgress` -> `LongTaskStateManager.set_progress`, so `start_heartbeat` is intentionally absent for `render_audio`.
- 2026-05-16: When local MLX/Qwen voice cloning sounds muddy, wrong, or slowed down, verify audio metadata before blaming the model. A prior failure made `script-app-runner.wav` sound like a bad cloned voice because worker chunk joining decoded segment WAV files with `miniaudio.decode` defaults (`2ch`/`44100Hz`) and then wrote them at the model rate (`24000Hz`), stretching a ~2:58 render to ~5:33. Compare a direct chunk-joined control against the app runner and check `ffprobe`/`afinfo` for duration, channels, and sample rate; worker PCM reads must force `nchannels=1` and `sample_rate=self._sample_rate`.
- 2026-04-20: The audio render HTTP envelope includes a `run_token` (UUID) that is also written into each persisted request state. The desktop UI filters polled updates by this token; when adding new long-running operations that may be retriggered by the user, follow the same pattern to avoid stale-state UI regressions.
- 2026-04-20: Reveal-in-Finder is exposed as a Tauri-only command (`reveal_in_finder`) and must NOT be added to the `DesktopBridge` interface, since the HTTP bridge parity tests require every interface method to have a matching HTTP contract. Tauri-only desktop helpers live under `apps/desktop/src/lib/shellOps.ts`.
- 2026-03-28: Do not run a newly created script in parallel with its `chmod +x` step. Apply permissions first, then execute the script sequentially, otherwise permission races can produce false negatives.
- 2026-03-28: Frontend dependency installation may fail inside the sandbox with npm registry `EPERM` network errors. If `pnpm install` is required for validation, rerun it with escalated permissions instead of assuming the lockfile or package manager is broken.
- 2026-03-28: Do not run state-dependent CLI writes and immediate readbacks in parallel. Operations like `start-interview`, `reply-session`, `generate-script`, `render-audio`, `configure-tts-provider`, and the follow-up `show-*` inspection commands must be sequenced, or later steps may observe stale state and fail for the wrong reason.
- 2026-03-28: The local MLX TTS path is runtime-gated. Before trying `local_mlx`, check `--show-local-tts-capability`. The project now uses `services/python-core/.venv` for local MLX validation, and `./scripts/dev/run-python-core.sh` prefers that interpreter automatically. Do not assume bare system `python3` has the same MLX availability as the project venv.
- 2026-04-01: Some environments can crash during `import mlx.core` with a native `NSRangeException` before Python handlers run. Treat `--show-local-tts-capability` as the source of truth: it now performs a subprocess bootstrap probe and may report `available: false` even when `mlx`, `mlx_audio`, and model path checks pass.
- 2026-03-28: Git writes may be sandbox-restricted even when normal file edits succeed. If `git commit` fails with `.git/index.lock: Operation not permitted`, rerun the commit with escalated permissions instead of treating it as a repository corruption issue.
- 2026-03-28: Transcript exports intentionally normalize to a trailing newline. When validating `transcript.txt`, compare normalized content or include the newline in expectations; this is storage behavior, not an audio-rendering regression.
- 2026-03-28: `git add .` may appear to succeed in the sandbox without actually staging changes. If `git status --short` still shows unstaged files after `git add .`, rerun the staging step with escalated permissions before assuming git is inconsistent.
- 2026-04-25: `scripts/dev/run-dev-all.sh` now defaults to restarting the Python runtime on port `8765` to avoid stale in-memory code paths during local debugging. Use `--reuse-runtime` only when you intentionally need process continuity across runs.
- 2026-04-25: For audio render debugging, check runtime metadata from `/healthz` first (pid/start/build token), then inspect `.local-data/runtime/request-state/*` and only then diagnose frontend `run_token` filtering behavior.
- 2026-04-26: Voice Studio preview text is user-editable and flows through `VoiceRenderSettings.preview_text`; empty preview text intentionally falls back to the packaged standard sentence. Audio-only `.mp4` may be served as `audio/mp4`, but the app does not currently transcode WAV to AAC/MP4 or create video MP4 output without a separate ffmpeg/afconvert packaging decision.
- 2026-04-26: Artifact audio playback URLs intentionally use the localhost HTTP route (`/api/v1/artifacts/audio`) in both Web and Tauri shells. Do not reintroduce `convertFileSrc` for generated audio unless Tauri asset protocol scope/capabilities are explicitly configured and parity-tested.
- 2026-04-26: Voice Studio preview rendering is a pollable long task (`render_voice_preview`), not a synchronous POST. Keep preview UI progress wired to task state; local MLX cold starts can otherwise look stuck.
- 2026-04-25: Voice Studio MVP routes are HTTP-bridge first (`listVoicePresets`, `renderVoicePreview`, `renderVoiceTake`, `setFinalVoiceTake`). Preserve bridge parity when changing them, and keep Voice Studio take retention to final take + latest candidate unless product requirements explicitly move to full version management.
- 2026-04-26: App-managed Hugging Face model downloads disable `hf_xet` (`HF_HUB_DISABLE_XET=1`) because Xet can stall behind local proxy/VPN setups while the Models page heartbeat appears capped. Keep download progress bounded below finalization unless real script progress is observed, and surface stalled downloads as retryable task failures instead of leaving them running indefinitely.
- 2026-04-26: Models page now owns local model storage management (`showModelStorage`, `migrateModelStorage`, `resetModelStorage`) while Finder opening and directory picking remain Tauri-only shell helpers in `shellOps.ts`/Rust commands. Keep migration on the existing `request_state` polling contract; do not introduce SSE model-download progress without an explicit architecture decision.
- 2026-04-29: Voice Studio is the canonical default voice source for script audio. Script Workbench `renderAudio` calls must pass/use the script artifact's `voice_settings`, falling back only to Voice Studio defaults; do not reintroduce raw Settings `tts_config.voice` as the default render voice. Voice Studio preview saves session/script voice settings when context is provided, and completed Voice Studio takes auto-promote to final audio for playback parity. Multi-script sessions persist per-script playback/takes under `artifact.script_artifacts`; load/render/delete through the script-scoped project view so one snapshot cannot overwrite another. Audio deletion must remain UI/API-first: preview deletion removes standalone preview files, take deletion removes take files and clears final playback when needed, and generated-audio deletion clears the selected script's artifact playback fields without requiring users to inspect `artifact.json`.
- 2026-04-29: Voice Studio preview tasks use unique `render_voice_preview:{run_token}` task ids and persisted `run_token` request states. Keep this isolation when changing preview polling, otherwise stale preview audio/settings can satisfy a newer preview request. Local MLX renders map Voice Studio presets to Qwen speaker names and forward style instructions, speed, and language into the worker; unsupported model variants may ignore some controls, so UI/docs must not imply every model applies every expressive parameter.
- 2026-04-30: Voice Studio preview locking is explicit, not automatic. `lockVoicePreview` stores the accepted preview as script-scoped `artifact.voice_reference`; local MLX/Qwen full renders and Voice Studio take renders must pass that locked preview path as `ref_audio` when present. Deleting a preview file must clear any matching `voice_reference`, while generated-audio deletion must preserve the lock. Keep UX copy honest: locks improve continuity but do not guarantee bit-identical Qwen output.
- 2026-04-30: Voice profiles are reusable Voice Studio assets. Built-in profile audio is packaged under `services/python-core/app/assets/voice-profiles/` and must remain git-tracked app content; user profile audio is copied into `.local-data/exports/_voice_profiles`. Selected profiles write script-scoped `artifact.voice_reference` with `source: voice_profile` plus `voice_profile_id`. Do not treat profile audio as a transient preview; deleting a profile must clear matching script references, but deleting a preview should not remove saved profiles.
- 2026-05-16: Voice Studio user profile creation is dialog-based and must not ask users to type local audio paths. The UI uses upload or microphone recording, then the HTTP bridge runs `POST /api/v1/voice-profiles` followed by multipart `POST /api/v1/voice-profiles/{profile_id}/sample`; v1 stores one sample per profile in the existing `audio_path`/`reference_text` fields. System audio capture remains unavailable until an explicit macOS/Tauri capture command is added.

## Open-source Release Docs

Public GitHub releases must keep `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `README.md`, and `README.zh-CN.md` in sync with install, provider, and release behavior. API keys are user-managed local configuration; do not claim secure vaulting unless Keychain or equivalent support is implemented.
