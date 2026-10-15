# Contributing to Aodcast

Thanks for helping improve Aodcast. This repository is currently an alpha-stage, local-first macOS desktop app with a Tauri frontend and Python orchestration core.

## Development setup

Prerequisites:

- Apple Silicon macOS for the full desktop and bundled local speech service
- Python 3.13+ for orchestration and Python 3.12 for `speech-service` (separate `uv` environments)
- `uv`
- Node.js and `pnpm`
- Rust and Cargo
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

## Running locally

```bash
./scripts/dev/check-toolchain.sh
./scripts/dev/run-dev-all.sh
```

Both desktop and web launchers start the bundled `speech-service`, wait for `http://127.0.0.1:8090/health`, then start the orchestration runtime (`8765`) and UI (`1420`). Health checks do not download or warm up models. The native runtime readiness probe uses the built-in voice-preset API and must not load models or call speech.

Use `Ctrl+C` in the launcher terminal to stop development processes it owns. Speech remains shared and runs until explicitly stopped. From the repository root:

```bash
./speech-service/service.sh status
./speech-service/service.sh logs
./speech-service/service.sh stop
```

The same script supports `start` and `restart`; its current-user LaunchAgent is `com.aodcast.speech-service`. Install inference dependencies only into `speech-service/.venv` and configure models in `speech-service/.env`; weights remain in the external Hugging Face cache. The orchestration core stays a lightweight HTTP client. See [service setup](speech-service/README.md).

For backend-only smoke testing with the mock LLM provider:

```bash
./scripts/dev/run-python-core.sh --create-demo-session
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --configure-tts-provider local_http
```

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

From the repository root, run real-model verification for changes to speech integration with the speech service online:

```bash
./speech-service/service.sh start
cd services/python-core
uv run --extra test python ../../scripts/verification/verify-local-speech.py
```

Results and memory samples are written into a new `.local-data/speech-verification/<timestamp>/` directory. See [the measured acceptance report](SPEECH_DECOUPLING_REPORT.md); keep test substitutes separate from real model evidence.

## Contribution guidelines

- Keep changes small, reviewable, and behavior-preserving unless the PR explicitly changes behavior.
- Update docs when changing user flow, storage shape, provider configuration, runtime behavior, or development workflow.
- Do not commit `.local-data/`, model weights, `.env`, `.omx/`, `docs/`, build outputs, virtualenvs, or node modules.
- Do not commit API keys, provider credentials, private prompts, generated audio, or user session data.
- For refactors, protect supported behavior with tests and prefer deletion/reuse over new abstractions. The local speech provider supports preset voices, WAV, normal speed, and transcription; cloning, style, exact pauses, and continuity conditioning require explicit unsupported feedback.
- Keep inference-memory slicing inside the bundled, process-isolated `speech-service`. Preserve Aodcast natural-paragraph Speech Plans and manifest assembly for editing and publication.
- Real-model integration checks require the running speech service. Do not report mocked client tests as model, quality, or performance validation.

## Commit messages

Use clear, decision-oriented commit messages. If a change encodes an important tradeoff, add trailers such as `Constraint:`, `Rejected:`, `Tested:`, and `Not-tested:` in the commit body.
