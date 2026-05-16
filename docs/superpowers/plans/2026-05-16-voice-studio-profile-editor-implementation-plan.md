# Voice Studio Profile Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-scope Voice Studio into a reusable voice-profile editor/library and keep final podcast generation plus final-audio management in Script Workbench.

**Architecture:** The backend profile-first contracts already exist: `selectVoiceProfile` writes script-scoped `artifact.voice_reference`, `renderVoicePreview` can preview a selected profile, and `renderAudio` generates final script audio. The implementation should mostly simplify the desktop UI: Voice Studio keeps profile selection/creation/preview, while Script Workbench shows the selected profile and owns generate/play/delete/download/reveal actions.

**Tech Stack:** React 18, TypeScript, Vite, Tauri desktop bridge, existing HTTP bridge contracts, local MLX/Qwen profile conditioning.

---

## File Structure

- Modify: `apps/desktop/src/pages/VoiceStudioPage.tsx`
  - Remove full podcast generation, cancellation, historical take controls, session/script dropdown selectors, and provider/output advanced render controls from the primary UI.
  - Keep dual-mode behavior: script-bound mode applies a profile to the current script; global mode manages the voice library only.
- Modify: `apps/desktop/src/pages/script-workbench/ScriptAudioSidebar.tsx`
  - Show the selected voice profile as the current voice asset.
  - Change the "Manage" action to "Change voice" and route to script-bound Voice Studio.
  - Keep final audio playback/delete/download/reveal in this sidebar.
- Modify: `apps/desktop/src/pages/script-workbench/ScriptWorkbenchHeader.tsx`
  - Make the generate button copy/state align with profile-first rendering.
- Modify: `apps/desktop/src/pages/script-workbench/useScriptWorkbenchAudio.ts`
  - Improve the no-profile Local MLX error message so the next action is explicit.
- Modify: `apps/desktop/src/lib/voiceSettings.ts`
  - Add a small helper for resolving the selected `VoiceProfileRecord`/display name from `artifact.voice_reference` without duplicating logic in components.
- Modify: `docs/product/product-overview.md`
  - Sync the product-facing source of truth with the approved design.
- Verify only: `services/python-core/tests/test_audio_rendering.py`
  - Existing backend tests already cover profile preview/full-render parity and generated audio deletion; do not change backend unless a UI implementation exposes a real API gap.

---

## Task 1: Add Voice Profile Display Helper

**Files:**
- Modify: `apps/desktop/src/lib/voiceSettings.ts`

- [ ] **Step 1: Add imports and helper functions**

Replace the first line:

```ts
import type { SessionProject, VoiceRenderSettings } from "../types";
```

with:

```ts
import type { SessionProject, VoiceProfileRecord, VoiceRenderSettings } from "../types";
```

Append these helpers to the end of the file:

```ts
export function selectedVoiceProfileId(project: SessionProject | null | undefined): string {
  const reference = project?.artifact?.voice_reference;
  return reference?.source === "voice_profile" ? reference.voice_profile_id ?? "" : "";
}

export function resolveSelectedVoiceProfile(
  project: SessionProject | null | undefined,
  profiles: VoiceProfileRecord[],
): VoiceProfileRecord | null {
  const profileId = selectedVoiceProfileId(project);
  if (!profileId) return null;
  return profiles.find((profile) => profile.voice_profile_id === profileId) ?? null;
}

export function selectedVoiceProfileLabel(project: SessionProject | null | undefined): string {
  const reference = project?.artifact?.voice_reference;
  if (reference?.source === "voice_profile" && reference.voice_profile_id) {
    return String(reference.name || reference.voice_profile_id);
  }
  return "";
}
```

- [ ] **Step 2: Run typecheck**

Run:

```bash
pnpm --dir apps/desktop check
```

Expected: it may fail until later tasks use the helper correctly, but there should be no syntax error in `voiceSettings.ts`.

- [ ] **Step 3: Commit**

