# Configuration

Aodcast is local-first. Provider settings are stored on the user's machine under the local data directory and are not intended for version control.

## Local data directory

By default, the Python core uses:

```text
.local-data/
```

inside the repository checkout during development. This directory may contain provider settings, generated sessions, transcripts, scripts, audio artifacts, request-state files, and other local runtime data. It is ignored by Git and should not be committed.

## API key storage model

Aodcast currently stores API keys as local user-managed configuration. It does not yet provide macOS Keychain integration or a dedicated secrets vault.

Users are responsible for protecting:

- provider API keys
- local config files
- shell history
- screenshots and logs
- backups and synced folders
- generated user content

For public issues and pull requests, redact keys, tokens, generated private content, and local data paths.

## Provider configuration

The app supports development mock providers and configurable provider adapters.

### LLM provider

Development smoke path:

```bash
./scripts/dev/run-python-core.sh --configure-llm-provider mock
```

OpenAI-compatible path:

```bash
./scripts/dev/run-python-core.sh \
  --configure-llm-provider openai_compatible \
  --llm-base-url "https://api.openai.com/v1" \
  --llm-model "gpt-4o-mini" \
  --llm-api-key "<your-key>"
```

### TTS provider

Development smoke path:

```bash
./scripts/dev/run-python-core.sh --configure-tts-provider mock_remote
```

Primary local MLX path:

```bash
./scripts/dev/run-python-core.sh --show-local-tts-capability
./scripts/dev/run-python-core.sh --configure-tts-provider local_mlx --clear-tts-local-model-path
```

OpenAI-compatible remote speech path:

```bash
./scripts/dev/run-python-core.sh \
  --configure-tts-provider openai_compatible \
  --tts-base-url "https://api.openai.com/v1" \
  --tts-model "gpt-4o-mini-tts" \
  --tts-api-key "<your-key>" \
  --tts-voice "alloy" \
  --tts-audio-format "wav"
```

## Environment variables

Aodcast does not require a `.env` file for normal development. `.env.example` documents optional helper-script variables such as `AODCAST_HF_MODEL_BASE`, `HF_HUB_CACHE`, and `HF_TOKEN`.
