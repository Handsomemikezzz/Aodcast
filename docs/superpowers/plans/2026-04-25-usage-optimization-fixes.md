# Usage Optimization Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 修复 `docs-local/202604252337优化.md` 中经代码核查确认存在或部分存在的体验问题，并把音频格式相关范围拆成可验证的小里程碑。

**Architecture:** 前端先修复导航、空状态和 Voice Studio 试音输入；后端扩展 `VoiceRenderSettings` 的预览文本并保持默认回退；音频格式策略先做“心智一致 + MIME/文案/测试”小闭环，不在本计划中引入 ffmpeg 或新增重型依赖。

**Tech Stack:** React + React Router + TypeScript (`apps/desktop`), Python unittest HTTP runtime/orchestration (`services/python-core`), shared JSON schemas (`packages/shared-schemas`).

---

## 核查结论

| ID | 判断 | 证据摘要 | 处理策略 |
| --- | --- | --- | --- |
| P1 | 存在 | `ScriptSessionResolve` 使用 `navigate(..., { replace: true })`；工作台 header 没有返回列表按钮；旧 `/voice`/`/export` redirect 使用 `replace`。 | 先加显式“返回脚本列表”；谨慎评估 resolver 是否改为 push。 |
| P2 | 存在 | Voice Studio 只展示 `standardText` 的 `<p>`；前后端设置里没有 `preview_text`；后端固定 `STANDARD_PREVIEW_TEXT`。 | 增加可编辑试音文本，空值回退标准文案。 |
| P3 | 部分存在，需拆范围 | 默认配置/设置/Voice Studio 是 `wav`；mock 固定 wav；MIME 有 `.m4a` 但无 `.mp4`；无视频轨。 | 本计划只做音频-only 心智与可选项整理；真正 AAC/M4A/MP4 转码另开里程碑。 |
| P4 | 存在 | `ScriptPage` 缺 `scriptId` 时只有提示文本，无返回列表入口。 | 增加返回 `/script` 按钮。 |
| P5 | 核心问题已修，仍需回归/文档 | `resolveAudioFileUrl` 已走 runtime `/api/v1/artifacts/audio`；后端已限制 exports 目录并设置 MIME。音频元素缺少 `onError` 缺失文件提示。 | 增加前端播放错误提示；补文档/测试。 |
| P6 | 存在 | Script 主路径 `renderAudio` 只传 provider/scriptId；后端 `render_audio` 使用保存的 TTS 配置。Voice Studio take 使用单次 `audio_format`。 | UI 明示“Script 主生成使用 Settings，Voice Studio 高级格式只影响本次 take”；暂不做主路径 override。 |
| P7 | 存在，属于 P1 的导航同类问题 | Chat 有时跳 `/script/:sessionId`，再被 resolver replace 到完整路径。 | 与 P1 一并通过显式返回入口降低困惑。 |

---

## File Structure

- Modify: `apps/desktop/src/pages/script-workbench/ScriptWorkbenchHeader.tsx` — 工作台头部新增“返回脚本列表”。
- Modify: `apps/desktop/src/pages/ScriptPage.tsx` — 缺 `scriptId` 空状态增加按钮。
- Modify: `apps/desktop/src/pages/VoiceStudioPage.tsx` — 试音文本改为可编辑 textarea；音频播放错误提示；格式说明文案。
- Modify: `apps/desktop/src/types.ts` — `VoiceRenderSettings` 增加 `preview_text?: string`。
- Modify: `apps/desktop/src/lib/httpBridge.ts` — 序列化 `preview_text`。
- Modify: `services/python-core/app/orchestration/audio_rendering.py` — `VoiceRenderSettings` 增加 `preview_text`，预览时使用用户文本或回退标准文案。
- Modify: `services/python-core/app/api/http_runtime.py` — 解析/序列化 `preview_text`；可选加入 `.mp4` 的音频-only MIME 映射。
- Modify: `services/python-core/tests/test_audio_rendering.py` — 覆盖自定义试音文本。
- Modify: `services/python-core/tests/test_http_runtime.py` — 覆盖预览请求透传 `preview_text` 与 `.mp4` MIME（如果实现 MIME）。
- Modify: `docs/product/product-overview.md` — 记录 Voice Studio 可编辑试音和格式心智边界。
- Modify: `docs/architecture/audio-rendering.md` — 记录当前不引入转码、WAV 默认、M4A/MP4 后续里程碑。
- Modify if behavior changes: `AGENTS.md` — 仅当新增跨边界规则或执行注意事项时同步。

