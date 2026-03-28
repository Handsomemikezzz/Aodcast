# EchoMind Podcast MVP Design

## 1. Objective

EchoMind Podcast is an open source, local-first macOS desktop application for turning user thoughts into publishable podcast content through AI-guided interviewing.

The MVP is designed to validate one narrow product claim:

`AI can turn a loosely formed topic into a usable solo podcast script and final audio through guided interviewing.`

## 2. MVP Scope

### In Scope

- macOS desktop application
- Tauri-based frontend shell
- local Python orchestration core
- text topic input
- AI-guided interview workflow
- solo monologue podcast script generation
- direct user editing of generated script
- final audio rendering through:
  - remote TTS API provider
  - local MLX-backed TTS provider
- local project persistence and recovery

### Out of Scope

- speech input or STT
- long-term memory or user profile learning
- multi-speaker podcast formats
- AI conversational rewrite loop after script generation
- cloud-hosted orchestration backend
- voice cloning
- Windows support in the initial release

## 3. Core Product Flow

The MVP follows a linear creation loop:

1. User enters a topic and creation intent.
2. The interview agent asks targeted follow-up questions.
3. The system evaluates whether enough material has been gathered.
4. The user can end the interview at any time, and the AI can also suggest ending.
5. The system generates a solo podcast draft.
6. The user edits the script directly.
7. The system renders final audio and exports the final transcript.

The product deliberately avoids interview-state rollback during the MVP. Users do not edit past answers during the interview. Edits happen only after script generation.

## 4. State Machine

### Primary States

- `topic_defined`
- `interview_in_progress`
- `readiness_evaluation`
- `ready_to_generate`
- `script_generated`
- `script_edited`
- `audio_rendering`
- `completed`
- `failed`

### Transition Logic

`topic_defined -> interview_in_progress`
Triggered after the user starts a new session.

`interview_in_progress -> readiness_evaluation`
Triggered after each user response.

`readiness_evaluation -> interview_in_progress`
Used when the material still lacks one or more of:

- a clear core viewpoint
- concrete detail or example
- causal logic between ideas
- a usable conclusion or takeaway

`readiness_evaluation -> ready_to_generate`
Used when the material is sufficient to support a coherent solo script.

`interview_in_progress -> ready_to_generate`
Can also be triggered directly by explicit user intent to stop the interview.

`ready_to_generate -> script_generated`
Triggered when the orchestration core completes the first script draft.

`script_generated -> script_edited`
Triggered after the user saves direct edits to the draft.

`script_edited -> audio_rendering`
Triggered when the user selects a TTS provider and starts audio generation.

`audio_rendering -> completed`
Triggered when the final transcript and audio artifacts are persisted.

### MVP State Constraints

- Interview mode is linear.
- No editing or replay of previous answers during the interview.
- Script edits do not return the session to interview mode.
- Failures must preserve the current session data and allow retry.

## 5. Interview Agent Design

The interview agent is not a general-purpose assistant. It is a focused content interviewer whose job is to gather enough structured material to generate a compelling solo podcast draft.

### Prompt Framework

#### Role Layer

The agent behaves as a perceptive podcast interviewer who clarifies thinking and exposes gaps in logic.

#### Goal Layer

The agent must gather enough material to produce a script with:

- a clear opening hook
- a coherent progression of ideas
- supporting detail or example
- a usable conclusion

#### Strategy Layer

The agent should probe for five categories of information:

- topic background
- core point of view
- examples or details
- emotional stance or intensity
- conclusion, recommendation, or takeaway

It should ask one high-value follow-up at a time.

#### Boundary Layer

The agent must not:

- invent user experiences
- ask several unrelated questions at once
- switch into long-form script writing before readiness is met
- end the interview while key information is still missing

### Readiness Heuristic

The orchestration core should maintain a simple completion model that checks whether the conversation has enough material to generate a solid solo episode. The default readiness criteria are:

- topic context is understandable
- at least one core judgment or thesis is explicit
- at least one concrete example or detail exists
- a usable ending or summary is available

When these are mostly satisfied, the AI may suggest ending the interview. The user may still end the interview manually at any time.

## 6. Architecture

The recommended MVP architecture is a local-first desktop stack built around a strict separation of concerns.

### Layer 1: Tauri App Shell

Responsibilities:

- screens and navigation
- session creation and project browsing
- configuration UI
- script editing UI
- local file import and export
- surfacing task status and failure states

The frontend should not contain interview orchestration rules or provider-specific business logic.

### Layer 2: Python Orchestration Core

Responsibilities:

- interview state management
- readiness evaluation
- prompt assembly
- script generation workflow
- provider dispatch
- retry handling
- artifact persistence
- recovery from interrupted tasks

This is the core business layer and should expose a stable interface to the desktop shell.

### Layer 3: Provider Adapters

The orchestration core should integrate all model and audio services through replaceable adapters:

