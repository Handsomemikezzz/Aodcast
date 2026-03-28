# Maintenance Playbook

## Goal

This playbook defines when to run maintenance-oriented subagents to keep Aodcast manageable under long-term agent collaboration.

## Event-Driven Triggers

Run one or more maintenance subagents when:

- a new provider is added
- repository directories are added, moved, or repurposed
- shared schemas change
- the session state machine changes
- AGENTS.md changes
- user-facing behavior changes without matching doc updates

## Periodic Triggers

Suggested cadence:

- weekly: `doc-syncer` and `repo-curator`
- biweekly: `contract-guard`
- monthly: `spec-keeper` and `code-pruner`

These are defaults and should be revised as the repository grows.

## Maintenance Output Rules

Maintenance runs should produce:

- a short report in `.agent/reports/`
- proposed doc updates when drift is found
- narrowly scoped cleanup changes instead of broad rewrite sweeps

## Cleanup Guardrails

- do not remove files without confirming they are unused or superseded
- do not rewrite governance docs without checking current architecture docs
- prefer incremental cleanup over large disruptive refactors