---

### Task 1: Navigation Safety Net for Script Workbench

**Files:**
- Modify: `apps/desktop/src/pages/script-workbench/ScriptWorkbenchHeader.tsx`
- Modify: `apps/desktop/src/pages/ScriptPage.tsx`

- [x] **Step 1: Add an explicit return button in the workbench header**

Update `apps/desktop/src/pages/script-workbench/ScriptWorkbenchHeader.tsx`:

```tsx
import { ArrowLeft, Save, Wand2 } from "lucide-react";
import type { UseScriptWorkbenchResult } from "./useScriptWorkbench";

export function ScriptWorkbenchHeader({ workbench }: { workbench: UseScriptWorkbenchResult }) {
  return (
    <section className="rounded-[28px] border border-outline bg-[linear-gradient(180deg,rgba(33,33,37,0.96),rgba(25,25,28,0.94))] px-5 py-5 shadow-[0_24px_80px_rgba(0,0,0,0.38)] backdrop-blur-xl lg:px-6">
      <button
        type="button"
        onClick={() => workbench.navigate("/script")}
        className="mb-4 inline-flex items-center gap-2 rounded-full border border-outline bg-surface-container-low px-3 py-2 text-xs font-medium text-secondary transition-colors hover:border-accent-amber/30 hover:text-primary"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        返回脚本列表
      </button>
      {/* keep the existing header body below unchanged */}
    </section>
  );
}
```

Do not remove existing Save / Generate Audio actions; insert the button above the existing flex container.

- [x] **Step 2: Add a list button to the missing-script empty state**

Replace the `!scriptId` branch in `apps/desktop/src/pages/ScriptPage.tsx` with:

```tsx
if (!scriptId) {
  return (
    <div className="flex h-full items-center justify-center p-8 text-center">
      <div className="max-w-sm rounded-2xl border border-outline bg-surface p-6">
        <p className="text-sm text-secondary">Missing script id. Use the script list or open from chat.</p>
        <button
          type="button"
          onClick={() => navigate("/script")}
          className="mt-4 rounded-xl border border-outline bg-surface-container-low px-4 py-2 text-sm font-medium text-primary hover:border-accent-amber/30"
        >
          返回脚本列表
        </button>
      </div>
    </div>
  );
}
```

- [x] **Step 3: Verify frontend typecheck**

Run:

```bash
pnpm --dir apps/desktop check
```

Expected: `tsc --noEmit` completes with exit code 0.

- [x] **Step 4: Commit**

```bash
git add apps/desktop/src/pages/script-workbench/ScriptWorkbenchHeader.tsx apps/desktop/src/pages/ScriptPage.tsx
git commit -m "Clarify script workspace escape routes

The script workspace can be reached through deep links and resolver redirects, so browser history is not always a reliable user-facing back path. A first-class return-to-list action gives every entry path the same recovery target.

Constraint: Product decision D1 says Script workbench return target is /script
Rejected: Change every resolver redirect to push | higher risk of duplicate transient history entries
Confidence: high
Scope-risk: narrow
Tested: pnpm --dir apps/desktop check
Not-tested: Manual browser history traversal across every legacy route"
```

---

### Task 2: Editable Voice Studio Preview Text

