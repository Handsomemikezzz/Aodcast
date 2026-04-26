# Contributing to Aodcast

Thanks for helping improve Aodcast. This repository is currently an alpha-stage, local-first macOS desktop app with a Tauri frontend and Python orchestration core.

## Development setup

Prerequisites:

- macOS for the full desktop/local MLX path
- Python 3.13+
- `uv`
- Node.js and `pnpm`
- Rust and Cargo

Bootstrap from the repository root:

```bash
cd services/python-core
uv venv .venv
uv pip install --python .venv/bin/python -e .
# For the primary local MLX TTS path on supported macOS machines:
uv pip install --python .venv/bin/python -e '.[local-mlx]'

cd ../../apps/desktop
pnpm install
```

## Running locally

```bash
./scripts/dev/check-toolchain.sh
./scripts/dev/run-dev-all.sh
```

For backend-only smoke testing with mock providers:

```bash
./scripts/dev/run-python-core.sh --create-demo-session
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --configure-tts-provider mock_remote
```

## Verification before opening a PR

Run the same checks used for release readiness:

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

## Contribution guidelines

- Keep changes small, reviewable, and behavior-preserving unless the PR explicitly changes behavior.
- Update docs when changing user flow, storage shape, provider configuration, runtime behavior, or development workflow.
- Do not commit `.local-data/`, model weights, `.env`, `.omx/`, `docs-local/`, build outputs, virtualenvs, or node modules.
- Do not commit API keys, provider credentials, private prompts, generated audio, or user session data.
- For refactors, protect existing behavior with tests first and prefer deletion/reuse over new abstractions.

## Commit messages

Use clear, decision-oriented commit messages. If a change encodes an important tradeoff, add trailers such as `Constraint:`, `Rejected:`, `Tested:`, and `Not-tested:` in the commit body.
