# Shared Schemas

These files define the cross-boundary contracts between the desktop shell and the Python orchestration core.

Current cross-boundary contracts:

- `session.schema.json`
- `episode-source.schema.json`
- `transcript.schema.json`
- `attachment.schema.json`
- `script.schema.json`
- `speech-plan.schema.json`
- `artifact.schema.json`
- `render-manifest.schema.json`
- `speaker-reference.schema.json`
- `tts-model-capability.schema.json`
- `tts-provider-config.schema.json`
- `llm-provider-config.schema.json`
- `llm-provider-status.schema.json`
- `llm-auth-start.schema.json`
- `bridge-request-state.schema.json`
- `memory-entry.schema.json`
- `memory-state.schema.json`
- `memory-usage-event.schema.json`

Rules:

- update schemas before cross-boundary implementation changes
- keep state values aligned with the source-of-truth spec and Python domain models
- keep `SpeakerReference` provider-neutral; model and delivery controls belong to render and speech-plan contracts
- use `native`, `approximated`, or `unsupported` model capability levels instead of silently dropping speech-plan controls
- treat schema edits as coordination points for multi-agent work

`TTSProviderConfig` selects `local_http` (default `http://127.0.0.1:8090/v1`) or `openai_compatible`. Model loading, downloads, and weight paths belong to the bundled `speech-service` HTTP process and its isolated Python 3.12 environment. Its source lives in this repository; the orchestration core only uses HTTP. Local service requests produce WAV at normal speed without style instructions. Preset models speak built-in voices; the Qwen3 TTS Base models (`0.6B-Base-8bit` default, `1.7B-Base-8bit`) zero-shot clone a `SpeakerReference` from its audio and exact `reference_text`, report `speaker_cloning: native`, and declare the service's `max_reference_duration_ms`. Every segment is conditioned on the same reference; preceding-audio continuity (`audio_context`) stays unsupported.

`Attachment` is a chat attachment on a user transcript turn: an immutable content-hashed blob under its session. Images go to the model as image input; documents (text, Markdown, CSV, JSON, PDF) go as backend-extracted text. A provider or model that cannot accept image input must fail explicitly instead of dropping it. Attachments are never long-term memory sources.