**Files:**
- Modify: `apps/desktop/src/types.ts`
- Modify: `apps/desktop/src/lib/httpBridge.ts`
- Modify: `apps/desktop/src/pages/VoiceStudioPage.tsx`
- Modify: `services/python-core/app/orchestration/audio_rendering.py`
- Modify: `services/python-core/app/api/http_runtime.py`
- Modify: `services/python-core/tests/test_audio_rendering.py`
- Modify: `services/python-core/tests/test_http_runtime.py`

- [x] **Step 1: Write backend failing test for custom preview text**

Add to `services/python-core/tests/test_audio_rendering.py`:

```python
def test_render_voice_preview_uses_custom_preview_text(self) -> None:
    service, _, artifact_store, _ = self.build_service()
    result = service.render_voice_preview(
        VoiceRenderSettings(
            voice_id="warm_narrator",
            style_id="natural",
            preview_text="这是我自己输入的一句试音文本。",
        )
    )

    self.assertEqual(result.settings.preview_text, "这是我自己输入的一句试音文本。")
    preview_audio = Path(result.audio_path)
    self.assertTrue(preview_audio.exists())
    preview_transcripts = list(artifact_store.exports_dir.glob("voice-preview-*.txt"))
    self.assertTrue(preview_transcripts)
    self.assertEqual(preview_transcripts[-1].read_text(encoding="utf-8"), "这是我自己输入的一句试音文本。\n")
```

If `write_preview_transcript` does not exist yet, this test should fail first; implement it in the next steps only if the product wants preview transcript retention. If not retaining preview transcripts, replace the transcript assertion with a fake provider assertion on `request.script_text`.

- [x] **Step 2: Run the targeted backend test and confirm red**

```bash
cd services/python-core
PYTHONPATH=. python3 -m unittest tests.test_audio_rendering.AudioRenderingTests.test_render_voice_preview_uses_custom_preview_text
```

Expected: fail because `VoiceRenderSettings.preview_text` and preview-text dispatch are not implemented.

- [x] **Step 3: Add `preview_text` to backend settings and preview request**

Modify `services/python-core/app/orchestration/audio_rendering.py`:

```python
@dataclass(frozen=True, slots=True)
class VoiceRenderSettings:
    voice_id: str = "warm_narrator"
    voice_name: str = ""
    style_id: str = "natural"
    style_name: str = ""
    speed: float = 1.0
    language: str = "zh"
    audio_format: str = "wav"
    preview_text: str = ""
```

In `render_voice_preview`, compute text before `TTSGenerationRequest`:

```python
preview_text = normalized.preview_text.strip() or STANDARD_PREVIEW_TEXT
request = TTSGenerationRequest(
    session_id="voice-preview",
    script_text=preview_text,
    voice=tts_config.voice,
    audio_format=tts_config.audio_format,
    speed=normalized.speed,
    style_id=normalized.style_id,
    style_prompt=style.prompt,
    language=normalized.language,
)
```

In `_normalize_settings`, add:

```python
preview_text=settings.preview_text.strip(),
```

- [x] **Step 4: Add HTTP payload parsing/serialization**

Modify `services/python-core/app/api/http_runtime.py`:

```python
def voice_settings_from_payload(payload: dict[str, object]) -> VoiceRenderSettings:
    return VoiceRenderSettings(
        voice_id=str(payload.get("voice_id") or "warm_narrator"),
        voice_name=str(payload.get("voice_name") or ""),
        style_id=str(payload.get("style_id") or "natural"),
        style_name=str(payload.get("style_name") or ""),
        speed=float(payload.get("speed") or 1.0),
        language=str(payload.get("language") or "zh"),
        audio_format=str(payload.get("audio_format") or "wav"),
        preview_text=str(payload.get("preview_text") or ""),
    )
```

Add to `serialize_voice_settings`:

```python
"preview_text": settings.preview_text,
```

- [x] **Step 5: Add frontend type and bridge serialization**

Modify `apps/desktop/src/types.ts`:

```ts
export type VoiceRenderSettings = {
  voice_id: string;
  voice_name?: string;
  style_id: string;
  style_name?: string;
  speed: number;
  language?: string;
  audio_format?: string;
  preview_text?: string;
};
```

