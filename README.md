# Aodcast

Aodcast is an open source macOS desktop app for AI-guided podcast creation.

The MVP is scoped to a local-first workflow:

1. User enters a topic in text.
2. AI conducts an interview to gather usable material.
3. The system generates a solo podcast script.
4. The user edits the script directly.
5. The system renders final audio through a remote TTS API or a local MLX-backed TTS provider.

When the UI runs inside Tauri, desktop actions are routed into the Python orchestration core through a Tauri command bridge. Browser-only runs still fall back to the mock bridge for UI iteration.

The repository is organized for long-term multi-agent collaboration. Start with:

- [AGENTS.md](/Users/chuhaonan/codeMIni-hn/github/Aodcast/AGENTS.md)
- [MVP design spec](/Users/chuhaonan/codeMIni-hn/github/Aodcast/docs/superpowers/specs/2026-03-28-echomind-podcast-mvp-design.md)
- [Agent governance](/Users/chuhaonan/codeMIni-hn/github/Aodcast/docs/operations/agent-governance.md)

## Bootstrap Commands

Run from the repository root:

- `cd apps/desktop && pnpm install`
- `cd services/python-core && uv venv .venv`
- `cd services/python-core && uv pip install --python .venv/bin/python '.[local-mlx]'`
- `./scripts/dev/check-toolchain.sh`
- `./scripts/dev/run-python-core.sh --create-demo-session`
- `./scripts/dev/run-python-core.sh --start-interview <session-id>`
- `./scripts/dev/run-python-core.sh --reply-session <session-id> --message "your answer"`
- `./scripts/dev/run-python-core.sh --configure-llm-provider mock`
- `./scripts/dev/run-python-core.sh --generate-script <session-id>`
- `./scripts/dev/run-python-core.sh --configure-tts-provider mock_remote`
- `./scripts/dev/run-python-core.sh --show-local-tts-capability`
- `./scripts/dev/run-python-core.sh --render-audio <session-id>`
- `./scripts/dev/run-desktop.sh`
- `./scripts/maintenance/run-repo-hygiene-check.sh`

Current environment note:

- The Python core can be bootstrapped locally today.
- Frontend dependency installation may require network-enabled execution in this environment.
- Tauri runtime verification requires `cargo`, which is not currently available on `PATH` in this environment.

## Local MLX Notes

- The Python runner script prefers `services/python-core/.venv/bin/python` when it exists.
- Use `./scripts/dev/run-python-core.sh --show-local-tts-capability` before selecting `local_mlx`.
- Install the full local stack with `uv pip install --python .venv/bin/python '.[local-mlx]'` so both `mlx` and `mlx-audio` are available.
- The default local model target is `mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit`.
- Use `./scripts/dev/run-python-core.sh --configure-tts-provider local_mlx --clear-tts-local-model-path` to switch from a stale local path back to the default Hugging Face repo-id mode.
- A local model directory must now look like a real MLX export and include at least one `.safetensors` file. The placeholder sample directory is useful for docs and path examples, but it is not treated as an executable model bundle anymore.

## Maintenance

- Use `./scripts/maintenance/run-repo-hygiene-check.sh` for the default Milestone 7 maintenance sweep.
- Store maintenance outcomes in `.agent/reports/`.

## Desktop Bridge

- The real desktop path is `React -> Tauri invoke -> Rust commands -> scripts/dev/run-python-core.sh -> app.main`.
- Python bridge calls should use `--bridge-json` so stdout remains a single JSON envelope for Rust to parse.
- If native Tauri validation is blocked by missing `cargo`, keep validating the Python bridge and frontend types independently until the Rust toolchain is available.