- `LLMProvider`
- `TTSApiProvider`
- `LocalTTSProvider`

The local provider for the first release targets macOS through MLX-backed model execution.

### Layer 4: Local Storage

The project should persist session state and generated outputs locally so that interruptions do not destroy user work.

## 7. Data Model

The MVP needs four primary data objects.

### Session

Represents one podcast creation run.

Fields should include:

- session id
- current state
- creation timestamps
- selected providers
- output preferences

### Transcript

Stores the interview question and answer history used as source material for generation.

### Script

Stores both:

- AI-generated draft
- user-edited final text

### Artifact

Stores generated deliverables and metadata:

- final transcript
- audio file path
- provider metadata
- generation timestamps

## 8. End-to-End Data Flow

1. The user creates a session from a text topic.
2. The Python core initializes interview state.
3. Each interview turn is appended to the transcript.
4. The readiness evaluator determines whether to continue asking questions or allow generation.
5. The LLM provider generates a structured solo podcast draft from the interview transcript.
6. The user edits the draft in the desktop app.
7. The final script is submitted to the selected TTS provider.
8. The audio output and final text are saved as project artifacts.
9. The session remains recoverable for later viewing or re-rendering.

## 9. Repository Layout

The repository should be organized for multi-agent work from day one.

```text
Aodcast/
├── AGENTS.md
├── docs/
│   ├── product/
│   ├── architecture/
│   ├── operations/
│   └── superpowers/specs/
├── apps/
│   └── desktop/
├── services/
│   └── python-core/
├── packages/
│   └── shared-schemas/
├── scripts/
│   ├── dev/
│   ├── maintenance/
│   └── release/
├── .agent/
│   ├── prompts/
│   ├── checklists/
│   ├── task-templates/
│   └── reports/
└── examples/
```

### Layout Rationale

- `apps/desktop` isolates the Tauri app shell.
- `services/python-core` isolates orchestration and provider logic.
- `packages/shared-schemas` holds shared contracts so multi-agent edits do not drift.
- `docs/operations` contains long-lived repo governance instead of scattering process rules.
- `.agent` keeps reusable agent assets separate from product documentation.

## 10. Agent Governance Model

This project is expected to be maintained by multiple agents over time. Governance must therefore be treated as part of the system design.

### Root Rule File

`AGENTS.md` is a living repository contract. It must evolve as the architecture, workflow, and collaboration model change. Agents must treat changes to repo structure, shared contracts, or maintenance policy as reasons to update `AGENTS.md`.

### Core Collaboration Rules

- work within owned directory boundaries whenever possible
- update shared contracts before cross-boundary implementation
- keep provider-specific code isolated
- keep docs current in the same change set as behavior changes
- prefer small, replaceable modules over large multi-purpose files

## 11. Maintenance Subagents

To prevent agent-managed entropy, the repository should define dedicated maintenance roles.

### `spec-keeper`

Checks whether product, architecture, and governance docs still match implementation and repo structure.

### `code-pruner`

Identifies dead code, duplicated logic, oversized files, stale scripts, and cleanup candidates.

### `contract-guard`

Checks schema drift and frontend/backend contract mismatches.

### `doc-syncer`

Updates README, ops docs, examples, and usage docs when implementation changes invalidate them.

### `repo-curator`

Checks whether the repository structure is degrading through temporary files, misplaced assets, or unmanaged operational sprawl.

These subagents are maintenance roles, not feature-delivery roles.

## 12. Maintenance Triggers

The project should support two maintenance modes.

### Event-Driven

Run relevant maintenance subagents when:

- repo structure changes
- provider interfaces change
- shared schema changes
- core product flow changes
- governance rules change

### Periodic

Run repository hygiene passes on a schedule to:

- remove stale implementation leftovers
- detect drift between docs and code
- refresh governance docs
- keep examples and scripts current

## 13. Failure Handling

The MVP should preserve user work across failures.

Required failure behavior:

- if LLM generation fails, keep the session and transcript recoverable
- if TTS rendering fails, keep the final script and allow provider switch or retry
- if the local TTS provider is unavailable, show a recoverable failure and allow fallback to a remote provider
- if the app closes mid-session, reload the latest persisted state on next launch

## 14. Testing Expectations

Even before full implementation, the architecture should assume tests around:

- interview state transitions
- readiness evaluation rules
- provider adapter boundaries
- persistence and recovery behavior
- schema compatibility between frontend and backend

The first implementation plan should treat orchestration tests and persistence tests as non-optional because those are the highest-risk parts of the MVP.

## 15. Acceptance Criteria for the MVP

The MVP is successful when a user can:

1. start a session from a text topic
2. complete an AI-guided interview
3. receive a usable solo podcast draft
4. edit the draft directly
5. generate audio through either a remote TTS API or a local MLX-backed provider
6. reopen the project without losing the session transcript or generated assets

