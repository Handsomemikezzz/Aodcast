# Multi-Agent Workflow

## Goal

This document defines how to break Aodcast work into parallelizable tasks without creating contract drift or repository sprawl.

## Working Model

Use one lead agent to coordinate planning and integration. Use bounded subagents for implementation and hygiene.

### Lead Agent Responsibilities

- choose the active source-of-truth doc
- break work into dependency-aware tasks
- assign one owned area per subagent
- merge schema and governance changes before dependent implementation
- trigger maintenance agents after structural changes

### Default Delivery Sequence

1. `schema-steward`
Define or update shared data contracts first.
2. `orchestration-builder`
Implement backend state and workflow around the agreed contracts.
3. `provider-integrator`
Add or update LLM and TTS adapters behind stable interfaces.
4. `desktop-builder`
Connect the UI to the stable backend and contracts.
5. `quality-runner`
Validate the critical user path and high-risk failure cases.
6. maintenance roles
Run targeted cleanup and doc-sync passes before closing the milestone.

## Parallelization Rules

Safe to run in parallel:

- frontend implementation and provider adapter work after schemas stabilize
- docs refresh and code cleanup after feature merge
- test writing alongside implementation when contracts are fixed

Do not run in parallel:

- schema changes and dependent implementation
- governance changes and repository restructuring without a single coordinator
- multiple agents editing the same orchestration or provider files without explicit split

## Required Outputs Per Milestone

- updated contracts if boundaries changed
- implementation changes in the owned directories
- updated docs for any behavior or workflow changes
- a short maintenance pass if the milestone affects repo structure or shared interfaces

