# Contributing to Aodcast

Thanks for helping improve Aodcast. This repository is currently an alpha-stage, local-first macOS desktop app with a Tauri frontend and Python orchestration core. For product behavior see [ARCHITECTURE.md](ARCHITECTURE.md); agent constraints live in [AGENTS.md](AGENTS.md).

## Development setup

Prerequisites:

- Apple Silicon macOS for the full desktop and bundled local speech service
- Python 3.13+ for orchestration and Python 3.12 for `speech-service` (separate `uv` environments)
- `uv`
- Node.js and `pnpm`
- Rust and Cargo
- `curl` and `lsof` for the development launcher
- FFmpeg for the bundled speech service and optional MP3 export (`brew install ffmpeg`)
- Optional: the official Codex CLI for ChatGPT subscription-provider development

Bootstrap from the repository root:

```bash
cd speech-service
uv sync --frozen
cp .env.example .env

cd ../services/python-core
uv sync --extra test

cd ../../apps/desktop
pnpm install

cd ../..
```

## Repository layout

- `apps/desktop`: Tauri UI, React routes, desktop shell commands, and frontend bridge code.
- `speech-service`: bundled MLX TTS/ASR HTTP service, Python 3.12 environment, and launchd lifecycle scripts.
- `services/python-core`: interview orchestration, script generation, provider dispatch, local storage, artifacts, and HTTP runtime.
- `packages/shared-schemas`: shared frontend/backend contract schemas.
- `scripts`: development and maintenance helpers.
- `docs`: gitignored local scratch (for example `tmp.md`, `plan.md`); human setup lives in README/CONTRIBUTING, architecture notes in ARCHITECTURE.md, agent constraints in AGENTS.md.

## Running locally

```bash
./scripts/dev/check-toolchain.sh
./scripts/dev/run-dev-all.sh
```

Both desktop and web launchers (`run-dev-all.sh`, `run-web-with-runtime.sh`) start the bundled `speech-service`, wait for `http://127.0.0.1:8090/health`, then start the orchestration runtime (`8765`) and UI (`1420`). Health checks do not download or warm up models; weights load on the first synthesis or transcription request. The native runtime readiness probe uses the built-in voice-preset API and must not load models or call speech. Direct `pnpm --dir apps/desktop tauri:dev` also runs the speech-service health prerequisite before starting its web shell. The checkout can live in any folder; launchers resolve paths relative to the repository.

Use `Ctrl+C` in the launcher terminal to stop development processes it owns. An explicitly reused runtime is left running. Speech remains shared and runs until explicitly stopped.

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

Run pieces individually:

```bash
./scripts/dev/run-python-core.sh --serve-http --host 127.0.0.1 --port 8765
```

## Development operators

- `run-dev-all.sh` starts speech and waits for its health check before restarting the Python runtime on port `8765`; use `--reuse-runtime` only when process continuity is intentional.
- For audio-render debugging: check `/healthz` runtime metadata first, then `.local-data/runtime/request-state/*`, then frontend `run_token` filtering.
- `run-python-core.sh` is an operator CLI only: `--serve-http`, `--configure-llm-provider`/`--configure-tts-provider`, `--show-llm-config`/`--show-tts-config`, `--check-llm-config`, `--show-local-tts-capability`, `--list-models-status`, and `--create-demo-session`. Each prints one JSON object. Interviews, scripts, and audio run through the HTTP runtime.
- Desktop package validation: `pnpm --dir apps/desktop tauri:build` (do not forward extra cargo-style flags after `--`). Non-interactive DMG builds rely on `CI=true` so Finder AppleScript styling is skipped.
- Apply `chmod +x` before running a newly created script; do not race permission and execution.
- To refresh README screenshots: run `./scripts/dev/run-dev-all.sh`, capture the current UI, save stable filenames under `images/`, and update both `README.md` and `README.zh-CN.md`. Do not include API keys, local paths, private prompts, or user data.

## First smoke test

Use the mock LLM provider first to verify interview and script generation without paid API access. From the repository root:

