# Changelog

All notable changes to Aodcast will be documented in this file.

## [0.1.0-alpha] - Unreleased

### Added

- Local-first macOS desktop workflow for AI-guided solo podcast creation.
- Interview-driven session flow, Podcast Editor rhythm guidance, script generation, script snapshots, and script editing.
- Versioned, provider-neutral Speech Plans with stable segments, structured breaks, emphasis, pronunciation, delivery metadata, and exact script-hash binding.
- Voice Studio for provider-neutral Speaker References, sample upload/recording up to 10 minutes, preview rendering, and reference management.
- Script-first Episode Workspace with contextual Sources/Conversation drawers, in-place Voice and Delivery controls, short passage preview, a persistent audio dock, and non-destructive audio freshness states.
- Immutable segment WAV assets and Render Manifests that record script, plan, reference, model pipeline, regeneration, assembly, and final-output lineage.
- Bundled `speech-service` with an isolated Python 3.12 environment and a lightweight `httpx` orchestration client for its HTTP API at `127.0.0.1:8090`, including WAV synthesis, multipart file transcription, health checks, cancellation, and actionable connection errors.
- Localhost HTTP runtime bridge between the Tauri/web UI and Python orchestration core.
- Mock LLM provider path for smoke tests and development fallback.
- ChatGPT subscription LLM provider through the official Codex app-server, including browser sign-in, dynamic account model discovery, streaming interview output, structured JSON generation, and Codex usage-window status.
- Chat composer attachments (images and TXT/Markdown/CSV/JSON/PDF documents) with paste, drag-and-drop, file picker, previews, and transcript display; images reach OpenAI-compatible and Codex models as image input, and document text is extracted by the Python runtime.
- Shared request-state contracts for long-running operations, script-scoped audio task ids, run-token-safe cancellation, and stale-poll rejection.

### Changed

- Consolidated the checkout into `AudioS/Aodcast/` and bundled local speech under `speech-service/`; launchers resolve paths relative to the repository.
- Desktop/web launchers now start speech, wait for `8090/health`, then start the orchestration runtime and UI. Health readiness does not warm up models.
- Renamed the current-user LaunchAgent to `com.aodcast.speech-service` and moved its logs to `~/Library/Logs/Aodcast/speech-service/`. Speech remains available after closing the UI and can be stopped explicitly with `./speech-service/service.sh stop`.

- Desktop creation now flows from Episodes into one Episode Workspace instead of a Material/Script/Voice/Audio wizard. Voice Studio remains the asset library while existing voices are selected inside the episode.
- Local speech inference, model loading/downloads, memory-safe slicing, and GPU/cache ownership run in the bundled, process-isolated `speech-service`. Aodcast sends natural paragraphs intact, with a 1,800-second read timeout and 5-second connect timeout.
- Editorial Speech Plans and Render Manifests remain in Aodcast for paragraph reuse, regeneration, and podcast assembly.
- Final `podcast.wav` is assembled from the Render Manifest with explicit pauses, format normalization, one edge fade per segment, audible-sample RMS matching, and a sample-peak ceiling.
- Default TTS provider is `local_http`; cloud TTS remains OpenAI-compatible only.
- Simplified the desktop UI: no global title bar, a single "New episode" entry that opens the idea composer (Markdown import is a secondary link), one Workspace header with script actions in an overflow menu, engine-aware Voice controls, and leaner Voice, Models, Memory, and Settings pages.
- The desktop UI, preset voice names, and user-facing runtime errors are now English. Speech sample text, voice IDs, and model-generated interview content are unchanged.

### Fixed

- Chat no longer waits for suspended text animations, stream cancellation, or a background session refresh before restoring Send after completion or Stop.
- Opening an episode no longer reports "Audio needs update" before any voice change; audio freshness compares saved voice settings by ID, not display name.
- Native runtime readiness probes the built-in voice-preset endpoint instead of a removed model-storage route. Desktop/web launchers separately ensure the speech HTTP service is online before starting the shell.

### Removed

- In-process speech inference adapters/workers, model download and storage migration flows, weight-path settings, and speech-model dependencies from the Python orchestration core. Inference dependencies now live only in `speech-service/`.

- Top-level Studio navigation, the four-step workflow stepper, raw session-state labels, and the primary Speech Plan viewer.
- Legacy voice-profile, preview-lock, and voice-take bridge/API flows. Persistent speaker identity now uses Speaker References, while final audio comes from manifest-driven rendering.
- Mock Testing TTS provider (`mock_remote`).

### Notes

- This release is intended as a GitHub source-code alpha, not a polished packaged desktop app distribution.
- Local audio uses the bundled speech service in a separate process, started automatically by desktop/web launchers. Its preset-voice API supports WAV at normal speed; it does not support reference-audio cloning, style, exact pauses, or continuity conditioning. Voice Studio assets remain manageable but cannot be cloned through this provider.
- ASR is exposed through the Python speech client; microphone input and subtitle-editing UI are not included.
- Model quality and performance claims require real-model measurements; client unit tests alone are insufficient.
- API keys are stored and managed locally by users at their own risk.
- Codex owns ChatGPT OAuth credential storage and refresh; Aodcast does not copy OAuth tokens or silently fall back from subscription usage to API-key billing.
- Codex subscription settings expose one global model-aware reasoning-effort selector; `Auto` uses the model default and explicit options are constrained by the live model catalog.
