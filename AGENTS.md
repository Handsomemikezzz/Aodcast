# AGENTS.md

## Purpose

This file is the collaboration contract for agents working on Aodcast. It defines constraints, ownership boundaries, and delivery process. Product status, setup, and operator notes belong in `README.md` / `README.zh-CN.md`. Code is the architecture source of truth.

Update this file when ownership boundaries, shared contracts, core product flow, or agent workflow change. If implementation invalidates these rules, update `AGENTS.md` in the same change set.

## Engineering Principles

- 不以维护向后兼容性为目标。对于已经废弃的代码路径，应直接移除，不再通过兼容层、回退机制或迁移方案予以保留。
- 在充分满足当前需求的前提下，采用尽可能简单的实现方案。避免引入缺乏实际需求依据的抽象、配置项和间接层。
- 采用渐进式、分层的方式构建系统。首先完成能够端到端运行的最小版本，再基于稳定可用的产品逐步增加功能。不要以尚未成熟的复杂性取代已经可用的产品。
- 保持组件的模块化，并明确划分不同职责与关注点。
- 当成熟且维护良好的库能够降低整体复杂度或提高可靠性时，应优先采用。除非有明确理由，不要重复实现通用功能。在自行实现功能或新增依赖之前，应优先评估项目现有依赖的能力。应先查阅相关文档和类型定义，不应未经确认就认定某个库不具备所需能力。
- 架构决策应着眼于长期演进。不要采用仅能解决当前问题、且预期需要在后续替换的权宜方案。在设计解决方案之前，先研究成熟产品如何解决同类问题。优先采用经过验证的模式和约定，避免从零开始另行设计一套方案。

## Ownership Rules

- UI work stays in `apps/desktop` unless a schema change is required.
- Backend work stays in `services/python-core` unless a schema change is required.
- Cross-boundary changes update shared contracts first in `packages/shared-schemas`.
- Provider-specific logic belongs only under `services/python-core/app/providers`.
- Model-specific capability negotiation, Speech Plan translation, clone modes, pause syntax, and generation arguments belong in provider adapters/runners under `services/python-core/app/providers`, not orchestration or desktop. Adapters must declare unsupported or approximated capabilities instead of silently dropping requested behavior.
- Interview state logic belongs only under `services/python-core/app/orchestration`. Content-dimension readiness alone must not hard-stop the interview or push a deterministic "generate script now" message. Soft-offer requires `can_offer_script` (dimensions + `MIN_USER_TURNS_FOR_SCRIPT_OFFER` in `readiness.py`). While the user keeps talking, stay in `interview_in_progress` with `soft_ready`; move to `ready_to_generate` only on explicit finish (`user_requested_finish` / `request_finish`).
- Imported episode sources belong in `services/python-core/app/domain/episode_source.py` and `storage/project_store.py`, with their cross-boundary contract in `packages/shared-schemas/episode-source.schema.json`. Keep imported Markdown as a versioned source snapshot; never coerce it into transcript turns or long-term memories. Source-backed script generation may use later user conversation as supplemental direction, but the imported source remains the factual and editorial source of truth.
- Long-term memory belongs only under `services/python-core/app`: `domain/memory.py`, `storage/memory_file_store.py`, `orchestration/memory_*.py`, `orchestration/sensitive.py`, `workers/memory_worker.py`. Keep file-native storage under `.local-data/memory/`; do not reintroduce SQLite, FTS5, vector stores, or embeddings. `entries/*.md` is the only source of truth; `catalog.json` and `MEMORY.md` are rebuildable indexes. Only user turns may become memories. Main interview/script flow uses read-only retrieval and must never block on memory work.
- Desktop bridge calls flow through `apps/desktop/src/lib/*Bridge.ts -> localhost HTTP runtime -> services/python-core`, never from React components to shell commands.
- The desktop shell may own runtime lifecycle helpers, but must not own podcast business logic or per-operation payload translation.
- Bridge success and failure payloads must include normalized `request_state` (`operation`, `phase`, `progress_percent`, `message`).
- Long-running HTTP bridge operations must persist pollable task state, expose `show_task_state` with incremental `progress_percent`, and support `cancel_task` with `running -> cancelling -> cancelled`. Retriggerable long tasks must use a `run_token` so the UI can ignore stale polls.
- Podcast Editor behavior belongs in script-generation prompts and keeps the saved script as clean spoken text: improve listening structure, sentence length, punctuation, and paragraph rhythm without filler, stage directions, or provider markup.
- Provider-neutral `SpeechPlan` and `RenderManifest` logic belongs under `services/python-core/app/domain`, `orchestration`, and `storage`, with cross-boundary contracts in `packages/shared-schemas`. A Speech Plan is versioned and bound to one exact script hash; structured breaks, emphasis, pronunciation, and delivery must never be persisted as provider-specific inline syntax.
- `SpeakerReference` is the provider-neutral identity source for “who is speaking”; it must not contain model, style, speed, or delivery settings. Voice Studio owns built-in and user-saved Speaker References, upload/recording, preview, and script selection. User reference audio is limited to 10 minutes and each revision is an immutable content-hashed blob. Deletion must refuse references still used by a script selection or Render Manifest. Voice is a first-class sidebar destination (`/voice-studio`), peer to Models and Memory; Studio may deep-link into it for a specific script but must not be the only entry.
- Speech Plan and Render Manifest snapshots are immutable and addressable by id. Render publication must re-read and compare the script hash, selected Speaker Reference, and active render id, then update only render-owned fields; stale jobs must never overwrite a newer script or render. Reused reference and segment files must match their persisted hashes before synthesis or assembly.
- Script Workbench owns local/cloud model selection for a full render, read-only Speech Plan inspection, segment playback, context-window regeneration, and generated-audio management. A local regeneration rerenders the target segment plus its immediate neighbors sequentially, conditions each new segment on preceding audio/text, and must keep the previous render current until the replacement window and assembly both succeed.
- Segment WAVs are immutable render assets. `RenderManifest` records script/plan/reference/pipeline hashes, segment lineage, regeneration windows, assembly settings, and final output. The final podcast WAV must be produced by manifest-driven assembly with explicit pauses, format normalization, boundary fades, RMS matching, and sample-peak limiting; MP3 remains an on-demand sibling export, not a publish flow. Do not label RMS, sample-peak, or edge-fade processing as LUFS, true-peak, or crossfade without implementing those algorithms.
- Full render and local regeneration for a script share the scoped task id `render_audio:<session_id>:<script_id>`. Cancellation must include the current `run_token`; a task from one script must never block, cancel, or overwrite another script's render state.
- Tauri-only helpers (for example `reveal_in_finder`) live under `apps/desktop/src/lib/shellOps.ts` and must not be added to `DesktopBridge` (HTTP bridge parity requires every interface method to have an HTTP contract).
- Do not claim secure vaulting for API keys unless Keychain or equivalent support exists.