Modify `apps/desktop/src/lib/httpBridge.ts` so `serializeVoiceSettings` includes:

```ts
preview_text: settings.preview_text ?? "",
```

- [x] **Step 6: Replace read-only preview sentence with editable textarea**

In `apps/desktop/src/pages/VoiceStudioPage.tsx`, rename state to make intent clear:

```tsx
const [previewText, setPreviewText] = useState("");
```

When loading presets:

```tsx
setPreviewText(catalog.standard_preview_text);
```

Include it in settings:

```tsx
preview_text: previewText,
```

Render the textarea:

```tsx
<textarea
  value={previewText}
  onChange={(event) => setPreviewText(event.target.value)}
  rows={3}
  placeholder="输入一句你想用来比较音色与风格的试音文本"
  className="mt-4 w-full resize-none rounded-2xl border border-outline bg-background px-4 py-3 text-sm text-primary outline-none focus:border-accent-amber/40"
/>
<p className="mt-2 text-[11px] text-secondary">留空时使用系统标准试音句。</p>
```

- [x] **Step 7: Verify backend and frontend**

```bash
cd services/python-core
PYTHONPATH=. python3 -m unittest tests.test_audio_rendering tests.test_http_runtime
cd ../..
pnpm --dir apps/desktop check
```

Expected: all pass.

- [x] **Step 8: Commit**

```bash
git add apps/desktop/src/types.ts apps/desktop/src/lib/httpBridge.ts apps/desktop/src/pages/VoiceStudioPage.tsx services/python-core/app/orchestration/audio_rendering.py services/python-core/app/api/http_runtime.py services/python-core/tests/test_audio_rendering.py services/python-core/tests/test_http_runtime.py
git commit -m "Let Voice Studio preview user-authored text

Voice comparison needs to exercise the words a user cares about, while still preserving the standard sentence as a safe fallback. The preview text now travels through the same typed settings object as voice, style, speed, and format.

Constraint: Empty preview text must continue to use the packaged standard sentence
Rejected: Store preview text on session artifacts | preview text is transient comparison input, not a final artifact contract
Confidence: high
Scope-risk: moderate
Tested: PYTHONPATH=. python3 -m unittest tests.test_audio_rendering tests.test_http_runtime
Tested: pnpm --dir apps/desktop check
Not-tested: Manual listening comparison with real remote TTS provider"
```

---

### Task 3: Make Audio Format Scope Explicit Without Adding Transcoding

**Files:**
- Modify: `apps/desktop/src/pages/SettingsPage.tsx`
- Modify: `apps/desktop/src/pages/VoiceStudioPage.tsx`
- Modify: `services/python-core/app/api/http_runtime.py`
- Modify: `services/python-core/tests/test_http_runtime.py`
- Modify: `docs/architecture/audio-rendering.md`
- Modify: `docs/product/product-overview.md`

- [x] **Step 1: Add MIME coverage test for `.mp4` audio-only files**

Add to `services/python-core/tests/test_http_runtime.py` near existing artifact audio tests:

```python
def test_artifact_audio_route_serves_mp4_as_audio_mp4(self) -> None:
    audio_path = self.artifact_store.exports_dir / "sample.mp4"
    audio_path.write_bytes(b"fake-mp4-audio")
    encoded_path = quote(str(audio_path))

    response = self.request("GET", f"/api/v1/artifacts/audio?path={encoded_path}")

    self.assertEqual(response.status, HTTPStatus.OK)
    headers = dict(response.headers)
    self.assertEqual(headers["Content-Type"], "audio/mp4")
    self.assertEqual(response.body, b"fake-mp4-audio")
```

- [x] **Step 2: Implement MIME mapping only**

Modify `_serve_artifact_audio` in `services/python-core/app/api/http_runtime.py`:

```python
".mp4": "audio/mp4",
```

Do not add conversion or claim video support.

- [x] **Step 3: Clarify Settings audio format copy**

