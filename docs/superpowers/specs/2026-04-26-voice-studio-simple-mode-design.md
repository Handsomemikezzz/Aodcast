# Voice Studio Simple Mode Design

## Goal

Make Voice Studio feel like a guided audio-production workspace: simple by default, professional controls available on demand, and always clear about the global model/engine currently used for generation.

## Product boundaries

- Models Center owns local model download, storage, deletion, and global local-model selection.
- Settings owns provider credentials and advanced connection fields.
- Voice Studio owns voice design, preview, full-audio rendering, and final take selection.

## User experience

Voice Studio starts in simple mode. The user should immediately see:

1. current script summary
2. current engine/model status
3. current voice recipe summary
4. preview action
5. generate final audio action
6. final/candidate takes

Advanced voice controls stay collapsed by default and expose voice presets, style, speed, language, output format, preview text, and provider override.

## Phase 1 scope

- Show current global engine/model at the top of Voice Studio.
- Add `Change model` navigation to Models Center.
- Disable or redirect generation when Local MLX is selected but no installed matching model is ready.
- Let Models Center set a downloaded model as the global default local model.
- Rename model states so users see `Current`, `Installed`, `Downloading`, or `Needs download` instead of ambiguous `Loaded`.
- Keep advanced parameters available but visually subordinate to the default flow.

## Acceptance criteria

- From Models Center, a downloaded Qwen TTS model can be selected as the global default.
- Voice Studio reflects that global selection without raw model editing.
- If the global engine is Local MLX and its model is not installed/available, Voice Studio shows an actionable Models Center CTA.
- A user can still preview, render, set final take, reveal, and download takes as before.
- Existing bridge parity and request-state tests continue to pass.
