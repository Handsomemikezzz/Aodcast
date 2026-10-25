# Aodcast Python Core

Local orchestration core for Aodcast. It owns interviews, scripts, provider dispatch, storage, the localhost HTTP runtime, and long-running task state. Speech models run in the bundled `speech-service` process, isolated in its own Python 3.12 environment.

## Setup and lifecycle

Use Python 3.13+. From this directory:

```bash
uv sync --extra test
```

From the Aodcast repository root, start the runtime alone:

```bash
./scripts/dev/run-python-core.sh --serve-http --host 127.0.0.1 --port 8765
```

Alternatively, `./scripts/dev/run-dev-all.sh` first starts the bundled speech service and waits for `8090/health`, then starts the runtime and Tauri/Vite. `run-web-with-runtime.sh` follows the same order. The runtime health check is `http://127.0.0.1:8765/healthz`; the development UI is `http://localhost:1420`. Native runtime readiness probes the built-in `/api/v1/voice-studio/presets` route and never loads speech models. Launcher health checks do not warm up models.

## Bundled speech service

The default `local_http` provider uses `httpx` to call `http://127.0.0.1:8090/v1`. The orchestration core contains no speech-model worker, inference dependencies, or weight downloader. Speech implementation and dependencies live in `speech-service/` in this same repository. From the repository root:

```bash
./speech-service/service.sh start
curl --fail http://127.0.0.1:8090/health
```

The same script supports `stop`, `restart`, `status`, and `logs`. Stopping Aodcast does not stop the speech service. The service lazily loads weights and unloads them after idle time; `loaded: false` is an expected healthy state. Install model dependencies with `(cd speech-service && uv sync --frozen)` and configure `HF_ENDPOINT`, voices, and language in `speech-service/.env`. Model weights remain in the external Hugging Face cache, outside Git. The LaunchAgent is `com.aodcast.speech-service`, with logs under `~/Library/Logs/Aodcast/speech-service/`. See the [service README](../../speech-service/README.md).

| API | Contract |
| --- | --- |
| `POST /v1/audio/speech` | JSON `input`, `voice`, `response_format: "wav"`; PCM16 WAV response |
| `POST /v1/audio/speech/clone` | Multipart `reference` WAV, exact `reference_text`, `input`, Base `model`, `language`; PCM16 WAV response |
| `POST /v1/audio/transcriptions` | Multipart `file` (WAV/MP3/M4A); JSON `text` response |
| `GET /health` | Configured and clone models, loaded state, reference-length window, process and Metal memory |

`LocalSpeechClient.transcribe(path, language=None) -> str` exposes ASR to Python. This is not a microphone-input or subtitle-editing UI. `LocalSpeechTTSProvider.synthesize(TTSGenerationRequest) -> TTSGenerationResponse` preserves the rendering contract and submits complete natural paragraphs with a 1,800-second read timeout and 30-second connect timeout. For preset models the adapter uses the service's actual model for voice mapping and response metadata; for the Qwen3 Base clone models it sends the selected model and the Speaker Reference with every segment. A stopped service produces an actionable startup message.

The service owns GPU serialization, inference slicing, silence trimming, slice crossfades, and model memory. Aodcast retains editorial Speech Plans, immutable paragraph audio, manifest publication, and podcast assembly. Local rendering supports preset voices, zero-shot Speaker Reference cloning with `Qwen3-TTS-12Hz-0.6B-Base-8bit` (default) or `1.7B-Base-8bit`, WAV, and normal speed. A clone model without a reference, or a reference sent to a preset model, fails explicitly. Style instructions, exact pause durations, and preceding-audio conditioning are unsupported; natural punctuation only approximates editorial pauses. Explicitly selecting a local preset for a full render detaches an older reference selection while preserving its audio assets and older manifests.

`AODCAST_SPEECH_URL` is a process environment variable used when no base URL is saved. Export it before starting Aodcast or configure `--tts-base-url`; the Python core does not automatically load a `.env` file.

## Verification

From this directory:

```bash
uv run --extra test ruff check app tests
uv run --extra test pytest -q
uv run --extra test python -m unittest discover -s tests -v
uv run --extra test python ../../scripts/verification/verify-local-speech.py
```

The last command requires the running speech service and performs real TTS→ASR and 1,246-character pipeline validation. It writes WAVs, results, and per-second memory samples under the repository's `.local-data/speech-verification/<timestamp>/`. Editorial planning uses a mock LLM; speech inference is real. See the [root README](../../README.md) for measured results and product setup.
