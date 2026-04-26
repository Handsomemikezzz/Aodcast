# Local MLX Quickstart

Local MLX TTS is a primary first-release capability for Aodcast. It targets local-first speech generation on supported macOS machines.

## Requirements

- macOS, preferably Apple Silicon
- Python 3.13+
- `uv`
- enough disk space for model weights
- enough unified memory for the selected model

The local MLX path is runtime-gated. Always check capability before selecting it.

## Install Python dependencies

From the repository root:

```bash
cd services/python-core
uv venv .venv
uv pip install --python .venv/bin/python -e '.[local-mlx]'
cd ../..
```

## Download model weights

The default model target is:

```text
mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit
```

Download into a user-owned model directory:

```bash
uv run --with huggingface_hub --with tqdm \
  scripts/model-download/download_qwen3_tts_mlx.py \
  --base-dir "${HF_HUB_CACHE:-$HOME/.cache/huggingface/hub}"
```

If a repository requires authentication, pass `--token` or set `HF_TOKEN` locally. Do not commit tokens.

## Check capability

```bash
./scripts/dev/run-python-core.sh --show-local-tts-capability
```

The capability report is the source of truth. It checks the platform, Python environment, MLX imports, model path, and bootstrap behavior.

## Configure local MLX

Use the default Hugging Face repo-id mode:

```bash
./scripts/dev/run-python-core.sh \
  --configure-tts-provider local_mlx \
  --clear-tts-local-model-path
```

Or use an explicit local model directory:

```bash
./scripts/dev/run-python-core.sh \
  --configure-tts-provider local_mlx \
  --tts-local-model-path "${HF_HUB_CACHE:-$HOME/.cache/huggingface/hub}/Qwen3-TTS-12Hz-0.6B-Base-8bit"
```

A local model directory must contain a real MLX export, including `.safetensors` weights. Placeholder directories are useful for docs/tests but are not executable model bundles.

## Validate with a render

Use mock LLM if you only want to validate the audio path:

```bash
./scripts/dev/run-python-core.sh --configure-llm-provider mock
./scripts/dev/run-python-core.sh --create-demo-session
./scripts/dev/run-python-core.sh --configure-tts-provider local_mlx --clear-tts-local-model-path
./scripts/dev/run-python-core.sh --render-audio <session-id>
```

## Notes and limitations

- First render may be slow because the worker loads the model.
- Long scripts are chunked and joined by the project runner.
- Voice Studio preview rendering is a pollable long task.
- Aodcast does not currently provide voice cloning.
- `.mp4` support is audio-container support when the selected provider/runtime creates a valid file; Aodcast does not currently transcode WAV to video MP4.
