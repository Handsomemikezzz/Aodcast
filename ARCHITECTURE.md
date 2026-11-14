# Architecture and Behavior Notes

These notes describe current product behavior for humans and operators. Agent coding constraints live in [AGENTS.md](AGENTS.md); setup and day-to-day commands live in [README.md](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## Current Scope

Aodcast currently focuses on local-first solo podcast creation:

- platform: macOS desktop (Tauri) + local Python orchestration core
- input: a text topic or one local/pasted Markdown source per episode
- output: solo podcast script plus final audio from Episode Workspace
- LLM: mock, OpenAI-compatible, or ChatGPT subscription through Codex
- local speech identity: a preset voice, or a Speaker Reference cloned by a Qwen3 Base model, selected per script
- TTS: bundled local HTTP `speech-service` in an isolated process, or remote API providers
- memory: file-native, local-only long-term user memory across episodes

The Python speech client also supports file transcription. Speech-to-text UI input, multi-host formats, and a required cloud backend remain out of scope.

The app can serve common audio suffixes and validate uploaded Speaker Reference duration through local decoders or `ffprobe`. Export to compressed audio formats depends on local conversion tools. True video MP4 output is out of scope.

## Feature Overview

- Interview-guided writing for a text topic; chat sending becomes available as soon as a reply completes or Stop is pressed, and animation or background session refresh never blocks the next message.
- Chat attachments: paste, drop, or pick images (PNG/JPEG/WebP/GIF) and documents (TXT/Markdown/CSV/JSON/PDF, up to 10 MB each, 8 per message). Images go to the model as image input; document text is extracted locally and sent as text.
- Markdown-first creation from a local `.md` file or pasted text, with source preview, podcast adaptation or faithful narration, target-length guidance, optional source discussion, and versioned source replacement.
- Multiple independent script snapshots per episode, whether it started from an interview or Markdown.
- A script-first Episode Workspace for editing, contextual Voice and Delivery selection, short passage previews, full rendering, non-destructive audio updates, playback, and export.
- Voice Studio for built-in and user-created Speaker References, sample upload/recording up to 10 minutes, asset previews, and reference management.
- Local voice cloning with `Qwen3-TTS-12Hz-0.6B-Base-8bit` (default) or `1.7B-Base-8bit`, with short passage previews kept per model for A/B comparison before a full render.
- A bundled native `speech-service` for local TTS/ASR (accessed through the lightweight `local_http` client), plus OpenAI-compatible remote TTS providers.
- Models page for local speech-service status, the active preset model reported by that service, and readiness of both cloning models.
- A mock LLM provider for interview and script smoke testing without paid access; audio rendering still needs a running local speech service or a configured remote TTS provider.
- ChatGPT subscription LLM access through the official local Codex app-server, with browser sign-in, account model discovery, and Codex usage-window reporting.
- Local-first storage under `.local-data/`.

## Interview and script offer

Offering script generation requires both content-dimension readiness and a minimum number of user answers (`MIN_USER_TURNS_FOR_SCRIPT_OFFER`, default 4). Each interview turn asks one follow-up and offers two grounded answer candidates (A/B) plus a free-answer option (C); the interview keeps going and presents script generation only as a secondary option until the user explicitly finishes or chooses to generate.

## Memory

Long-term memory is file-native under `.local-data/memory/`. `entries/*.md` is the source of truth; `catalog.json` and `MEMORY.md` are rebuildable indexes. Only user turns become memories. Interview/script flows use read-only retrieval and do not block on background memory work.

## Podcast Editor and Speech Director

The Podcast Editor keeps generated scripts as plain spoken text while improving listening structure, sentence length, punctuation, and paragraph breathing, without manufacturing filler words, provider tags, or stage directions. At the start of a full render, the internal Speech Director creates a versioned, provider-neutral Speech Plan (stable segments, structured pauses, emphasis, pronunciation, delivery guidance) bound to the exact script hash; these concepts are not exposed in the main UI. Editing the script makes the prior plan and render stale; generate the full audio again before local regeneration.

## Desktop bridge and long tasks

UI calls go through the desktop HTTP bridge to the local Python runtime. Long operations (audio render, voice preview, and similar) persist pollable `request_state`, expose progress, support cancel, and use `run_token` so retriggered runs do not show stale UI state. Full render and context-window regeneration share the script-scoped task id `render_audio:<session_id>:<script_id>`; cancellation must carry that run's token, so different scripts do not collide. Stateful long-task operations should otherwise be sequenced unless concurrency is under test.

## Episode Workspace and Voice Studio

- Episode Workspace keeps the script as the primary canvas, with Sources and Conversation in contextual drawers, Voice and Delivery in a lightweight inspector, and Preview/full audio controls in a persistent bottom dock.
- A full render saves immutable segment WAVs and a Render Manifest, then assembles the manifest's final WAV. MP3 is an on-demand sibling export next to that final render.
- Preview uses selected text, the current paragraph, or the script opening and creates disposable audio without replacing the current episode render.
- Existing audio remains playable after script, source, voice, or delivery changes and is labeled `Audio needs update` until a replacement render succeeds.
- Voice Studio owns reusable Speaker Reference assets. With the local engine, the inspector's Voice section starts with **Model**, grouped into *Built-in voices* (CustomVoice) and *Clone a voice* (`Qwen3 TTS 0.6B Base`, the default when a reference is selected, and `1.7B Base`). The voice control below follows the model's declared cloning capability: preset models offer only built-in voices, cloning models offer your saved voices and built-in samples plus a link to clone a new one. The same reference serves both cloning models without duplicating assets. Previews of the same passage are kept per model, and the audio dock switches between them; changing the model marks existing audio `Audio needs update`. Explicitly rendering with a local preset detaches an earlier cloning selection without deleting its source audio or older Render Manifests.
- Cloning a new voice in Voice Studio: tips on recording conditions, a ~10 second read-aloud passage that fills the transcript exactly, a recording timer that stops at the local cloning limit, a length check for uploaded or recorded samples, and a required confirmation that the speaker consented. Created from an episode, the voice is applied to that script and the app returns to the episode, ready to preview.
- Built-in reference audio lives under `services/python-core/app/assets/speaker-references/` (tracked for now). User metadata lives in `.local-data/speaker-references/`; uploaded or recorded audio is normalized to immutable 48 kHz mono 16-bit PCM WAV under `.local-data/exports/_speaker_references/`. Creation requires the matching reference text; system audio capture is not available yet.
- The local speech service loads the preset model from its `.env` and the clone model named by each request, keeping one model resident at a time. Aodcast records the selected provider, model, and Speaker Reference hash in each manifest, so context-window regeneration reuses the model and reference of the render it replaces. Speech Plan and context-window regeneration contracts remain internal rather than appearing in the primary UI.
- Artifact audio playback uses the localhost HTTP route `/api/v1/artifacts/audio` in both Web and Tauri shells.
- Tauri-only helpers such as Reveal in Finder live in shell helpers and are not part of the HTTP `DesktopBridge` surface.

## Local speech boundary

Aodcast's orchestration core contains no speech-model worker or in-process inference. `LocalSpeechClient` preserves the synchronous TTS provider contract while performing cancellable HTTP requests. The bundled `speech-service` process controls model loading, GPU concurrency, inference slicing, and ASR decoding. Preset voice selection remains stable across requests. Clone requests upload the selected Speaker Reference WAV and transcript with every segment; preceding generated audio is never sent as a continuity condition.

Aodcast sends complete natural paragraphs, including paragraphs longer than 1,000 characters. The service owns memory-safe text slicing, serial GPU inference, silence trimming, crossfades, cache cleanup, and idle model unloading. Aodcast retains Speech Plans, immutable paragraph audio, and Render Manifests for editorial assembly and local regeneration; these are publishing assets, not GPU-memory slices.

Manifest-driven assembly in Aodcast normalizes paragraph WAVs, applies one edge fade per segment, matches audible-sample RMS level, inserts editorial pauses, enforces a sample-peak ceiling, and writes `podcast.wav`. This publication stage remains separate from the service's inference-slice crossfades.

## Capabilities and limits

- The current local service supports preset voices, zero-shot voice cloning with two Qwen3 TTS Base models, WAV output, normal speed (`1.0`), and transcription.
- Cloning uses in-context learning: the Speaker Reference audio and its exact transcript condition every inference slice. The service trims edge silence and accepts 3–30 seconds of reference speech by default (`CLONE_MIN/MAX_REFERENCE_SECONDS`); longer clips are rejected with an explicit message rather than truncated, because a truncated clip no longer matches its transcript. A clean 5–15 second clip of one speaker with a word-for-word transcript (punctuation included) gives the most stable result.
- Voice Studio keeps uploads/recordings up to 10 minutes as assets, but only references inside the cloning window can be cloned locally; the UI flags longer or shorter samples.
- Fine-tuning, voice conversion, other model families, style instructions, precise Speech Plan breaks, and preceding-audio conditioning are unsupported and produce explicit capability feedback. Each segment is cloned from the same reference rather than from previously generated audio. Use natural punctuation for rhythm; punctuation is not a precise pause contract.
- Model loading/downloading may make the first request slower. Idle unloading releases model weights and caches; the service process still uses memory.
- A full podcast render still saves an editorial Speech Plan, renders paragraph WAVs, and publishes the assembled `podcast.wav`. MP3 export remains an optional FFmpeg conversion.
- `.mp4` is accepted only as a Speaker Reference audio-container input and normalized to WAV; Aodcast does not generate video MP4.

## Data and privacy details

Aodcast is local-first. Generated sessions, imported source snapshots, scripts, Speech Plans, Render Manifests, Speaker References, transcripts, audio artifacts, provider configuration, and request-state files are stored under `.local-data/`, which is ignored by Git and must not be committed.

- **Imported Markdown** is snapshotted under `.local-data/sessions/<session-id>/source.json`. Script generation sends the normalized article, generation preferences, and any supplemental source discussion to the configured LLM provider; when that provider is remote, this content leaves the device and is handled under the provider's terms. Imported source text is not converted into transcript turns and is never written into long-term memory; only later user-authored conversation turns may be eligible for memory when memory is enabled.
- **Chat attachments** are stored as immutable content-hashed files under `.local-data/sessions/<session-id>/attachments/`. Each interview turn re-sends the conversation's attachments (the six most recent images and up to 40k characters of document text) to the configured LLM provider. Attachments never become long-term memories. If the selected model cannot accept images, the reply fails with an explicit error instead of silently dropping them.
- **Long-term memory** is local-only, stored as Markdown files under `.local-data/memory/`. It is opt-in (first-run notice), can be turned off per episode or globally, and is fully viewable and deletable. High-sensitivity secrets (passwords, API keys, payment credentials, full ID numbers, precise addresses) are never saved, even on request.
- **ChatGPT subscription via Codex:** Codex owns OAuth storage and token refresh. Aodcast receives only account status, plan labels, model metadata, rate-limit summaries, and the generated model output; OAuth tokens and browser cookies are never copied into Aodcast configuration or bridge payloads.
- **API keys** are local user-managed configuration; there is no macOS Keychain integration or secrets vault. Protect local config files, shell history, logs, screenshots, backups, synced folders, generated transcripts, and generated audio.
- Do not open public issues or pull requests containing API keys, private prompts, imported source text, private generated content, local data paths, transcripts, or audio artifacts.
