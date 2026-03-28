# Interview Orchestration

## Purpose

This document describes the current Milestone 2 orchestration shape for the interview phase.

## Flow

The Python orchestration core currently supports four interview actions:

- start interview
- submit user response
- evaluate readiness
- request finish

## State Behavior

- `start_interview` moves a new session into `interview_in_progress` and appends the first agent question.
- `submit_user_response` appends the user turn, evaluates readiness, and either:
  - returns to `interview_in_progress` with the next agent question, or
  - moves the session to `ready_to_generate`
- `request_finish` moves the session to `ready_to_generate` even if readiness is incomplete.

## Readiness Heuristic

The current heuristic checks for four dimensions:

- topic context
- core viewpoint
- example or detail
- conclusion

This is a deterministic baseline for the MVP bootstrap phase. It exists to define orchestration boundaries before real provider-backed prompting is added.

## Prompt Input Shape

The orchestration layer assembles a reusable prompt input object containing:

- topic
- creation intent
- session state
- turn count
- missing readiness dimensions
- role, goal, strategy, and boundary instructions

This object is the planned handoff shape for future LLM-backed question generation.