```bash
git add apps/desktop/src/lib/voiceSettings.ts
git commit -m "Add selected voice profile helpers" -m "Constraint: Voice Studio and Script Workbench both need to read script-scoped voice_reference consistently.
Rejected: Duplicating voice_reference parsing in each component | it increases drift between the two pages.
Confidence: high
Scope-risk: narrow
Tested: pnpm --dir apps/desktop check
Not-tested: browser UI"
```

---

## Task 2: Simplify Voice Studio State And Actions

**Files:**
- Modify: `apps/desktop/src/pages/VoiceStudioPage.tsx`

- [ ] **Step 1: Remove final-audio state and legacy take functions**

Delete these state variables and derived values:

```ts
const [rendering, setRendering] = useState(false);
const [requestState, setRequestState] = useState<RequestState | null>(null);
const takes = project?.artifact?.takes ?? [];
const finalTakeId = project?.artifact?.final_take_id ?? "";
const renderUsesLocalEngine = providerOverride ? providerOverride === "local_mlx" : isLocalEngine;
const renderEngineReady = Boolean(ttsConfig) && (!renderUsesLocalEngine || (localPathConfigured ? localPathReady : Boolean(localCatalogModelInstalled && ttsCapability?.available)));
```

Delete these functions completely:

```ts
function takeStatus(take: AudioTakeRecord, finalTakeId: string): string {
  return take.take_id === finalTakeId ? "最终版本" : "候选版本";
}
```

```ts
const startPolling = (taskId: string) => {
  stopPolling();
  pollingRef.current = window.setInterval(() => {
    void bridge.showTaskState(taskId)
      .then(async (state) => {
        if (!state) return;
        setRequestState(state);
        if (isTerminalRequestState(state)) {
          stopPolling();
          setRendering(false);
          await loadProject(selectedSessionId, selectedScriptId);
        } else if (isActiveRequestState(state)) {
          setRendering(true);
        }
      })
      .catch((err) => setError(getErrorMessage(err, "Lost connection to rendering runtime.")));
  }, POLL_INTERVAL_MS);
};
```

```ts
const handleRenderTake = async () => {
  setError(null);
  setMessage(null);
  if (!selectedSessionId || !selectedScriptId) {
    setError("请先选择 Session 和脚本，再生成完整音频。");
    return;
  }
  if (!renderEngineReady) {
    setError("当前本地语音模型尚未准备好。请先在 Models Center 下载或选择可用模型，或在高级设置中临时切换到云端 TTS。");
    return;
  }
  if (!scriptText) {
    setError("当前脚本没有可生成的内容，请先选择包含正文的脚本。");
    return;
  }
  if (!selectedProfileId) {
    setError("请先从音色库选择一个音色，再生成完整音频。");
    return;
  }
  try {
    setRendering(true);
    const result = await bridge.renderAudio(selectedSessionId, {
      providerOverride,
      scriptId: selectedScriptId,
      voiceSettings: settings,
      requireVoiceProfile: renderUsesLocalEngine,
    });
    const state = result.request_state ?? {
      operation: "render_audio",
      phase: "running",
      progress_percent: 5,
      message: "Rendering audio...",
    };
    setRequestState(state);
    setProject(result.project);
    startPolling(result.task_id ?? `render_audio:${selectedSessionId}`);
    setMessage("已开始使用所选音色生成完整音频；完成后会自动成为 Script 页的默认音频。");
  } catch (err) {
    setRendering(false);
    setError(getErrorMessage(err, "Failed to render voice take."));
  }
};
```

```ts
const handleCancel = async () => {
  const state = await bridge.cancelTask(requestState?.task_id ?? `render_audio:${selectedSessionId}`);
  if (state) setRequestState(state);
};
```

```ts
const handleSetFinal = async (take: AudioTakeRecord) => {
  try {
    setError(null);
    const updated = await bridge.setFinalVoiceTake(selectedSessionId, take.take_id);
    setProject(updated);
    setMessage("已设为最终版本，Script 页音频区会显示该 take。");
  } catch (err) {
    setError(getErrorMessage(err, "Failed to set final take."));
  }
};
```

