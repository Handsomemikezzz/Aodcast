# Shared Schemas

These files define the cross-boundary contracts between the desktop shell and the Python orchestration core.

Current MVP contracts:

- `session.schema.json`
- `episode-source.schema.json`
- `transcript.schema.json`
- `script.schema.json`
- `speech-plan.schema.json`
- `artifact.schema.json`
- `render-manifest.schema.json`
- `speaker-reference.schema.json`
- `tts-model-capability.schema.json`
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
