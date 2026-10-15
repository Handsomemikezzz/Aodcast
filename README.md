# Aodcast

[![CI](https://github.com/Handsomemikezzz/Aodcast/actions/workflows/ci.yml/badge.svg)](https://github.com/Handsomemikezzz/Aodcast/actions/workflows/ci.yml)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![Desktop](https://img.shields.io/badge/desktop-Tauri-blue)
![Backend](https://img.shields.io/badge/backend-Python%203.13-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

English | [简体中文](README.zh-CN.md)

Aodcast is an open-source, local-first macOS desktop app for turning a text idea or an existing Markdown article into a solo podcast script and final audio.

The app runs as a Tauri desktop shell backed by a local Python HTTP runtime. It guides the user through an interview, generates editable script snapshots, and renders final audio through local or remote speech providers. Local synthesis uses preset voices from the bundled `speech-service` running in a separate process; Speaker Reference audio remains a reusable asset library, not a local cloning feature.

> Status: source-code alpha. Aodcast is usable for local development, but it is not yet a hardened packaged desktop distribution. Provider keys and generated content are stored locally; there is no Keychain or dedicated secret vault integration yet.

## What Works

- Text-topic podcast creation with an interview-guided writing flow.
- Markdown-first creation from a local `.md` file or pasted text, with source preview, podcast adaptation or faithful narration, target-length guidance, optional source discussion, and versioned source replacement.
- Multiple independent script snapshots per episode, regardless of whether it started from an interview or Markdown.
- Script generation uses Podcast Editor behavior to write clean, listenable narration with deliberate sentence length, punctuation, and paragraph rhythm—without manufacturing filler words or stage directions.
- An internal Speech Director that creates a versioned, provider-neutral Speech Plan with stable segments, structured pauses, emphasis, pronunciation, and delivery guidance for the exact script hash without exposing those engineering concepts in the main UI.
- A script-first Episode Workspace for editing, contextual Voice and Delivery selection, short passage previews, full audio rendering, non-destructive audio updates, playback, and export.
- Voice Studio for built-in and user-created Speaker References, sample upload/recording up to 10 minutes, asset previews, and reference management; existing voices are selected directly inside an episode.
- A bundled native `speech-service` for local TTS/ASR, accessed through a lightweight `local_http` client, plus OpenAI-compatible remote TTS providers. Model loading and downloads stay inside the service process and its isolated environment.
- Manifest-driven WAV assembly with explicit pauses, consistent format/loudness, render lineage, and reusable per-segment audio assets.
- Models page for local speech-service status and the active model reported by that service.
- A mock LLM provider for interview and script smoke testing without paid provider access; audio rendering still requires a running local speech service or a configured remote TTS provider.
- ChatGPT subscription LLM access through the official local Codex app-server, with browser sign-in, account model discovery, and Codex usage-window reporting.
- Local-first development storage under `.local-data/`.

## Screenshots

### Episodes

Create and manage podcast episodes from the home screen.

![Episodes](images/episodes.png)

To refresh screenshots later: run `./scripts/dev/run-dev-all.sh`, capture the current UI, save stable filenames under `images/`, and update both `README.md` and `README.zh-CN.md`. Do not include API keys, local paths, private prompts, or user data.

## Requirements

- Apple Silicon macOS for the desktop app and MLX speech service
- Python 3.13+ for orchestration; Python 3.12 for `speech-service` (managed separately by `uv`)
- `uv`
- Node.js
- `pnpm`
- Rust and Cargo
- `curl` and `lsof` for the development launcher
- FFmpeg for the bundled speech service and optional MP3 export (`brew install ffmpeg`)

Check the local toolchain:

```bash
./scripts/dev/check-toolchain.sh
```

## Quick Start

From the repository root:

```bash
cd speech-service
uv sync --frozen
cp .env.example .env

cd ../services/python-core
uv sync --extra test

cd ../../apps/desktop
pnpm install

cd ../..
./scripts/dev/run-dev-all.sh
```

`run-dev-all.sh` starts `speech-service`, waits for `http://127.0.0.1:8090/health`, then starts the Python runtime on `127.0.0.1:8765` and launches Tauri with Vite on `http://localhost:1420`. `./scripts/dev/run-web-with-runtime.sh` follows the same order for the browser shell. The health check does not warm up models; weights load on the first synthesis or transcription request.

### Daily start and stop

After installing dependencies, run this one command from the repository root:

```bash
./scripts/dev/run-dev-all.sh
```

The local folder layout is `AudioS/Aodcast/`, with the service in `Aodcast/speech-service/`. The checkout can live elsewhere; launchers resolve paths relative to the repository.

Direct `pnpm --dir apps/desktop tauri:dev` also runs the speech-service health prerequisite before starting its web shell.

Press `Ctrl+C` in the launcher terminal to stop the development app and the runtime owned by that launcher. An explicitly reused runtime is left running. The shared speech process remains available to other clients; stop it explicitly:

```bash
./speech-service/service.sh stop
```

For manual speech management, use `./speech-service/service.sh start|stop|restart|status|logs` (choose one action). `start` installs/enables the current user's LaunchAgent `com.aodcast.speech-service`, including login startup; `stop` disables it. Logs are under `~/Library/Logs/Aodcast/speech-service/`. Closing Aodcast does not stop speech. Idle unloading releases model weights while leaving HTTP running.

| Component | Address | Ownership / check |
| --- | --- | --- |
| Aodcast UI | Development: `http://localhost:1420` | Tauri + Vite; terminal launcher |
| Aodcast Python runtime | `http://127.0.0.1:8765` | Interviews, scripts, tasks, artifacts; `GET /healthz` |
| Bundled speech service | `http://127.0.0.1:8090` | TTS/ASR models and GPU memory; `GET /health` |

```bash
curl --fail http://127.0.0.1:8765/healthz
curl --fail http://127.0.0.1:8090/health
```

A speech health response with `loaded: false` is normal before the first request or after idle unloading. The Models page shows the service's configured model and readiness; the orchestration UI does not install or switch model weights.

## First Smoke Test

Use the mock LLM provider first to verify interview and script generation without paid API access. From the repository root:

```bash
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --configure-tts-provider local_http
./scripts/dev/run-python-core.sh --create-demo-session
./scripts/dev/run-dev-all.sh
```

In the app, create or open an episode, continue its conversation, create a draft, and preview or render audio from the Episode Workspace.

## Provider Setup

Provider settings are stored locally under `.local-data/` and are not intended for version control.

### Development Mock LLM

Use the mock LLM provider for smoke testing interview and script generation without paid API access:

```bash
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --configure-tts-provider local_http
```

Check whether the saved LLM configuration is ready for interview and script generation:

```bash
./scripts/dev/run-python-core.sh --check-llm-config
```

### ChatGPT Subscription Through Codex

Install the official Codex CLI, then select **ChatGPT subscription (via Codex)** in Settings:

```bash
npm install -g @openai/codex
```

Aodcast starts the official local `codex app-server`, opens the ChatGPT browser sign-in flow, and discovers models available to that account. Interview, summary, script, Speech Plan, and memory calls use ephemeral Codex threads and consume the signed-in account's Codex plan allowance. Aodcast never reads or stores Codex access or refresh tokens and never silently falls back to API-key billing. The sign-in is shared with the official Codex CLI on the same machine.

Settings also exposes one global **Reasoning effort** selector for every Codex-backed LLM task. `Auto` omits the turn override and uses the selected model's reported default. Explicit choices are populated from that model's live `supportedReasoningEfforts`; switching models resets an unsupported saved choice to `Auto`. Higher effort can increase response time and consume the plan allowance faster.

For CLI-only configuration after the account is already signed in with `codex login`:

```bash
./scripts/dev/run-python-core.sh \
  --configure-llm-provider codex_subscription \
  --llm-model "gpt-5.6-sol" \
  --llm-reasoning-effort auto
```

### OpenAI-Compatible Providers

Configure an OpenAI-compatible LLM provider:

```bash
./scripts/dev/run-python-core.sh \
  --configure-llm-provider openai_compatible \
  --llm-base-url "https://api.openai.com/v1" \
  --llm-model "gpt-4o-mini" \
  --llm-api-key "<your-key>"
```

Configure an OpenAI-compatible TTS provider:

```bash
./scripts/dev/run-python-core.sh \
  --configure-tts-provider openai_compatible \
  --tts-base-url "https://api.openai.com/v1" \
  --tts-model "gpt-4o-mini-tts" \
  --tts-api-key "<your-key>" \
  --tts-voice "alloy" \
  --tts-audio-format "wav"
```

### Environment Variables

Aodcast does not require a `.env` file for normal development. `.env.example` documents `VITE_AODCAST_RUNTIME_URL` for pointing a parallel worktree's Vite shell at its own local runtime. `AODCAST_SPEECH_URL` supplies the default speech endpoint when provider settings have no saved base URL; a saved `--tts-base-url` takes priority. Export this variable before starting the app: the Python core reads process environment variables and does not automatically load `.env`. Speech-model settings and optional Hugging Face mirror/token/cache overrides belong in `speech-service/.env`, which that service loads itself. Weights stay in the external Hugging Face cache and are never committed. If Codex is installed outside `PATH`, `/opt/homebrew/bin`, or `/usr/local/bin`, set `AODCAST_CODEX_BIN` to the absolute official Codex executable path.

### Exporting MP3

Final renders stay WAV. After audio exists, use **Export** next to the final render. MP3 conversion requires FFmpeg on the local machine.

- Aodcast writes a 192 kbps MP3 beside the WAV, for example `.local-data/exports/<session-id>/renders/<render-id>/podcast.mp3`.
- Finder opens on the MP3 so you can upload it to Xiaoyuzhou or any other host.
- Aodcast does not store platform credentials, upload audio, generate RSS, or track remote publication state.

### Bundled Local Speech Service

Aodcast's default TTS provider is `local_http`. It uses `httpx` to call the bundled native macOS `speech-service` at `http://127.0.0.1:8090/v1`. Source code ships in this repository; inference stays in a separate process and Python 3.12 `.venv`. The orchestration core uses its own Python 3.13+ environment and does not import inference libraries. See the [service README](speech-service/README.md) for configuration and memory limits.

The desktop/web launchers start speech automatically. To manage it alone from the repository root:

```bash
./speech-service/service.sh start
curl http://127.0.0.1:8090/health
```

Configure Aodcast from its repository root:

```bash
./scripts/dev/run-python-core.sh \
  --configure-tts-provider local_http \
  --tts-base-url http://127.0.0.1:8090/v1 \
  --tts-voice "默认中文音色" \
  --tts-audio-format wav
./scripts/dev/run-python-core.sh --show-local-tts-capability
```

| Request | Contract |
| --- | --- |
| `POST /v1/audio/speech` | JSON with `input`, `voice`, and `response_format: "wav"`; returns PCM WAV bytes. `默认中文音色` selects the service default voice. |
| `POST /v1/audio/transcriptions` | Multipart `file` upload (WAV, MP3, M4A); JSON response with `text`. |
| `GET /health` | Loaded model state and process memory. |

The service's default models are `mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit` (TTS) and `mlx-community/Qwen3-ASR-0.6B-8bit` (ASR). To use `mlx-community/Kokoro-82M-bf16`, change `TTS_MODEL`, `TTS_VOICE=zf_xiaobei`, and `TTS_LANGUAGE=z` in `speech-service/.env`, run `(cd speech-service && uv sync --frozen --extra kokoro)`, then `./speech-service/service.sh restart`. Optional `HF_ENDPOINT=https://hf-mirror.com` also belongs in that service environment. The orchestration core has no model downloader, weight-path setting, or model-directory migration; the bundled service owns model acquisition and cache use.

Aodcast sends complete natural paragraphs, including paragraphs longer than 1,000 characters. The service owns memory-safe text slicing, serial GPU inference, silence trimming, crossfades, cache cleanup, and idle model unloading. Aodcast retains Speech Plans, immutable paragraph audio, and Render Manifests for editorial assembly and local regeneration; these are publishing assets, not GPU-memory slices. The HTTP client uses a 1,800-second read timeout and a 5-second connect timeout. A stopped service produces an actionable error directing you to `./speech-service/service.sh start`.

#### Transcription from Python

Run from `services/python-core` after `uv sync --extra test`:

```python
from app.providers.local_speech.client import LocalSpeechClient

client = LocalSpeechClient()
text = client.transcribe("/absolute/path/to/audio.wav", language="zh")
print(text)
```

ASR is a new Python client capability; it is not a microphone-input or subtitle-editing UI workflow.

#### Capabilities and limits

- The current local service supports preset voices, WAV output, normal speed (`1.0`), and transcription.
- Voice cloning, style instructions, precise Speech Plan breaks, and preceding-audio conditioning are unsupported and must produce explicit capability feedback. Use natural punctuation for rhythm; punctuation is not a precise pause contract.
- Voice Studio continues to manage reference-audio assets, including uploads/recordings up to 10 minutes with matching transcripts. Those assets cannot become cloned voices through `local_http`; choose a supported preset instead.
- Model loading/downloading may make the first request slower. Idle unloading releases model weights and caches; the service process still uses memory.
- A full podcast render still saves an editorial Speech Plan, renders paragraph WAVs, and publishes the assembled `podcast.wav`. MP3 export remains an optional FFmpeg conversion.
- `.mp4` is accepted only as a Speaker Reference audio-container input and normalized to WAV; Aodcast does not generate video MP4.

#### Real-model verification

Run the real TTS→ASR loopback and 1,246-character podcast pipeline from `services/python-core`:

```bash
uv run --extra test python ../../scripts/verification/verify-local-speech.py
```

The script writes WAV files, `results.json`, and per-second `memory.jsonl` into a new `.local-data/speech-verification/<timestamp>/` directory. It uses real speech models and a deterministic mock LLM only for editorial planning. It checks the spoken closing marker to detect truncated long audio.

On 2026-10-15, the 16 GiB Apple M4 run produced a 9.04-second short WAV in 51.00 seconds (first load), recognized it in 9.20 seconds with 0% normalized character error, and rendered the 1,246-character paragraph in 207.94 seconds into 266.31 seconds of audio. The service handled all 11 inference slices. Service RSS peaked at 2.07 GiB and Metal allocation at 6.68 GiB; those counters use different accounting and must not be added. These are measurements of the earlier decoupling acceptance run, not a new migration benchmark or performance guarantees. The [acceptance report](SPEECH_DECOUPLING_REPORT.md) links the original outputs.

## Development Commands

Run the desktop app with the local runtime:

```bash
./scripts/dev/run-dev-all.sh
```

Run the Python runtime directly:

```bash
./scripts/dev/run-python-core.sh --serve-http --host 127.0.0.1 --port 8765
```

Run frontend checks:

```bash
pnpm --dir apps/desktop check
pnpm --dir apps/desktop test
pnpm --dir apps/desktop build:web
```

Run Rust checks for the Tauri shell:

```bash
cd apps/desktop/src-tauri
cargo check
```

Run Python tests:

```bash
cd services/python-core
uv sync --extra test
uv run ruff check .
uv run python -m unittest discover -s tests -v
```

Run the repository hygiene check:

```bash
./scripts/maintenance/run-repo-hygiene-check.sh
```

## Repository Layout

- `apps/desktop`: Tauri UI, React routes, desktop shell commands, and frontend bridge code.
- `speech-service`: bundled MLX TTS/ASR HTTP service, Python 3.12 environment, and launchd lifecycle scripts.
- `services/python-core`: interview orchestration, script generation, provider dispatch, local storage, artifacts, and HTTP runtime.
- `packages/shared-schemas`: shared frontend/backend contract schemas.
- `scripts`: development and maintenance helpers.
- `docs`: gitignored local scratch (for example `tmp.md`, `plan.md`); human setup lives in README; agent constraints live in AGENTS.md.

Useful docs:

- [Agent collaboration contract](AGENTS.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## Data And Privacy

Aodcast is local-first. During development, generated sessions, imported source snapshots, scripts, Speech Plans, Render Manifests, Speaker References, transcripts, audio artifacts, provider configuration, and request-state files are stored under:

```text
.local-data/
```

This directory is ignored by Git and must not be committed.

API keys are stored as local user-managed configuration. Aodcast does not currently provide macOS Keychain integration or a dedicated secrets vault. Protect local config files, shell history, logs, screenshots, backups, synced folders, generated transcripts, and generated audio.

For ChatGPT subscription access, Codex owns OAuth storage and token refresh. Aodcast receives only account status, plan labels, model metadata, rate-limit summaries, and the generated model output; OAuth tokens and browser cookies are never copied into Aodcast configuration or bridge payloads.

Imported Markdown is snapshotted under `.local-data/sessions/<session-id>/source.json`. Script generation sends the normalized article, generation preferences, and any supplemental source discussion to the configured LLM provider. When that provider is remote, this content leaves the device and is handled under the provider's terms. Imported source text is not converted into transcript turns and is never written into Aodcast long-term memory; only later user-authored conversation turns may be eligible for memory when memory is enabled.

Long-term memory is local-only. When enabled, Aodcast saves a small set of reusable user knowledge as Markdown files under `.local-data/memory/` so interviews and scripts can stay consistent across episodes. Memory is opt-in (first-run notice), can be turned off per episode or globally, and is fully viewable and deletable. High-sensitivity secrets (passwords, API keys, payment credentials, full ID numbers, precise addresses) are never saved, even on request.

Do not open public issues or pull requests containing API keys, private prompts, imported source text, private generated content, local data paths, transcripts, or audio artifacts.

## Current Scope

Aodcast currently focuses on local-first solo podcast creation:

- platform: macOS desktop (Tauri) + local Python orchestration core
- input: a text topic or one local/pasted Markdown source per episode
- output: solo podcast script plus final audio from Episode Workspace
- LLM: mock, OpenAI-compatible, or ChatGPT subscription through Codex
- local speech identity: a preset voice selected per script; Speaker Reference assets are managed separately
- TTS: bundled local HTTP `speech-service` in an isolated process, or remote API providers
- memory: file-native, local-only long-term user memory across episodes

The Python speech client also supports file transcription. Speech-to-text UI input, multi-host formats, and a required cloud backend remain out of scope.

The app can serve common audio suffixes and validate uploaded Speaker Reference duration through local decoders or `ffprobe`. Export to compressed audio formats depends on local conversion tools. True video MP4 output is out of scope.

## Architecture And Behavior Notes

These notes describe current product behavior for humans and operators. Agent coding constraints live in [AGENTS.md](AGENTS.md).

### Interview and script offer

Offering script generation requires both content-dimension readiness and a minimum number of user answers (`MIN_USER_TURNS_FOR_SCRIPT_OFFER`, default 4). The interview keeps asking open-ended follow-ups and presents script generation only as a secondary option until the user explicitly finishes or chooses to generate.

### Memory

Long-term memory is file-native under `.local-data/memory/`. `entries/*.md` is the source of truth; `catalog.json` and `MEMORY.md` are rebuildable indexes. Only user turns become memories. Interview/script flows use read-only retrieval and do not block on background memory work.

### Podcast Editor and Speech Director

The Podcast Editor keeps generated scripts as plain spoken text while improving listening structure, sentence length, punctuation, and paragraph breathing. It does not add provider tags, stage directions, or synthetic filler. At the start of a full render, the Speech Director creates a versioned Speech Plan bound to the exact script hash. Editing the script makes the prior plan and render stale; generate the full audio again before local regeneration.

### Desktop bridge and long tasks

UI calls go through the desktop HTTP bridge to the local Python runtime. Long operations (audio render, voice preview, and similar) persist pollable `request_state`, expose progress, support cancel, and use `run_token` so retriggered runs do not show stale UI state. Full render and context-window regeneration share the script-scoped task id `render_audio:<session_id>:<script_id>`; cancellation must carry that run's token, so different scripts do not collide. Stateful long-task operations should otherwise be sequenced unless concurrency is under test.

### Episode Workspace and Voice Studio

- Episode Workspace keeps the script as the primary canvas, with Sources and Conversation in contextual drawers, Voice and Delivery in a lightweight inspector, and Preview/full audio controls in a persistent bottom dock.
- A full render saves immutable segment WAVs and a Render Manifest, then assembles the manifest's final WAV. MP3 is an on-demand sibling export next to that final render.
- Preview uses selected text, the current paragraph, or the script opening and creates disposable audio without replacing the current episode render.
- Existing audio remains playable after script, source, voice, or delivery changes and is labeled `Audio needs update` until a replacement render succeeds.
- Voice Studio owns reusable Speaker Reference assets. Local HTTP rendering uses the episode's preset voice instead of a reference. Explicitly selecting a local preset for a full render detaches an earlier cloning selection without deleting its source audio or older Render Manifests; local previews do not send reference audio.
- Built-in reference audio lives under `services/python-core/app/assets/speaker-references/` (tracked for now). User metadata lives in `.local-data/speaker-references/`; uploaded or recorded audio is normalized to immutable 48 kHz mono 16-bit PCM WAV under `.local-data/exports/_speaker_references/`. Creation requires the matching reference text; system audio capture is not available yet.
- The local speech service chooses and loads its active model. Aodcast records the selected provider and pipeline in each manifest. Speech Plan and context-window regeneration contracts remain internal rather than appearing in the primary UI.
- Artifact audio playback uses the localhost HTTP route `/api/v1/artifacts/audio` in both Web and Tauri shells.
- Tauri-only helpers such as Reveal in Finder live in shell helpers and are not part of the HTTP `DesktopBridge` surface.

### Local speech boundary

Aodcast's orchestration core contains no speech-model worker or in-process inference. `LocalSpeechClient` preserves the synchronous TTS provider contract while performing cancellable HTTP requests. The bundled `speech-service` process controls model loading, GPU concurrency, inference slicing, and ASR decoding. Preset voice selection remains stable across requests; reference audio and preceding generated audio are not sent as cloning or continuity conditions.

Manifest-driven assembly in Aodcast normalizes paragraph WAVs, applies one edge fade per segment, matches audible-sample RMS level, inserts editorial pauses, enforces a sample-peak ceiling, and writes `podcast.wav`. This publication stage remains separate from the service's inference-slice crossfades.

### Development operators

- `./scripts/dev/run-dev-all.sh` starts speech and waits for its health check before restarting the Python runtime on port `8765`; use `--reuse-runtime` only when process continuity is intentional.
- For audio-render debugging: check `/healthz` runtime metadata first, then `.local-data/runtime/request-state/*`, then frontend `run_token` filtering.
- Prefer sequenced CLI write-then-read flows (`start-interview`, `reply-session`, `generate-script`, `render-audio`, configure/show commands); parallel write/read can observe stale state.
- Desktop package validation: `pnpm --dir apps/desktop tauri:build` (do not forward extra cargo-style flags after `--`). Non-interactive DMG builds rely on `CI=true` so Finder AppleScript styling is skipped.
- Apply `chmod +x` before running a newly created script; do not race permission and execution.

## Contributing

Contributions are welcome. Keep changes small, update docs when behavior changes, and run the relevant verification commands before opening a pull request.

Do not commit `.local-data/`, `.env`, model weights, generated audio, transcripts, virtual environments, `node_modules`, build outputs, or private credentials.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution guide.

## Security

If you find a vulnerability, do not open a public issue with exploit details. Report it privately to `cxh1210@mail.ustc.edu.cn` or follow [SECURITY.md](SECURITY.md).

## License

Aodcast is released under the [MIT License](LICENSE).

Real-model verification results, cleanup inventory, memory measurements, and the replay script are recorded in [Speech decoupling acceptance report](SPEECH_DECOUPLING_REPORT.md).
