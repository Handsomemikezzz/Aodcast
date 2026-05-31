# Interview Orchestration

## Purpose

This document describes the current orchestration shape for the interview phase.

## Flow

The Python orchestration core currently supports four interview actions:

- start interview
- submit user response
- evaluate readiness
- request finish

Desktop trigger:
- The Chat page provides a manual **“生成脚本”** action.
- Trigger path: `request_finish` -> `generateScript` -> open Script page.
- Each generation creates a new script snapshot.

## State Behavior

- `start_interview` moves a new session into `interview_in_progress` and appends the first agent question.
- `submit_user_response` appends the user turn, evaluates readiness, and returns to `interview_in_progress` with the next agent question.
- Readiness (`is_ready`) is exposed as a signal (`ai_can_finish`) but does not auto-end the conversation.
- `request_finish` moves the session to `ready_to_generate` even if readiness is incomplete.

## Readiness Heuristic

The current heuristic checks for four dimensions:

- topic context
- core viewpoint
- example or detail
- conclusion

This deterministic check drives the `ai_can_finish` signal. Question generation can use the configured LLM provider, with mock fallback behavior kept inside the Python provider layer.

## Prompt Input Shape

The orchestration layer assembles a reusable prompt input object containing:

- topic
- creation intent
- session state
- turn count
- missing readiness dimensions
- role, goal, strategy, and boundary instructions

LLM-backed interview question generation consumes this prompt input through the provider adapter.
