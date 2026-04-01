# Local Storage Layout

## Purpose

This document describes the current Milestone 1 storage shape used by the Python orchestration core.

## Root

Local project data is written under:

```text
.local-data/
└── sessions/
    └── <session-id>/
        ├── session.json
        ├── transcript.json
        ├── script.json
        └── artifact.json
```

## File Roles

- `session.json`: session metadata and current state
- `transcript.json`: interview turns
- `script.json`: generated draft and user-edited final script
- `artifact.json`: output metadata such as transcript and audio paths

## Current Notes

- The storage layout is local-first and file-based.
- Recovery loads a full project by rebuilding these records from the session directory.
- This layout is intentionally simple for the MVP and may evolve with future contract/versioning needs.
