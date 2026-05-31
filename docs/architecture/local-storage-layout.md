# Local Storage Layout

## Purpose

This document describes the current file-backed storage shape used by the Python orchestration core.

## Root

Local project data is written under:

```text
.local-data/
└── sessions/
    └── <session-id>/
        ├── session.json
        ├── transcript.json
        ├── scripts/
        │   └── <script-id>.json
        └── artifact.json
```

## File Roles

- `session.json`: session metadata and current state
- `transcript.json`: interview turns
- `scripts/<script-id>.json`: generated draft, edited final script, soft-delete state, and revisions
- `artifact.json`: output metadata such as transcript/audio paths, per-script artifact payloads, voice settings, voice references, and legacy takes

## Current Notes

- The storage layout is local-first and file-based.
- Recovery loads a full project by rebuilding these records from the session directory.
- Older single-file `script.json` records are migrated into `scripts/<script-id>.json` by `ProjectStore` when scripts are listed or loaded.