## Change Protocol

1. Read relevant code, tests, and configuration first.
2. Identify the owned directory boundary.
3. Update shared schema or `AGENTS.md` first when the change crosses boundaries.
4. Implement the smallest complete change set.
5. Update `AGENTS.md` and/or README when agent constraints or human-facing behavior/workflow change.

## Code Generation Rules

- Prefer small, single-purpose files.
- Do not duplicate provider logic across orchestration or UI layers.
- Avoid framework glue where a simple interface will do.
- Keep internal domain models separate from external provider payloads.
- Favor explicit interfaces and replaceable adapters over vendor-coupled logic.

## Documentation Rules

- Code is the primary architecture reference.
- Human setup and product/status notes belong in `README.md` and `README.zh-CN.md`.
- Agent constraints belong in `AGENTS.md`.
- Do not add tracked documentation under `docs/`; that directory is gitignored local scratch.
- Keep public release docs (`LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, README pair) aligned when install, provider, or release behavior changes.

## Delivery Workflow

Roles:

- `schema-steward`: `packages/shared-schemas`
- `orchestration-builder`: `services/python-core/app/orchestration`, `domain`, `storage`
- `provider-integrator`: `services/python-core/app/providers`
- `desktop-builder`: `apps/desktop`
- `quality-runner`: `services/python-core/tests` and frontend tests when present

Default sequence: schema -> orchestration -> providers -> desktop -> tests -> maintenance pass.

When using multiple agents: one bounded area per agent; merge contract changes before dependents; lead agent still follows these boundaries if teammate spawning is unavailable.

## Maintenance Subagents

Run after structural or contract changes, and periodically to control entropy:

- `spec-keeper`: keep `AGENTS.md` and README aligned with code
- `code-pruner`: identify dead code and duplicate paths
- `contract-guard`: check schema and bridge contract drift
- `doc-syncer`: refresh README and human setup docs
- `repo-curator`: police temporary files and directory sprawl

Default local sweep: `./scripts/maintenance/run-repo-hygiene-check.sh`.
