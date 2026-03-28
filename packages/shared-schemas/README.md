# Shared Schemas

These files define the cross-boundary contracts between the desktop shell and the Python orchestration core.

Current MVP contracts:

- `session.schema.json`
- `transcript.schema.json`
- `script.schema.json`
- `artifact.schema.json`

Rules:

- update schemas before cross-boundary implementation changes
- keep state values aligned with the source-of-truth spec and Python domain models
- treat schema edits as coordination points for multi-agent work