```ts
const handleDeleteTake = async (take: AudioTakeRecord) => {
  try {
    setError(null);
    const updated = await bridge.deleteVoiceTake(selectedSessionId, take.take_id);
    setProject(updated);
    setMessage(take.take_id === finalTakeId ? "最终音频已删除。" : "候选 take 已删除。");
  } catch (err) {
    setError(getErrorMessage(err, "Failed to delete voice take."));
  }
};
```

```ts
const handleDownload = (take: AudioTakeRecord) => {
  const src = resolveAudioFileUrl(take.audio_path);
  const filename = take.audio_path.split("/").pop() || "voice-take.wav";
  const link = document.createElement("a");
  link.href = src;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
};
```

- [ ] **Step 2: Remove unused imports**

Update the first import from `lucide-react` so it contains only icons still used after removing final-audio controls:

```ts
import { CheckCircle2, ChevronDown, Loader2, Mic, RefreshCw, SlidersHorizontal, Trash2, Wand2 } from "lucide-react";
```

Remove unused imports from request-state helpers:

```ts
import { getErrorMessage } from "../lib/requestState";
```

Remove unused type imports:

```ts
  ModelStatus,
  ScriptRecord,
  SessionProject,
  TTSCapability,
  TTSProviderConfig,
  VoicePreset,
  VoiceProfileRecord,
  VoiceRenderSettings,
  VoiceStylePreset,
```

- [ ] **Step 3: Run typecheck and fix only unused-symbol errors from this task**

Run:

```bash
pnpm --dir apps/desktop check
```

Expected: no unused imports or undefined variables from deleted final-audio state/actions.

- [ ] **Step 4: Commit**

```bash
git add apps/desktop/src/pages/VoiceStudioPage.tsx
git commit -m "Remove final audio actions from Voice Studio" -m "Constraint: Voice Studio is now a voice-profile editor/library, not the final-audio workspace.
Rejected: Keeping hidden take and full-render handlers in the page | stale handlers make future UI drift likely.
Confidence: high
Scope-risk: moderate
Tested: pnpm --dir apps/desktop check
Not-tested: browser UI"
```

---

## Task 3: Rebuild Voice Studio UI Around Dual Entry Modes

**Files:**
- Modify: `apps/desktop/src/pages/VoiceStudioPage.tsx`

- [ ] **Step 1: Add explicit mode constants**

After the `selectedSession` constant, add:

```ts
const scriptBoundMode = Boolean(routeSessionId && routeScriptId);
const canApplyProfileToScript = Boolean(selectedSessionId && selectedScriptId);
const scriptTitle = project?.script?.title || selectedSession?.session.topic || "当前脚本";
```

- [ ] **Step 2: Replace the hero copy**

Replace the current hero title/subtitle/button block with:

```tsx
<section className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-5">
  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent-amber">Voice Studio</p>
      <h1 className="mt-2 font-headline text-2xl font-semibold text-primary">音色工坊</h1>
      <p className="mt-2 max-w-2xl text-sm text-secondary">
        {scriptBoundMode
          ? `为「${scriptTitle}」选择或创建一个可复用音色。完整音频生成和成品管理会在 Script 页完成。`
          : "管理可复用音色库。打开某个脚本后，可以把这里的音色应用到那一集播客。"}
      </p>
    </div>
    {scriptBoundMode ? (
      <button
        type="button"
        onClick={() => selectedSessionId && selectedScriptId && navigate(`/script/${selectedSessionId}/${selectedScriptId}`)}
        className="rounded-2xl border border-outline bg-surface-container-low px-4 py-2 text-sm font-medium text-primary hover:bg-surface-container"
      >
        返回 Script
      </button>
    ) : null}
  </div>
</section>
```

- [ ] **Step 3: Remove session/script selectors from the page body**