In `apps/desktop/src/pages/SettingsPage.tsx`, change the placeholder and helper copy around audio format:

```tsx
placeholder="wav, mp3, m4a, or audio-only mp4"
```

Add a small helper below the input:

```tsx
<p className="mt-1 text-[11px] text-secondary">
  WAV is the safest default. M4A/MP4 here means audio-only output when the selected provider/runtime can produce it; this app does not create video MP4 files yet.
</p>
```

- [x] **Step 4: Clarify Voice Studio one-off format copy**

In `apps/desktop/src/pages/VoiceStudioPage.tsx`, under the output format input, add:

```tsx
<p className="mt-1 text-[11px] text-secondary">
  只影响本次 Voice Studio take；Script 页“生成完整音频”仍使用 Settings 中保存的 TTS 格式。MP4 指 audio-only 容器，不含视频画面。
</p>
```

- [x] **Step 5: Document deferred transcoding milestone**

Update `docs/architecture/audio-rendering.md` and `docs/product/product-overview.md` with:

```md
### Audio-only MP4 / M4A scope

The current app can request provider/runtime output formats and serve common audio suffixes, but it does not transcode WAV to AAC/M4A/MP4 itself. `.mp4` means audio-only container support when the selected provider/runtime produces a valid file. True video MP4 and guaranteed WAV → AAC conversion require a separate ffmpeg/afconvert packaging decision.
```

- [x] **Step 6: Verify**

```bash
cd services/python-core
PYTHONPATH=. python3 -m unittest tests.test_http_runtime.HttpRuntimeTests.test_artifact_audio_route_serves_mp4_as_audio_mp4
cd ../..
pnpm --dir apps/desktop check
```

Expected: tests and typecheck pass.

- [x] **Step 7: Commit**

```bash
git add apps/desktop/src/pages/SettingsPage.tsx apps/desktop/src/pages/VoiceStudioPage.tsx services/python-core/app/api/http_runtime.py services/python-core/tests/test_http_runtime.py docs/architecture/audio-rendering.md docs/product/product-overview.md
git commit -m "Set audio format expectations before adding transcoding

Users asked for more everyday formats, but the current architecture only requests formats from providers/runtimes and serves resulting files. The UI and docs now distinguish audio-only MP4/M4A from true video MP4 and defer guaranteed WAV-to-AAC conversion to a separate packaging decision.

Constraint: No new dependencies without explicit request
Rejected: Bundle ffmpeg in this fix | licensing, binary size, and packaging impact need a separate milestone
Rejected: Rename default output to MP4 | would overpromise support for runtimes that currently emit WAV
Confidence: medium
Scope-risk: narrow
Tested: PYTHONPATH=. python3 -m unittest tests.test_http_runtime.HttpRuntimeTests.test_artifact_audio_route_serves_mp4_as_audio_mp4
Tested: pnpm --dir apps/desktop check
Not-tested: Real provider-generated M4A/MP4 playback across browsers"
```

---

### Task 4: Audio Preview Failure Feedback

**Files:**
- Modify: `apps/desktop/src/pages/script-workbench/useScriptWorkbenchAudio.ts`
- Modify: `apps/desktop/src/pages/script-workbench/ScriptAudioSidebar.tsx`
- Modify: `apps/desktop/src/pages/VoiceStudioPage.tsx`
- Optional Modify: `apps/desktop/src/pages/GeneratePage.tsx`

- [x] **Step 1: Add audio-element load error handlers**

For Script workbench, expose a handler from `useScriptWorkbenchAudio.ts`:

```ts
const handleAudioLoadError = () => {
  setAudioError("无法加载音频文件。文件可能已移动或删除，请重新生成音频。");
};
```

Return it from the hook and add it to `UseScriptWorkbenchAudioResult` / `UseScriptWorkbenchResult`.

- [x] **Step 2: Wire the handler to the Script audio element**

In `apps/desktop/src/pages/script-workbench/ScriptAudioSidebar.tsx`:

