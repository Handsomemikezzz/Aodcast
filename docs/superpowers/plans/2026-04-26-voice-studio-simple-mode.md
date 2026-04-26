# Voice Studio Simple Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a simple-default Voice Studio flow with global local-model awareness and Models Center default-model selection.

**Architecture:** Reuse the existing `DesktopBridge` methods (`showTTSConfig`, `configureTTSProvider`, `listModelsStatus`, `showLocalTTSCapability`) rather than adding backend routes. Models Center writes global TTS config when a downloaded model is selected. Voice Studio derives an engine summary from TTS config, capability, and model catalog status.

**Tech Stack:** React + TypeScript in `apps/desktop`, Python HTTP runtime already covered by bridge parity tests, Markdown docs.

---

### Task 1: Models Center global default selection

**Files:**
- Modify: `apps/desktop/src/pages/ModelsPage.tsx`

- [ ] Load TTS config alongside model/storage status.
- [ ] Derive whether each catalog row is the global current local model by comparing `tts.provider === "local_mlx"`, no custom `local_model_path`, and `tts.model === model.hf_repo_id`.
- [ ] Add `Use as default` for downloaded non-current rows.
- [ ] On click, call `configureTTSProvider({ provider: "local_mlx", model: model.hf_repo_id, local_model_path: "", audio_format: currentAudioFormat })` and refresh.
- [ ] Replace ambiguous `Loaded` badge with `Current` or `Installed`.

### Task 2: Voice Studio current engine strip

**Files:**
- Modify: `apps/desktop/src/pages/VoiceStudioPage.tsx`

- [ ] Load TTS config, model catalog, and local capability during initial page load.
- [ ] Compute current engine label and status.
- [ ] Show a top status strip with `Current engine`, model display name, status, and `Change model`.
- [ ] If Local MLX is selected but not installed/available, disable full render and show `Open Models` CTA.

### Task 3: Simple-default presentation

**Files:**
- Modify: `apps/desktop/src/pages/VoiceStudioPage.tsx`

- [ ] Add a compact voice recipe summary above Advanced controls.
- [ ] Keep existing voice/style/speed/preview controls in Advanced, collapsed by default.
- [ ] Preserve existing preview/render/take behavior.
- [ ] Add model name to take card metadata when available.

### Task 4: Verification and docs

**Files:**
- Modify: `docs/product/product-overview.md`
- Modify: `docs/architecture/desktop-editing-flow.md`

- [ ] Document that Models Center owns global local model selection.
- [ ] Document that Voice Studio defaults to simple mode and shows current engine status.
- [ ] Run `pnpm --dir apps/desktop check`.
- [ ] Run Python bridge/model tests.