Delete the entire section headed `脚本选择`. Do not replace it. Script selection happens before entering script-bound Voice Studio; global mode intentionally has no script selector.

- [ ] **Step 4: Update profile card actions**

Inside the voice profile card action area, replace the selection button block with:

```tsx
{scriptBoundMode ? (
  <button
    type="button"
    onClick={() => void handleSelectVoiceProfile(profile)}
    disabled={isSelected}
    className="rounded-xl border border-outline px-3 py-2 text-xs font-medium text-primary disabled:opacity-50"
  >
    {isSelected ? "已用于当前脚本" : "用于当前脚本"}
  </button>
) : (
  <span className="rounded-xl border border-outline px-3 py-2 text-xs text-secondary">
    打开脚本后可选用
  </span>
)}
```

- [ ] **Step 5: Update `handleSelectVoiceProfile` for global mode copy**

Replace the initial guard in `handleSelectVoiceProfile` with:

```ts
if (!canApplyProfileToScript) {
  setError("请先从 Script 页面打开 Voice Studio，再把音色应用到具体脚本。");
  return;
}
```

Replace its success message with:

```ts
setMessage(`已为当前脚本选用「${profile.name}」。返回 Script 页后可以生成完整音频。`);
```

- [ ] **Step 6: Replace Advanced controls with read-only engine context**

Remove the `Advanced voice controls` section. Replace it with a compact engine section:

```tsx
<section className="rounded-[28px] border border-outline bg-[rgba(27,27,30,0.92)] p-5">
  <div className="flex items-start justify-between gap-3">
    <div>
      <h2 className="text-sm font-semibold text-primary">当前语音引擎</h2>
      <p className="mt-1 text-xs text-secondary">{engineLabel}</p>
      <p className={cn("mt-1 text-xs", localEngineReady ? "text-secondary" : "text-amber-200")}>{engineStatus}</p>
    </div>
    <button
      type="button"
      onClick={() => navigate("/models")}
      className="rounded-2xl border border-outline px-3 py-2 text-xs font-medium text-primary hover:bg-surface-container"
    >
      Change model
    </button>
  </div>
</section>
```

- [ ] **Step 7: Remove full-audio and historical take sections**

Delete the sections headed:

```tsx
<h2 className="text-sm font-semibold text-primary">完整音频生成</h2>
```

and:

```tsx
<h2 className="text-sm font-semibold text-primary">历史 take</h2>
```

- [ ] **Step 8: Run typecheck**

Run:

```bash
pnpm --dir apps/desktop check
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/desktop/src/pages/VoiceStudioPage.tsx
git commit -m "Reframe Voice Studio as profile editor" -m "Constraint: User wants Voice Studio to be an音色自定义卡面, not a mixed generation page.
Rejected: Keeping script dropdowns in Voice Studio | it duplicates navigation state and blurs script ownership.
Confidence: high
Scope-risk: moderate
Directive: Do not reintroduce final podcast actions on Voice Studio without a new product decision.
Tested: pnpm --dir apps/desktop check
Not-tested: browser UI"
```

---

## Task 4: Make Script Workbench The Final Audio Workspace

**Files:**
- Modify: `apps/desktop/src/pages/script-workbench/ScriptAudioSidebar.tsx`
- Modify: `apps/desktop/src/pages/script-workbench/ScriptWorkbenchHeader.tsx`
- Modify: `apps/desktop/src/pages/script-workbench/useScriptWorkbenchAudio.ts`

- [ ] **Step 1: Update ScriptAudioSidebar voice card copy**

In `ScriptAudioSidebar.tsx`, replace the import:

```ts
import { resolveProjectVoiceSettings } from "../../lib/voiceSettings";
```

with:

```ts
import { resolveProjectVoiceSettings, selectedVoiceProfileLabel } from "../../lib/voiceSettings";
```

After `const voiceSettings = resolveProjectVoiceSettings(workbench.project);`, add:

```ts
const selectedProfileLabel = selectedVoiceProfileLabel(workbench.project);
const scriptVoiceStudioPath = workbench.project?.script
  ? `/voice-studio/${workbench.project.session.session_id}/${workbench.project.script.script_id}`
  : "/voice-studio";
```

Replace the voice card header label from:

```tsx
<p className="text-xs font-semibold uppercase tracking-[0.18em] text-secondary">Voice Persona</p>
```

to:

```tsx
<p className="text-xs font-semibold uppercase tracking-[0.18em] text-secondary">Selected Voice</p>
```

Replace both current `workbench.navigate("/settings")` handlers in the voice card with:

```tsx
workbench.navigate(scriptVoiceStudioPath)
```

Replace the voice name paragraph with:

```tsx
<p className="text-sm font-medium text-primary">
  {selectedProfileLabel || "未选择音色"}
</p>
```

Replace the voice detail paragraph with:

```tsx
<p className="mt-1 text-xs text-secondary">
  {selectedProfileLabel
    ? `${voiceSettings.language || "zh"} · ${workbench.selectedEngine === "local_mlx" ? "Local MLX" : workbench.cloudProvider}`
    : "选择音色后，Script 页会用它生成完整音频。"}
</p>
```

Change the button label from:

```tsx
Open Voice Studio
```

to:

```tsx
Change voice
```

- [ ] **Step 2: Update generated audio section copy**

Replace:

```tsx
<p className="mt-1 text-xs text-secondary">Preview, export, or share the latest render.</p>
```

with:

```tsx
<p className="mt-1 text-xs text-secondary">Play, delete, download, or reveal the final render for this script.</p>
```

Replace the empty-state paragraph with:

```tsx
<p className="mt-2 max-w-[280px] text-xs leading-6 text-secondary">
  Choose a voice profile, save your latest edits, then generate the final audio from this Script page.
</p>
```

- [ ] **Step 3: Update header generate button copy**

In `ScriptWorkbenchHeader.tsx`, replace:

```tsx
{workbench.generating ? "Generating..." : "Generate Audio"}
```

with:

```tsx
{workbench.generating ? "Generating..." : "Generate final audio"}
```

- [ ] **Step 4: Improve no-profile error**

In `useScriptWorkbenchAudio.ts`, replace:

```ts
setAudioError("请先在 Voice Studio 选择一个音色，再使用 Local MLX 生成音频。");
```

with:

```ts
setAudioError("请先在 Voice Studio 为当前脚本选择一个音色，然后回到 Script 页生成完整音频。");
```

- [ ] **Step 5: Run typecheck**

Run:

```bash
pnpm --dir apps/desktop check
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/pages/script-workbench/ScriptAudioSidebar.tsx apps/desktop/src/pages/script-workbench/ScriptWorkbenchHeader.tsx apps/desktop/src/pages/script-workbench/useScriptWorkbenchAudio.ts
git commit -m "Make Script Workbench own final audio flow" -m "Constraint: Final podcast artifacts are script-owned and should be played/deleted/downloaded from Script Workbench.
Rejected: Mirroring final-audio controls in Voice Studio | duplicate controls create inconsistent ownership.
Confidence: high
Scope-risk: moderate
Tested: pnpm --dir apps/desktop check
Not-tested: browser UI"
```

---

## Task 5: Sync Product Docs And Run Regression Checks

**Files:**
- Modify: `docs/product/product-overview.md`

- [ ] **Step 1: Update Voice Studio and Script handoff bullets**

Replace the current Voice Studio, Script handoff, and UI bullets with:

```md
- **Voice Studio**: `/voice-studio` is the global reusable voice library, and `/voice-studio/:sessionId/:scriptId` is the script-bound voice selection entry point. Voice Studio creates, previews, deletes, and selects voice profiles. It does not generate or manage final podcast audio.
- **Script handoff**: Selecting a profile from script-bound Voice Studio writes the current script's `artifact.voice_reference` with `source: "voice_profile"` and `voice_profile_id`. Script Workbench then uses that profile for final podcast rendering.
- **UI**: The script route focuses on editing and final-audio production/review; Voice Studio owns voice-profile selection, reference-audio preview, and profile creation.
```

