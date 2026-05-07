# Aodcast

![Status](https://img.shields.io/badge/status-source--alpha-orange)
![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![License](https://img.shields.io/badge/license-MIT-blue)

Aodcast is an open source, local-first macOS desktop app for AI-guided podcast creation.

It turns a text topic into an interview-guided solo podcast script, then helps you edit script snapshots and render audio through Voice Studio. The current release target is a **GitHub source-code alpha** for developers and early testers, not a polished signed or notarized macOS distribution.

## Project Status

Aodcast is usable as a development build. Expect rough edges, local setup requirements, and active changes to the app flow.

| Area | Status |
| --- | --- |
| macOS desktop development workflow | Available |
| Tauri app shell + local Python HTTP runtime | Available |
| Text-topic interview flow | Available |
| Solo script generation and script snapshots | Available |
| Voice Studio preview/take workflow | Available |
| Local MLX-backed TTS | Alpha, hardware/model dependent |
| OpenAI-compatible LLM/TTS providers | Configurable |
| Mock providers for smoke testing | Available |
| Signed/notarized macOS app package | Not available |
| Speech-to-text input, voice cloning, multi-host shows | Out of scope |

## What It Does

1. Enter a podcast topic in text.
2. Let the app interview you to gather useful material.
3. Generate a solo podcast script.
4. Edit and manage multiple script snapshots from the same session.
5. Use Voice Studio to preview voices, lock a reference voice, generate takes, and select final audio.

## Screenshots

Screenshots and short demo clips should be added before a tagged public alpha announcement. For now, this repository is optimized for source-code review and local developer testing.

## Repository Layout

- `apps/desktop`: Tauri UI and desktop shell
- `services/python-core`: interview orchestration, script generation, provider dispatch, local storage, and HTTP runtime
- `packages/shared-schemas`: shared frontend/backend contracts
- `docs/product`: product-facing behavior notes
- `docs/architecture`: architecture and data-flow notes
- `docs/operations`: agent governance and maintenance workflow docs
- `docs/superpowers`: implementation specs and milestone plans
- `examples`: sample placeholders and examples
- `scripts`: development, maintenance, release, and model-download helpers

Useful starting points:

- [Product overview](docs/product/product-overview.md)
- [Configuration](docs/configuration.md)
- [Local MLX quickstart](docs/local-mlx-quickstart.md)
- [Repository layout](docs/architecture/repository-layout.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## Requirements

- macOS for the full desktop path
- Python 3.13+
- `uv`
- Node.js
- `pnpm`
- Rust and Cargo

Local MLX TTS works best on compatible Apple Silicon machines and requires model weights. Always use the capability checker before assuming the local MLX path is available.

Check your local toolchain:

```bash
./scripts/dev/check-toolchain.sh
```

## Quick Start

From the repository root:

```bash
cd services/python-core
uv venv .venv
uv pip install --python .venv/bin/python -e .

cd ../../apps/desktop
pnpm install

cd ../..
./scripts/dev/run-dev-all.sh
```

`run-dev-all.sh` starts the Python runtime on `127.0.0.1:8765`, clears stale dev-server state, and launches the Tauri development app. The web dev server is served at `http://localhost:1420`.

## Smoke Test With Mock Providers

Mock providers are intended for development and CI smoke paths. They let you test the app without a paid LLM or TTS provider.

```bash
./scripts/dev/run-python-core.sh --create-demo-session
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --configure-tts-provider mock_remote
```

Mock output is not the primary product experience. Use real configured providers or local MLX when evaluating actual generation quality.

## Local MLX TTS

Install the optional local MLX dependency group:

```bash
cd services/python-core
uv pip install --python .venv/bin/python -e '.[local-mlx]'
cd ../..
```

Download the default model into a user-owned Hugging Face cache/model folder:

```bash
uv run --with huggingface_hub --with tqdm \
  scripts/model-download/download_qwen3_tts_mlx.py \
  --base-dir "${HF_HUB_CACHE:-$HOME/.cache/huggingface/hub}"
```

Check whether local MLX is actually usable on your machine:

```bash
./scripts/dev/run-python-core.sh --show-local-tts-capability
```

Configure the local MLX provider in repo-id mode:

```bash
./scripts/dev/run-python-core.sh \
  --configure-tts-provider local_mlx \
  --clear-tts-local-model-path
```

See [Local MLX quickstart](docs/local-mlx-quickstart.md) for model storage, troubleshooting, and hardware notes.

## Provider Configuration

Aodcast supports development mock providers, a primary local MLX TTS path, and OpenAI-compatible remote provider adapters.

See [Configuration](docs/configuration.md) for:

- LLM provider setup
- TTS provider setup
- local config behavior
- optional environment variables
- API key handling notes

## Local Data And Privacy

Aodcast is local-first. During development, generated sessions, provider configuration, transcripts, scripts, audio files, and request-state files are stored under:

```text
.local-data/
```

This directory is ignored by Git and must not be committed.

API keys are currently stored as local user-managed configuration. Aodcast does **not** yet provide macOS Keychain integration or a dedicated secrets vault. Users are responsible for protecting local config files, shell history, logs, screenshots, backups, synced folders, and generated project data.

Do not open public issues or pull requests containing API keys, private prompts, generated private content, local data paths, transcripts, or audio artifacts.

## Verification

Run the release-readiness checks before opening a pull request:

```bash
./scripts/maintenance/run-repo-hygiene-check.sh

cd apps/desktop
pnpm check
pnpm build:web

cd src-tauri
cargo check

cd ../../../services/python-core
.venv/bin/python -m unittest discover -s tests -v
```

Notes:

- `run-repo-hygiene-check.sh` includes Python tests, frontend typecheck, and frontend web build.
- `cargo check` is run separately under `apps/desktop/src-tauri`.
- Full macOS signing, notarization, and packaged distribution are not part of the source-code alpha gate.

## Contributing

Contributions are welcome while the project is in alpha, especially focused fixes, setup improvements, documentation, tests, and small behavior improvements.

Before opening a pull request:

1. Keep the change small and reviewable.
2. Update docs when changing user flow, storage shape, provider configuration, runtime behavior, or development workflow.
3. Run the verification commands above.
4. Do not commit `.local-data/`, `.env`, model weights, generated audio, transcripts, virtualenvs, node modules, build outputs, or private credentials.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution guide.

## Roadmap

Near-term alpha work:

- improve first-run setup and error recovery
- add public screenshots and demo clips
- harden provider configuration UX
- improve local model download/status flows
- expand automated smoke coverage
- prepare a cleaner source alpha release checklist

Out of scope for the current alpha:

- cloud backend dependency
- speech-to-text input
- long-term user memory
- multi-host podcast formats
- voice cloning
- polished signed/notarized macOS distribution

## Security

This is an alpha-stage local desktop project and is not yet hardened as a packaged application. If you find a vulnerability, do not open a public issue with exploit details. Follow the private reporting guidance in [SECURITY.md](SECURITY.md).

## License

Aodcast is released under the [MIT License](LICENSE).
