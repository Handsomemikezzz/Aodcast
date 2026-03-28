# Milestone 7 Hardening Pass

## Scope

- local MLX TTS follow-through after Milestone 6
- maintenance script bootstrap
- regression and hygiene validation

## Roles Simulated

- `quality-runner`
- `doc-syncer`
- `repo-curator`
- `spec-keeper`

## Findings

- Local MLX provider flow is functionally wired and now validated through both success and failure paths.
- The repository needed a single repeatable hygiene command instead of relying on ad hoc terminal history.
- Git commit operations may require escalation in this environment because `.git/index.lock` writes are sandbox-restricted.

## Actions Taken

- added local MLX capability success coverage
- added audio rendering regression coverage for draft fallback behavior
- added `scripts/maintenance/run-repo-hygiene-check.sh`
- synced README and maintenance playbook with the maintenance workflow
- updated `AGENTS.md` with the git commit sandbox note

## Validation

- `python3 -m unittest discover -s tests -v`
- `pnpm check`
- `pnpm build:web`
- placeholder scan across docs and source trees

## Follow-Up

- Keep using project-local `.venv` as the source of truth for MLX checks on macOS.
- Replace the placeholder local model path once the real MLX speech-model contract is chosen.