- [ ] **Step 2: Update audio-rendering docs only if implementation changed runtime behavior**

If no backend/runtime behavior changed, do not edit `docs/architecture/audio-rendering.md`. The existing architecture doc already states Script Workbench exposes deletion for generated audio and that profile-first render uses `selectVoiceProfile -> renderVoicePreview -> renderAudio`.

- [ ] **Step 3: Run frontend typecheck**

```bash
pnpm --dir apps/desktop check
```

Expected: PASS.

- [ ] **Step 4: Run backend profile/audio regression tests**

```bash
cd services/python-core
PYTHONPATH=. .venv/bin/python -m unittest tests.test_audio_rendering tests.test_bridge_request_state_schema
```

Expected: PASS.

- [ ] **Step 5: Run web build**

```bash
pnpm --dir apps/desktop build:web
```

Expected: PASS. If dependency installation is missing, stop and report the missing package-manager state instead of changing lockfiles.

- [ ] **Step 6: Manual browser check**

Start the desktop web app:

```bash
pnpm --dir apps/desktop dev:web -- --host 127.0.0.1
```

Open the printed local URL and check:

- `/voice-studio` shows the global library, no script selector, no full-audio generation, no historical take section.
- `/voice-studio/:sessionId/:scriptId` shows script-bound copy and `用于当前脚本` actions.
- Selecting a profile updates the current script and lets the user return to Script.
- Script Workbench shows the selected voice profile and still exposes final audio generation/playback/delete/download/reveal.

- [ ] **Step 7: Commit**

```bash
git add docs/product/product-overview.md
git commit -m "Document Voice Studio profile-editor boundary" -m "Constraint: Product docs must match the approved Voice Studio/Profile-first design.
Rejected: Leaving old Voice Studio generation wording | future work would follow stale ownership boundaries.
Confidence: high
Scope-risk: narrow
Tested: pnpm --dir apps/desktop check; PYTHONPATH=. .venv/bin/python -m unittest tests.test_audio_rendering tests.test_bridge_request_state_schema; pnpm --dir apps/desktop build:web
Not-tested: packaged Tauri build"
```

---

## Final Verification

- [ ] Run:

```bash
git status --short
```

Expected: only intentional tracked changes remain, with no debug artifacts.

- [ ] Run:

```bash
pnpm --dir apps/desktop check
pnpm --dir apps/desktop build:web
cd services/python-core
PYTHONPATH=. .venv/bin/python -m unittest tests.test_audio_rendering tests.test_bridge_request_state_schema
```

Expected: all commands pass.

- [ ] Confirm the old Voice Studio production controls are absent:

```bash
rg -n "完整音频生成|历史 take|renderVoiceTake|setFinalVoiceTake|deleteVoiceTake|handleRenderTake|handleSetFinal|handleDeleteTake" apps/desktop/src/pages/VoiceStudioPage.tsx
```

Expected: no matches.

- [ ] Confirm Script Workbench still owns final audio controls:

```bash
rg -n "Generate final audio|handleDeleteAudio|handleDownloadAudio|handleRevealInFinder|deleteGeneratedAudio" apps/desktop/src/pages/script-workbench apps/desktop/src/lib/desktopBridge.ts
```

Expected: matches in Script Workbench/header/sidebar/audio hook and bridge contract.

---

## Self-Review

- Spec coverage: The plan covers dual Voice Studio entry modes, removing final-audio actions from Voice Studio, keeping profile creation/preview/selection, moving final-audio management to Script Workbench, and syncing product docs.
- Placeholder scan: No `TODO`, `TBD`, or undefined implementation placeholders are used.
- Type consistency: Existing bridge methods are reused; no backend API additions are required for this UI re-scope.
