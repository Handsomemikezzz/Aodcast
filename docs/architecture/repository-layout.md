# Repository Layout

## Current Layout

This repository is intentionally structured for local-first desktop development and long-term multi-agent maintenance.

- `apps/desktop`: Tauri app shell
- `services/python-core`: orchestration core and provider adapters
- `packages/shared-schemas`: shared contracts
- `docs/operations`: governance and maintenance docs
- `.agent`: reusable agent prompts, checklists, templates, and reports

## Design Intent

- isolate UI from orchestration
- isolate provider implementations from business flow
- isolate governance docs from product docs
- make cross-agent boundaries obvious