```bash
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --configure-tts-provider local_http
./scripts/dev/run-python-core.sh --create-demo-session
./scripts/dev/run-dev-all.sh
```

In the app, create or open an episode, continue its conversation, create a draft, and preview or render audio from the Episode Workspace.

## Provider setup

Provider settings are stored locally under `.local-data/` and are not intended for version control.

### Mock LLM

```bash
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --configure-tts-provider local_http
```

Check whether the saved LLM configuration is ready for interview and script generation:

```bash
./scripts/dev/run-python-core.sh --check-llm-config
```

### ChatGPT subscription through Codex

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

### OpenAI-compatible providers

LLM:

```bash
./scripts/dev/run-python-core.sh \
  --configure-llm-provider openai_compatible \
  --llm-base-url "https://api.openai.com/v1" \
  --llm-model "gpt-4o-mini" \
  --llm-api-key "<your-key>"
```

TTS:

```bash
./scripts/dev/run-python-core.sh \
  --configure-tts-provider openai_compatible \
  --tts-base-url "https://api.openai.com/v1" \
  --tts-model "gpt-4o-mini-tts" \
  --tts-api-key "<your-key>" \
  --tts-voice "alloy" \
  --tts-audio-format "wav"
```

### Environment variables

Aodcast does not require a `.env` file for normal development. `.env.example` documents `VITE_AODCAST_RUNTIME_URL` for pointing a parallel worktree's Vite shell at its own local runtime. `AODCAST_SPEECH_URL` supplies the default speech endpoint when provider settings have no saved base URL; a saved `--tts-base-url` takes priority. Export this variable before starting the app: the Python core reads process environment variables and does not automatically load `.env`. Speech-model settings and optional Hugging Face mirror/token/cache overrides belong in `speech-service/.env`, which that service loads itself. Weights stay in the external Hugging Face cache and are never committed. If Codex is installed outside `PATH`, `/opt/homebrew/bin`, or `/usr/local/bin`, set `AODCAST_CODEX_BIN` to the absolute official Codex executable path.

## Exporting MP3

Final renders stay WAV. After audio exists, use **Export** next to the final render. MP3 conversion requires FFmpeg on the local machine.

- Aodcast writes a 192 kbps MP3 beside the WAV, for example `.local-data/exports/<session-id>/renders/<render-id>/podcast.mp3`.
- Finder opens on the MP3 so you can upload it to Xiaoyuzhou or any other host.
- Aodcast does not store platform credentials, upload audio, generate RSS, or track remote publication state.

## Bundled local speech service

Aodcast's default TTS provider is `local_http`. It uses `httpx` to call the bundled native macOS `speech-service` at `http://127.0.0.1:8090/v1`. Source code ships in this repository; inference stays in a separate process and Python 3.12 `.venv`. The orchestration core uses its own Python 3.13+ environment and does not import inference libraries. Install inference dependencies only into `speech-service/.venv` and configure models in `speech-service/.env`; weights remain in the external Hugging Face cache. See the [service README](speech-service/README.md) for configuration and memory limits.

The desktop/web launchers start speech automatically. To manage it alone from the repository root, use `./speech-service/service.sh start|stop|restart|status|logs` (choose one action):

```bash
./speech-service/service.sh start
curl http://127.0.0.1:8090/health
```

`start` installs/enables the current user's LaunchAgent `com.aodcast.speech-service`, including login startup; `stop` disables it. Logs are under `~/Library/Logs/Aodcast/speech-service/`. Closing Aodcast does not stop speech. Idle unloading releases model weights while leaving HTTP running.

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