```tsx
<audio
  ref={workbench.audioRef}
  controls
  src={workbench.audioSrc}
  onError={workbench.handleAudioLoadError}
  className="mt-4 w-full [&::-webkit-media-controls-panel]:bg-background [&::-webkit-media-controls-panel]:border [&::-webkit-media-controls-panel]:border-outline"
/>
```

- [x] **Step 3: Add Voice Studio preview/take audio load errors**

In `apps/desktop/src/pages/VoiceStudioPage.tsx`, add:

```tsx
const handleAudioLoadError = () => {
  setError("无法加载音频文件。文件可能已移动或删除，请重新生成音频。");
};
```

Use it on both preview and take audio elements:

```tsx
<audio ref={previewAudioRef} controls src={previewSrc} onError={handleAudioLoadError} className="mt-4 w-full" />
<audio controls src={src} onError={handleAudioLoadError} className="mt-3 w-full" />
```

- [x] **Step 4: Verify**

```bash
pnpm --dir apps/desktop check
pnpm --dir apps/desktop build:web
```

Expected: typecheck and Vite build pass. Vite may keep the existing large chunk warning; that is not a failure.

- [x] **Step 5: Commit**

```bash
git add apps/desktop/src/pages/script-workbench/useScriptWorkbenchAudio.ts apps/desktop/src/pages/script-workbench/ScriptAudioSidebar.tsx apps/desktop/src/pages/VoiceStudioPage.tsx apps/desktop/src/pages/GeneratePage.tsx
git commit -m "Explain missing artifact playback failures

The HTTP artifact route fixes browser file URL blocking, but users still need a clear recovery path when a persisted artifact path no longer points to a playable file. Audio elements now surface a regenerate hint instead of failing silently.

Constraint: Artifact serving remains restricted to the exports directory
Confidence: high
Scope-risk: narrow
Tested: pnpm --dir apps/desktop check
Tested: pnpm --dir apps/desktop build:web
Not-tested: Manual deletion of artifact file followed by browser playback"
```

---

### Task 5: Final Regression Pass

**Files:**
- No direct file target unless verification reveals failures.

- [x] **Step 1: Run Python tests**

```bash
cd services/python-core
PYTHONPATH=. python3 -m unittest discover -s tests
```

Expected: all tests pass.

- [x] **Step 2: Run frontend typecheck and web build**

```bash
pnpm --dir apps/desktop check
pnpm --dir apps/desktop build:web
```

Expected: typecheck/build pass. Existing Vite chunk-size warning is acceptable.

- [x] **Step 3: Run Rust compile check**

```bash
cd apps/desktop/src-tauri
cargo check
```

Expected: compile check passes.

- [x] **Step 4: Optional manual browser smoke test**

Run dev stack per repo notes:

```bash
./scripts/dev/run-dev-all.sh
```

Smoke path:

1. Open Script list.
2. Open a script workspace.
3. Click “返回脚本列表”; confirm it lands on `/script`.
4. Reopen the script; open Voice Studio.
5. Edit preview text and generate preview.
6. Confirm the preview uses the custom text if using a test provider that exposes request text, or at least that no runtime/schema error occurs.
7. Generate a voice take and confirm Script sidebar still shows the selected final take.

- [x] **Step 5: Final commit only if verification required follow-up edits**

Use Lore commit protocol for any fixes discovered during regression.

---

## Out of Scope / Follow-up Plan

A separate plan should cover guaranteed “daily format” output if product chooses it:

1. Decide target: M4A only, audio-only MP4, or true video MP4.
2. Decide encoder: provider-native, macOS `afconvert`, bundled ffmpeg, or user-installed ffmpeg.
3. Add a post-processing module under `services/python-core/app/providers` or `services/python-core/app/orchestration` with explicit dependency/license checks.
4. Extend request-state progress for post-processing.
5. Add packaging and notarization checks for any bundled binary.

Do not fold that into the small UX fix unless the dependency/packaging decision is made explicitly.
