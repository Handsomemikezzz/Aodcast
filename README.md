# Aodcast

Aodcast is an open source, local-first macOS desktop app for AI-guided podcast creation.

The current release target is a **GitHub source-code alpha**, not a polished packaged desktop distribution. The app is designed for developers and early testers who are comfortable running a Tauri frontend and a local Python orchestration runtime.

## What it does

1. You enter a podcast topic in text.
2. AI conducts an interview to gather usable material.
3. Aodcast generates a solo podcast script.
4. You edit and manage script snapshots.
5. Voice Studio renders preview and final audio, with local MLX TTS as the primary first-release path.

## Current scope

In scope for the alpha:

- macOS desktop development workflow
- Tauri app shell plus local Python HTTP runtime
- text-topic input
- interview-driven solo script generation
- script snapshots and editing
- Voice Studio preview/take flow
- local MLX-backed TTS as the primary first-release capability
- mock providers for smoke testing and development fallback
- OpenAI-compatible LLM/TTS adapters for user-configured providers

Out of scope for the alpha:

- speech-to-text input
- long-term user memory
- multi-host podcast formats
- cloud backend dependency
- voice cloning
- polished signed/notarized macOS app distribution

## Repository map

- `apps/desktop`: Tauri UI and app shell
- `services/python-core`: interview orchestration, script generation, provider dispatch, storage, and HTTP runtime
- `packages/shared-schemas`: shared data contracts and schemas
- `docs/architecture`: architecture notes
- `docs/operations`: agent governance and maintenance docs
- `docs/superpowers`: implementation specs/plans from development milestones
- `examples`: sample placeholders and examples
- `scripts`: development, maintenance, release, and model-download helpers

Start with:

- [Product overview](docs/product/product-overview.md)
- [Local MLX quickstart](docs/local-mlx-quickstart.md)
- [Configuration](docs/configuration.md)
- [Repository layout](docs/architecture/repository-layout.md)
- [Contributing guide](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

## Prerequisites

- macOS for the full desktop/local MLX path
- Python 3.13+
- `uv`
- Node.js and `pnpm`
- Rust and Cargo

Local MLX works best on compatible Apple Silicon machines and requires model weights. The capability checker is the source of truth for whether the local path is available on a given machine.

## Bootstrap

From the repository root:

```bash
cd services/python-core
uv venv .venv
uv pip install --python .venv/bin/python -e .

# Install the primary local MLX TTS stack on supported macOS machines:
uv pip install --python .venv/bin/python -e '.[local-mlx]'

cd ../../apps/desktop
pnpm install
```

## Run the app during development

```bash
./scripts/dev/check-toolchain.sh
./scripts/dev/run-dev-all.sh
```

The Tauri/web UI talks to the Python orchestration core through a localhost HTTP runtime. Browser-only development and Tauri development both use the HTTP bridge path.

## Smoke test with mock providers

Mock providers are for development and CI smoke paths. They are not the primary product experience.

```bash
./scripts/dev/run-python-core.sh --create-demo-session
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --configure-tts-provider mock_remote
```

## Local MLX quickstart

Install local MLX dependencies:

```bash
cd services/python-core
uv pip install --python .venv/bin/python -e '.[local-mlx]'
cd ../..
```

Download the default model to a user-owned model folder:

```bash
uv run --with huggingface_hub --with tqdm \
  scripts/model-download/download_qwen3_tts_mlx.py \
  --base-dir "$HOME/Library/Application Support/Aodcast/models"
```

Check capability before selecting local MLX:

```bash
./scripts/dev/run-python-core.sh --show-local-tts-capability
```

Configure local MLX in repo-id mode:

```bash
./scripts/dev/run-python-core.sh \
  --configure-tts-provider local_mlx \
  --clear-tts-local-model-path
```

See [Local MLX quickstart](docs/local-mlx-quickstart.md) for details and troubleshooting.

## Provider configuration and API keys

See [Configuration](docs/configuration.md).

Aodcast stores provider configuration locally for a local-first workflow. API keys entered by users are managed on the user's own machine. Users are responsible for protecting local config files, backups, shell history, logs, screenshots, and generated project data.

## Verification

Run before opening a PR or merging release-prep work:

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
- Full macOS packaging/signing/notarization is not part of the source-code alpha release gate.

## License

Aodcast is released under the [MIT License](LICENSE).