The HTTP client uses a 1,800-second read timeout and a 30-second connect timeout. A stopped service produces an actionable error directing you to `./speech-service/service.sh start`. Boundary details (natural paragraphs, slicing, assembly) are in [ARCHITECTURE.md](ARCHITECTURE.md#local-speech-boundary).

### Transcription from Python

Run from `services/python-core` after `uv sync --extra test`:

```python
from app.providers.local_speech.client import LocalSpeechClient

client = LocalSpeechClient()
text = client.transcribe("/absolute/path/to/audio.wav", language="zh")
print(text)
```

ASR is a new Python client capability; it is not a microphone-input or subtitle-editing UI workflow.

## Verification before opening a PR

Run the same checks used for release readiness:

```bash
./scripts/maintenance/run-repo-hygiene-check.sh

cd apps/desktop
pnpm check
pnpm test
pnpm build:web

cd src-tauri
cargo check

cd ../../../services/python-core
uv run --extra test ruff check app tests
uv run --extra test pytest -q
uv run --extra test python -m unittest discover -s tests -v
```

### Real-model verification

For changes to speech integration, run with the speech service online. From the repository root:

```bash
./speech-service/service.sh start
cd services/python-core
uv run --extra test python ../../scripts/verification/verify-local-speech.py
uv run --extra test python ../../scripts/verification/verify-local-clone.py
```

`verify-local-speech.py` runs the real TTS→ASR loopback and a 1,246-character podcast pipeline. It writes WAV files, `results.json`, and per-second `memory.jsonl` into a new `.local-data/speech-verification/<timestamp>/` directory, uses real speech models and a deterministic mock LLM only for editorial planning, and checks the spoken closing marker to detect truncated long audio.

On 2026-10-15, the 16 GiB Apple M4 run produced a 9.04-second short WAV in 51.00 seconds (first load), recognized it in 9.20 seconds with 0% normalized character error, and rendered the 1,246-character paragraph in 207.94 seconds into 266.31 seconds of audio. The service handled all 11 inference slices. Service RSS peaked at 2.07 GiB and Metal allocation at 6.68 GiB; those counters use different accounting and must not be added. These are measurements of the earlier decoupling acceptance run, not a new migration benchmark or performance guarantees.

`verify-local-clone.py` reuses one Speaker Reference for both Base models (pass `--reference /path/to/friend.wav --reference-text "exact transcript"` to use your own recording). On 2026-10-25 (16 GiB M4, 8.2-second generated reference, about 18 GiB of macOS swap in use from other apps), both models passed. Each one rendered a short clone that ASR read back with 0% character error, a 4-segment episode with its closing marker intact, and a 3-segment context-window regeneration. The 0.6B episode was 38.2 s of audio in 96.6 s; the 1.7B episode was 37.1 s in 132.8 s. Metal peak allocation reached 6.27 GiB with 0.6B and 7.25 GiB after 1.7B; the counter is cumulative for the service process. Because the service keeps one model resident, alternating between 0.6B and 1.7B reloads weights each time, and under heavy swap a single 1.7B slice can take minutes. Compare by previewing one passage per model rather than interleaving full renders.

Keep test substitutes separate from real model evidence.

## Contribution guidelines

- Keep changes small, reviewable, and behavior-preserving unless the PR explicitly changes behavior.
- Update docs when changing user flow, storage shape, provider configuration, runtime behavior, or development workflow.
- Do not commit `.local-data/`, model weights, `.env`, `.omx/`, `docs/`, build outputs, virtualenvs, or node modules. Also keep out generated audio, transcripts, and private credentials.
- Do not commit API keys, provider credentials, private prompts, generated audio, or user session data. Do not open public issues or pull requests containing them, imported source text, private generated content, local data paths, transcripts, or audio artifacts.
- For refactors, protect supported behavior with tests and prefer deletion/reuse over new abstractions. The local speech provider supports preset voices, Qwen3 Base reference cloning, WAV, normal speed, and transcription; style, exact pauses, and continuity conditioning require explicit unsupported feedback.
- Keep inference-memory slicing inside the bundled, process-isolated `speech-service`. Preserve Aodcast natural-paragraph Speech Plans and manifest assembly for editing and publication.
- Real-model integration checks require the running speech service. Do not report mocked client tests as model, quality, or performance validation.

## Commit messages

Use clear, decision-oriented commit messages. If a change encodes an important tradeoff, add trailers such as `Constraint:`, `Rejected:`, `Tested:`, and `Not-tested:` in the commit body.
