# Script Generation

## Purpose

This document describes the current Milestone 3 script generation flow.

## Flow

The Python core now supports a draft-generation path after the interview reaches `ready_to_generate`.

1. Load the persisted session project.
2. Check LLM configuration readiness through the shared preflight contract when the request comes from the desktop shell.
3. Load the active LLM configuration from local config storage.
4. Build a provider adapter from the configured provider name.
5. Generate a draft from the transcript.
6. Persist the draft and transition the session to `script_generated`.

## Provider Layer

Current LLM providers:

- `mock`: deterministic local provider used for bootstrap and tests
- `openai_compatible`: configurable adapter for remote chat-completions style APIs

## Local Configuration

The active LLM configuration is stored under:

```text
.local-data/
└── config/
    └── llm.json
```

The config contains:

- provider
- model
- base_url
- api_key

The same readiness rules are exposed through `--check-llm-config` and `GET /api/v1/config/llm/preflight`. Chat and script-generation UI should display that preflight result instead of duplicating provider-specific validation rules in React components.

## Failure Behavior

- generation failures preserve transcript and script records
- session state moves to `failed`
- the error message is stored in `session.last_error`
- failed sessions can be retried through the same generation path after configuration is fixed
