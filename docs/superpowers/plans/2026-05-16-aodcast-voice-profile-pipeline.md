# Aodcast Voice Profile Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make voice generation profile-first: users add/select one voice profile, preview it, and render podcasts through the same profile reference audio and reference text.

**Architecture:** Keep the existing voice profile store and script-scoped `artifact.voice_reference`, but make `source: "voice_profile"` the primary path. Preview and full render resolve the same profile anchor, pass `ref_audio` and `ref_text` into local MLX/Qwen, and the desktop UI stops presenting temporary preview locks or Voice Studio take comparison as primary workflows.

**Tech Stack:** Python 3.13 stdlib/unittest backend, local HTTP runtime bridge, React/Vite/Tauri desktop frontend, JSON schemas in `packages/shared-schemas`.

**Execution status (2026-05-16):** Implemented and verified. Main deviations from the draft plan:
- `POST /audio:render` and `POST /voice-takes:render` parse `require_voice_profile` with `_body_flag(...)`, not raw `bool(...)`, so string `"false"` is not treated as true.
- Voice Studio's primary full-audio path now calls `renderAudio` with `requireVoiceProfile`; legacy take APIs remain available for compatibility and are hidden behind Advanced UI.
- Preview-to-profile promotion remains available behind Advanced UI for compatibility, but selected voice profiles are the required primary anchor before preview or full render.
- Git commit/staging may be blocked in this sandbox by `.git/index.lock` permissions; verification evidence should be used if commit creation fails.

---

## File Structure

- Modify `services/python-core/app/domain/voice_profile.py`: expose reference-text semantics while preserving `preview_text` compatibility.
- Modify `services/python-core/app/storage/voice_profile_store.py`: create user profiles directly from a user-provided reference audio file and reference text.
- Modify `services/python-core/app/orchestration/audio_rendering.py`: let preview use a selected profile anchor; make full render fail early for profile-first local renders without a selected profile.
- Modify `services/python-core/app/api/http_runtime.py`: accept profile-first payloads for create/profile preview routes.
- Modify `services/python-core/app/api/serializers.py`: serialize/parse reference text consistently.
- Modify `packages/shared-schemas/artifact.schema.json` and `packages/shared-schemas/voice-profile.schema.json`: document the profile anchor/reference-text contract.
- Modify `apps/desktop/src/types.ts`: add reference-text and profile preview types.
- Modify `apps/desktop/src/lib/desktopBridge.ts` and `apps/desktop/src/lib/httpBridge.ts`: send profile-first payloads.
- Modify `apps/desktop/src/pages/VoiceStudioPage.tsx`: simplify to current profile, profile library, add profile, preview, and generate.
- Modify `docs/product/product-overview.md`, `docs/architecture/audio-rendering.md`, and `docs/architecture/tts-pipeline.md`: reflect profile-first behavior.
- Modify tests:
  - `services/python-core/tests/test_http_runtime.py`
  - `services/python-core/tests/test_audio_rendering.py`
  - `services/python-core/tests/test_local_mlx_tts.py`
  - `services/python-core/tests/test_bridge_request_state_schema.py`
  - `services/python-core/tests/http_contract_helpers.py` only if bridge method names change; prefer keeping names stable.

---

### Task 1: Tighten Voice Profile Storage Around Reference Text

**Files:**
- Modify: `services/python-core/app/domain/voice_profile.py`
- Modify: `services/python-core/app/storage/voice_profile_store.py`
- Modify: `packages/shared-schemas/voice-profile.schema.json`
- Test: `services/python-core/tests/test_http_runtime.py`

- [ ] **Step 1: Write failing HTTP test for direct user profile creation**

Add this test to `services/python-core/tests/test_http_runtime.py` near `test_create_voice_profile_and_select_for_script`:

```python
def test_create_voice_profile_requires_reference_text_and_copies_reference_audio(self) -> None:
    source_audio = self.artifact_store.write_preview_audio(b"reference-audio", "wav")

    missing_status, _, missing_payload = self.request_json(
        "POST",
        "/api/v1/voice-profiles",
        body={
            "name": "缺少文本",
            "audio_path": str(source_audio),
            "provider": "local_mlx",
            "model": "mlx-voice",
        },
    )

    self.assertEqual(missing_status, 400)
    self.assertIn("reference_text", missing_payload["error"]["message"])

    status, _, payload = self.request_json(
        "POST",
        "/api/v1/voice-profiles",
        body={
            "name": "我的稳定主播",
            "audio_path": str(source_audio),
            "reference_text": "这是一段用于克隆音色的参考文本。",
            "provider": "local_mlx",
            "model": "mlx-voice",
            "language": "zh",
            "audio_format": "wav",
        },
    )

    self.assertEqual(status, 200)
    profile = payload["data"]["profile"]
    self.assertEqual(profile["name"], "我的稳定主播")
    self.assertEqual(profile["preview_text"], "这是一段用于克隆音色的参考文本。")
    self.assertEqual(profile["reference_text"], "这是一段用于克隆音色的参考文本。")
    self.assertEqual(profile["source"], "user_saved")
    self.assertNotEqual(profile["audio_path"], str(source_audio))
    self.assertTrue(Path(profile["audio_path"]).exists())
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd services/python-core
PYTHONPATH=. .venv/bin/python -m unittest tests.test_http_runtime.HTTPRuntimeTests.test_create_voice_profile_requires_reference_text_and_copies_reference_audio
```

Expected: fail because `reference_text` is not required and not serialized as `reference_text`.

- [ ] **Step 3: Add a compatibility alias on `VoiceProfileRecord`**

In `services/python-core/app/domain/voice_profile.py`, change `to_dict()` so it emits both keys from the same stored value:

```python
    def to_dict(self) -> dict[str, Any]:
        created_at = self.created_at or utc_now_iso()
        updated_at = self.updated_at or created_at
        reference_text = self.preview_text
        return {
            "voice_profile_id": self.voice_profile_id,
            "name": self.name,
            "source": self.source,
            "audio_path": self.audio_path,
            "preview_text": reference_text,
            "reference_text": reference_text,
            "provider": self.provider,
            "model": self.model,
            "voice_id": self.voice_id,
            "voice_name": self.voice_name,
            "style_id": self.style_id,
            "style_name": self.style_name,
            "speed": self.speed,
            "language": self.language,
            "audio_format": self.audio_format,
            "description": self.description,
            "created_at": created_at,
            "updated_at": updated_at,
            "last_used_at": self.last_used_at,
        }
```

In `from_dict()`, read `reference_text` first and fall back to the old key:

```python
            preview_text=str(payload.get("reference_text") or payload.get("preview_text") or ""),
```

- [ ] **Step 4: Update profile creation validation**

In `services/python-core/app/storage/voice_profile_store.py`, change `create_user_profile(...)` to accept direct profile input while keeping the old generated-preview path callable:

```python
    def create_user_profile(
        self,
        *,
        name: str,
        preview_audio_path: str = "",
        reference_audio_path: str = "",
        reference_text: str = "",
        settings: VoiceRenderSettings | None = None,
        provider: str,
        model: str,
        language: str = "zh",
        audio_format: str = "wav",
    ) -> VoiceProfileRecord:
        raw_audio_path = reference_audio_path.strip() or preview_audio_path.strip()
        source_audio = self._validate_reference_audio_path(raw_audio_path)
        text = reference_text.strip()
        if not text and settings is not None:
            text = settings.preview_text.strip()
        if not text:
            raise ValueError("Field 'reference_text' is required.")
        normalized = self._normalize_settings(settings or VoiceRenderSettings(language=language, audio_format=audio_format, preview_text=text))
        profile_id = f"user_{uuid4().hex}"
        suffix = source_audio.suffix.lower().lstrip(".") or normalized.audio_format or "wav"
        target = self.audio_dir / f"{profile_id}.{suffix}"
        shutil.copyfile(source_audio, target)
        now = utc_now_iso()
        profile = VoiceProfileRecord(
            voice_profile_id=profile_id,
            name=name.strip() or "我的音色",
            source="user_saved",
            audio_path=str(target),
            preview_text=text,
            provider=provider.strip() or "local_mlx",
            model=model.strip(),
            voice_id=normalized.voice_id,
            voice_name=normalized.voice_name,
            style_id=normalized.style_id,
            style_name=normalized.style_name,
            speed=normalized.speed,
            language=normalized.language,
            audio_format=suffix,
            description="用户添加的参考音色",
            created_at=now,
            updated_at=now,
        )
        profiles = self._read_user_profiles()
        profiles.append(profile)
        self._write_user_profiles(profiles)
        return profile
```

Replace `_validate_export_audio_path` with `_validate_reference_audio_path` that accepts an existing file, copies it into app-managed storage, and rejects directories:

```python
    def _validate_reference_audio_path(self, path: str) -> Path:
        if not path.strip():
            raise ValueError("Voice profile reference audio path is required.")
        target = Path(path).expanduser().resolve()
        if not target.exists():
            raise ValueError("Voice profile reference audio is missing.")
        if not target.is_file():
            raise ValueError("Voice profile reference audio must point to a file.")
        if target.suffix.lower() not in {".wav", ".mp3", ".m4a", ".mp4", ".aac", ".flac"}:
            raise ValueError("Voice profile reference audio must be a supported audio file.")
        return target
```

- [ ] **Step 5: Update HTTP route body parsing**

In `services/python-core/app/api/http_runtime.py`, update the `POST /api/v1/voice-profiles` branch:

```python
            settings_payload = body.get("voice_settings")
            settings = voice_settings_from_payload(settings_payload) if isinstance(settings_payload, dict) else None
            profile = self.context.get_voice_profile_store().create_user_profile(
                name=str(body.get("name") or ""),
                reference_audio_path=str(body.get("reference_audio_path") or body.get("audio_path") or ""),
                reference_text=str(body.get("reference_text") or ""),
                preview_audio_path=str(body.get("audio_path") or ""),
                settings=settings,
                provider=str(body.get("provider") or ""),
                model=str(body.get("model") or ""),
                language=str(body.get("language") or "zh"),
                audio_format=str(body.get("audio_format") or "wav"),
            )
```

- [ ] **Step 6: Update voice profile JSON schema**

In `packages/shared-schemas/voice-profile.schema.json`, add `reference_text` as a string property and keep `preview_text` for compatibility. If the schema has a required array, include `reference_text` for new payloads while not removing `preview_text` until frontend and backend compatibility tests are updated.

- [ ] **Step 7: Run the test**

Run:

```bash
cd services/python-core
PYTHONPATH=. .venv/bin/python -m unittest tests.test_http_runtime.HTTPRuntimeTests.test_create_voice_profile_requires_reference_text_and_copies_reference_audio
```

Expected: `OK`.

- [ ] **Step 8: Commit**

```bash
git add services/python-core/app/domain/voice_profile.py services/python-core/app/storage/voice_profile_store.py services/python-core/app/api/http_runtime.py packages/shared-schemas/voice-profile.schema.json services/python-core/tests/test_http_runtime.py
git commit -m "Make voice profiles carry explicit reference text

Constraint: Voice profile storage must remain compatible with existing preview_text payloads.
Rejected: Keep creating user profiles only from generated previews | It preserves the unstable temporary-preview workflow.
Confidence: high
Scope-risk: moderate
Directive: Treat preview_text and reference_text as one value until a dedicated migration removes the legacy key.
Tested: PYTHONPATH=. .venv/bin/python -m unittest tests.test_http_runtime.HTTPRuntimeTests.test_create_voice_profile_requires_reference_text_and_copies_reference_audio
Not-tested: Desktop UI manual file picker flow."
```

---

### Task 2: Make Profile Preview Use The Same Anchor As Full Render

**Files:**
- Modify: `services/python-core/app/orchestration/audio_rendering.py`
- Modify: `services/python-core/app/api/http_runtime.py`
- Test: `services/python-core/tests/test_audio_rendering.py`
- Test: `services/python-core/tests/test_http_runtime.py`

- [ ] **Step 1: Write failing orchestration test**

Add to `services/python-core/tests/test_audio_rendering.py`:

```python
def test_voice_preview_uses_selected_profile_reference_audio_and_text(self) -> None:
    store, config_store, artifact_store, service = self.build_environment()
    config_store.save_tts_config(TTSProviderConfig(provider="local_mlx", model="mlx-voice", local_model_path="/tmp/model"))
    profile_audio = artifact_store.write_preview_audio(b"profile-audio", "wav")
    captured: dict[str, object] = {}

    class CapturingProvider:
        def synthesize(self, request):  # type: ignore[no-untyped-def]
            captured["request"] = request
            return TTSGenerationResponse(
                audio_bytes=b"preview-audio",
                file_extension=request.audio_format,
                provider_name="local_mlx",
                model_name="mlx-voice",
            )

    voice_reference = {
        "source": "voice_profile",
        "voice_profile_id": "profile-1",
        "audio_path": str(profile_audio),
        "preview_text": "这是一段参考文本。",
        "provider": "local_mlx",
        "model": "mlx-voice",
    }

    with patch("app.orchestration.audio_rendering.build_tts_provider", return_value=CapturingProvider()):
        result = service.render_voice_preview_with_cancellation(
            VoiceRenderSettings(preview_text="试听当前音色。"),
            voice_reference=voice_reference,
        )

    request = captured["request"]
    self.assertEqual(result.audio_path.endswith(".wav"), True)
    self.assertEqual(request.script_text, "试听当前音色。")
    self.assertEqual(request.reference_audio_path, str(profile_audio))
    self.assertEqual(request.reference_text, "这是一段参考文本。")
```

- [ ] **Step 2: Run failing orchestration test**

Run:

```bash
cd services/python-core
PYTHONPATH=. .venv/bin/python -m unittest tests.test_audio_rendering.AudioRenderingTests.test_voice_preview_uses_selected_profile_reference_audio_and_text
```

Expected: fail because `render_voice_preview_with_cancellation` has no `voice_reference` argument.

- [ ] **Step 3: Add optional `voice_reference` parameter**

In `services/python-core/app/orchestration/audio_rendering.py`, update the signature and request creation:

```python
    def render_voice_preview_with_cancellation(
        self,
        settings: VoiceRenderSettings,
        *,
        override_provider: str = "",
        voice_reference: dict[str, object] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[AudioRenderProgress], None] | None = None,
    ) -> VoicePreviewResult:
```

Before building the request, validate profile references only for local MLX:

```python
        resolved_reference = {}
        if tts_config.provider == "local_mlx" and voice_reference:
            audio_path = str(voice_reference.get("audio_path") or "")
            if audio_path:
                self._validate_reference_audio_path(audio_path)
                resolved_reference = dict(voice_reference)
```

Set reference fields in `TTSGenerationRequest`:

```python
            reference_audio_path=str(resolved_reference.get("audio_path") or ""),
            reference_text=str(resolved_reference.get("reference_text") or resolved_reference.get("preview_text") or ""),
            voice_lock_id=str(resolved_reference.get("lock_id") or resolved_reference.get("voice_profile_id") or ""),
```

- [ ] **Step 4: Write failing HTTP preview test**

Add to `services/python-core/tests/test_http_runtime.py`:

```python
def test_voice_preview_route_uses_profile_reference_when_profile_id_is_sent(self) -> None:
    session_id, script_id = self.seed_renderable_project()
    profile_audio = self.artifact_store.write_preview_audio(b"profile-audio", "wav")
    profile = self.voice_profile_store.create_user_profile(
        name="稳定主播",
        reference_audio_path=str(profile_audio),
        reference_text="这是一段参考文本。",
        provider="local_mlx",
        model="mlx-voice",
    )
    self.context.audio_rendering.select_voice_profile(
        session_id,
        script_id=script_id,
        profile=profile,
    )

    with patch.object(
        RuntimeContext,
        "start_render_voice_preview",
        autospec=True,
        return_value=success_envelope({"task_id": "render_voice_preview:test"}, operation="render_voice_preview"),
    ) as mocked_start:
        status, _, payload = self.request_json(
            "POST",
            "/api/v1/voice-studio/preview",
            body={
                "session_id": session_id,
                "script_id": script_id,
                "voice_profile_id": profile.voice_profile_id,
                "preview_text": "试听当前音色。",
            },
        )

    self.assertEqual(status, 200)
    self.assertTrue(payload["ok"])
    _, settings = mocked_start.call_args.args[:2]
    self.assertEqual(settings.preview_text, "试听当前音色。")
    self.assertEqual(mocked_start.call_args.kwargs["voice_profile_id"], profile.voice_profile_id)
```

- [ ] **Step 5: Thread `voice_profile_id` through runtime context**

Find `RuntimeContext.start_render_voice_preview` in `services/python-core/app/api/http_runtime.py`. Add a keyword argument:

```python
    def start_render_voice_preview(
        self,
        settings: VoiceRenderSettings,
        *,
        session_id: str = "",
        script_id: str = "",
        override_provider: str = "",
        voice_profile_id: str = "",
    ) -> dict[str, object]:
```

Inside the worker callback, resolve a profile reference when `voice_profile_id` is present:

```python
            voice_reference: dict[str, object] | None = None
            if voice_profile_id.strip():
                profile = self.get_voice_profile_store().get_profile(voice_profile_id)
                voice_reference = {
                    "source": "voice_profile",
                    "voice_profile_id": profile.voice_profile_id,
                    "audio_path": profile.audio_path,
                    "preview_text": profile.preview_text,
                    "reference_text": profile.preview_text,
                    "provider": profile.provider,
                    "model": profile.model,
                }
```

Pass it into `render_voice_preview_with_cancellation(..., voice_reference=voice_reference, ...)`.

In the `POST /api/v1/voice-studio/preview` route, read and pass the id:

```python
            voice_profile_id = str(body.get("voice_profile_id") or "").strip()
            self._send_bridge_envelope(
                self.context.start_render_voice_preview(
                    voice_settings_from_payload(body),
                    session_id=session_id,
                    script_id=script_id,
                    override_provider=provider,
                    voice_profile_id=voice_profile_id,
                ),
                origin=origin,
            )
```

- [ ] **Step 6: Run backend preview tests**

Run:

```bash
cd services/python-core
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_audio_rendering.AudioRenderingTests.test_voice_preview_uses_selected_profile_reference_audio_and_text \
  tests.test_http_runtime.HTTPRuntimeTests.test_voice_preview_route_uses_profile_reference_when_profile_id_is_sent
```

Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add services/python-core/app/orchestration/audio_rendering.py services/python-core/app/api/http_runtime.py services/python-core/tests/test_audio_rendering.py services/python-core/tests/test_http_runtime.py
git commit -m "Route voice previews through selected profiles

Constraint: Preview and full render must share the same profile anchor semantics.
Rejected: Keep preview as preset-only synthesis | It lets the preview sound unlike the rendered podcast.
Confidence: high
Scope-risk: moderate
Directive: New preview UI should send voice_profile_id instead of creating temporary preview locks.
Tested: PYTHONPATH=. .venv/bin/python -m unittest tests.test_audio_rendering.AudioRenderingTests.test_voice_preview_uses_selected_profile_reference_audio_and_text tests.test_http_runtime.HTTPRuntimeTests.test_voice_preview_route_uses_profile_reference_when_profile_id_is_sent
Not-tested: Real MLX audio quality comparison."
```

---

### Task 3: Enforce Profile-First Full Render In The Primary Path

**Files:**
- Modify: `services/python-core/app/orchestration/audio_rendering.py`
- Modify: `services/python-core/app/api/http_runtime.py`
- Test: `services/python-core/tests/test_audio_rendering.py`

- [ ] **Step 1: Write failing test for full render without profile**

Add to `services/python-core/tests/test_audio_rendering.py`:

```python
def test_local_mlx_render_requires_selected_voice_profile_in_profile_first_mode(self) -> None:
    store, config_store, _, service = self.build_environment()
    config_store.save_tts_config(TTSProviderConfig(provider="local_mlx", model="mlx-voice", local_model_path="/tmp/model"))
    session_id = self.seed_script_project(store)

    with self.assertRaisesRegex(ValueError, "Select a voice profile"):
        service.render_audio(session_id, require_voice_profile=True)
```

- [ ] **Step 2: Run failing test**

Run:

```bash
cd services/python-core
PYTHONPATH=. .venv/bin/python -m unittest tests.test_audio_rendering.AudioRenderingTests.test_local_mlx_render_requires_selected_voice_profile_in_profile_first_mode
```

Expected: fail because `render_audio` has no `require_voice_profile` argument.

- [ ] **Step 3: Add `require_voice_profile` flag**

Update `render_audio` and `render_audio_with_cancellation` signatures:

```python
        require_voice_profile: bool = False,
```

Pass it from `render_audio` into `render_audio_with_cancellation`.

After `voice_reference = self._voice_reference_for(...)`, add:

```python
        if require_voice_profile and tts_config.provider == "local_mlx":
            if voice_reference.get("source") != "voice_profile" or not voice_reference.get("voice_profile_id"):
                raise ValueError("Select a voice profile before generating podcast audio.")
```

- [ ] **Step 4: Ensure render still uses selected profile reference**

Add or update this assertion in the existing `test_local_mlx_render_uses_locked_preview_as_reference_audio` test by creating a separate profile-specific test:

```python
def test_local_mlx_render_uses_selected_voice_profile_reference_audio_and_text(self) -> None:
    store, config_store, artifact_store, service = self.build_environment()
    config_store.save_tts_config(TTSProviderConfig(provider="local_mlx", model="mlx-voice", local_model_path="/tmp/model"))
    session_id = self.seed_script_project(store)
    profile_audio = artifact_store.write_preview_audio(b"profile-audio", "wav")
    project = service.select_voice_profile(
        session_id,
        profile=VoiceProfileRecord(
            voice_profile_id="profile-1",
            name="稳定主播",
            source="user_saved",
            audio_path=str(profile_audio),
            preview_text="这是一段参考文本。",
            provider="local_mlx",
            model="mlx-voice",
            voice_id="warm_narrator",
        ),
    )
    captured: dict[str, object] = {}

    class CapturingProvider:
        def synthesize(self, request):  # type: ignore[no-untyped-def]
            captured["request"] = request
            return TTSGenerationResponse(
                audio_bytes=b"local-audio",
                file_extension=request.audio_format,
                provider_name="local_mlx",
                model_name="mlx-voice",
            )

    with patch("app.orchestration.audio_rendering.build_tts_provider", return_value=CapturingProvider()):
        service.render_audio(session_id, require_voice_profile=True)

    request = captured["request"]
    self.assertEqual(request.reference_audio_path, str(profile_audio))
    self.assertEqual(request.reference_text, "这是一段参考文本。")
    self.assertEqual(project.artifact.voice_reference["source"], "voice_profile")
```

- [ ] **Step 5: Add HTTP body flag for profile-first UI**

In `services/python-core/app/api/http_runtime.py`, in the `POST /audio:render` route:

```python
            require_voice_profile = _body_flag(body, "require_voice_profile")
            self._send_bridge_envelope(
                self.context.start_render_audio(
                    session_id,
                    script_id=script_id,
                    override_provider=provider,
                    settings=settings,
                    require_voice_profile=require_voice_profile,
                ),
                origin=origin,
            )
```

Update `RuntimeContext.start_render_audio` to accept and pass `require_voice_profile`.

- [ ] **Step 6: Run render tests**

Run:

```bash
cd services/python-core
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_audio_rendering.AudioRenderingTests.test_local_mlx_render_requires_selected_voice_profile_in_profile_first_mode \
  tests.test_audio_rendering.AudioRenderingTests.test_local_mlx_render_uses_selected_voice_profile_reference_audio_and_text
```

Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add services/python-core/app/orchestration/audio_rendering.py services/python-core/app/api/http_runtime.py services/python-core/tests/test_audio_rendering.py
git commit -m "Require selected profiles for profile-first renders

Constraint: Script Workbench compatibility still needs the old render path unless callers opt into profile-first enforcement.
Rejected: Globally block all local_mlx renders without profiles | It could break legacy sessions and tests unrelated to Voice Studio simplification.
Confidence: high
Scope-risk: moderate
Directive: New profile-first UI must set require_voice_profile=true when rendering podcast audio.
Tested: PYTHONPATH=. .venv/bin/python -m unittest tests.test_audio_rendering.AudioRenderingTests.test_local_mlx_render_requires_selected_voice_profile_in_profile_first_mode tests.test_audio_rendering.AudioRenderingTests.test_local_mlx_render_uses_selected_voice_profile_reference_audio_and_text
Not-tested: Cloud-provider degrade copy."
```

---

### Task 4: Update Desktop Bridge Contracts For Profile-First Calls

**Files:**
- Modify: `apps/desktop/src/types.ts`
- Modify: `apps/desktop/src/lib/desktopBridge.ts`
- Modify: `apps/desktop/src/lib/httpBridge.ts`
- Test: `services/python-core/tests/http_contract_helpers.py` only if method names are changed.

- [ ] **Step 1: Update TypeScript types**

In `apps/desktop/src/types.ts`, update `VoiceProfileRecord` so it includes both keys:

```ts
export type VoiceProfileRecord = {
  voice_profile_id: string;
  name: string;
  source: "built_in" | "user_saved";
  audio_path: string;
  preview_text: string;
  reference_text?: string;
  provider: string;
  model: string;
  voice_id: string;
  voice_name?: string;
  style_id: string;
  style_name?: string;
  speed: number;
  language: string;
  audio_format: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
  last_used_at?: string;
};
```

- [ ] **Step 2: Update bridge input types**

In `apps/desktop/src/lib/desktopBridge.ts`, replace `CreateVoiceProfileInput` with:

```ts
export type CreateVoiceProfileInput = {
  name: string;
  audioPath: string;
  referenceText: string;
  provider: string;
  model: string;
  language?: string;
  audioFormat?: string;
};
```

Extend preview and render options:

```ts
export type RenderVoicePreviewOptions = {
  onState?: (state: RequestState) => void;
  sessionId?: string;
  scriptId?: string;
  providerOverride?: string;
  voiceProfileId?: string;
};

export type RenderAudioOptions = {
  providerOverride?: string;
  scriptId?: string;
  voiceSettings?: VoiceRenderSettings;
  requireVoiceProfile?: boolean;
};
```

Keep `lockVoicePreview`, `renderVoiceTake`, `setFinalVoiceTake`, and `deleteVoiceTake` in the interface for compatibility, but update their comments to say `Legacy`.

- [ ] **Step 3: Update HTTP bridge payloads**

In `apps/desktop/src/lib/httpBridge.ts`, update `renderAudio` body:

```ts
body: JSON.stringify({
  provider_override: options?.providerOverride ?? "",
  script_id: options?.scriptId ?? "",
  voice_settings: options?.voiceSettings ? serializeVoiceSettings(options.voiceSettings) : undefined,
  require_voice_profile: options?.requireVoiceProfile ?? false,
}),
```

Update `renderVoicePreview` body:

```ts
body: JSON.stringify({
  ...serializeVoiceSettings(settings),
  session_id: options?.sessionId ?? "",
  script_id: options?.scriptId ?? "",
  provider_override: options?.providerOverride ?? "",
  voice_profile_id: options?.voiceProfileId ?? "",
}),
```

Update `createVoiceProfile` body:

```ts
body: JSON.stringify({
  name: input.name,
  audio_path: input.audioPath,
  reference_audio_path: input.audioPath,
  reference_text: input.referenceText,
  provider: input.provider,
  model: input.model,
  language: input.language ?? "zh",
  audio_format: input.audioFormat ?? "wav",
}),
```

- [ ] **Step 4: Run frontend typecheck**

Run:

```bash
pnpm --dir apps/desktop check
```

Expected: pass. If dependencies are missing, run `pnpm --dir apps/desktop install` only if necessary and keep lockfile changes if the package manager updates them.

- [ ] **Step 5: Run bridge contract tests**

Run:

```bash
cd services/python-core
PYTHONPATH=. .venv/bin/python -m unittest tests.test_http_bridge_parity tests.test_http_browser_desktop_parity
```

Expected: pass if method names remain stable.

- [ ] **Step 6: Commit**

```bash
git add apps/desktop/src/types.ts apps/desktop/src/lib/desktopBridge.ts apps/desktop/src/lib/httpBridge.ts services/python-core/tests/http_contract_helpers.py
git commit -m "Expose profile-first voice bridge payloads

Constraint: Desktop bridge method names should remain stable to preserve HTTP parity tests.
Rejected: Remove legacy voice take bridge methods now | It creates avoidable contract churn before UI migration is verified.
Confidence: high
Scope-risk: narrow
Directive: New UI should call createVoiceProfile with referenceText and renderAudio with requireVoiceProfile.
Tested: pnpm --dir apps/desktop check; PYTHONPATH=. .venv/bin/python -m unittest tests.test_http_bridge_parity tests.test_http_browser_desktop_parity
Not-tested: Tauri shell file chooser integration."
```

---

### Task 5: Simplify Voice Studio UI Around Profile Library

**Files:**
- Modify: `apps/desktop/src/pages/VoiceStudioPage.tsx`
- Modify: `apps/desktop/src/lib/shellOps.ts` only if an existing file picker helper is reused or added.

- [ ] **Step 1: Replace UI state with profile-first state**

In `VoiceStudioPage.tsx`, remove state that only supports temporary locks/takes:

```ts
const [previewPath, setPreviewPath] = useState("");
const [lastPreviewProvider, setLastPreviewProvider] = useState("");
const [lastPreviewModel, setLastPreviewModel] = useState("");
const [lastPreviewSettings, setLastPreviewSettings] = useState<VoiceRenderSettings | null>(null);
const [advancedOpen, setAdvancedOpen] = useState(false);
```

Add state for direct profile creation:

```ts
const [newProfileName, setNewProfileName] = useState("");
const [newProfileAudioPath, setNewProfileAudioPath] = useState("");
const [newProfileReferenceText, setNewProfileReferenceText] = useState("");
```

Keep `previewSrc`, `previewing`, `previewRequestState`, `rendering`, and `requestState`.

- [ ] **Step 2: Derive selected profile from script artifact**

Use this derived value:

```ts
const voiceReference = project?.artifact?.voice_reference;
const selectedProfile = voiceReference?.voice_profile_id
  ? voiceProfiles.find((profile) => profile.voice_profile_id === voiceReference.voice_profile_id)
  : undefined;
const selectedProfileReferenceText = selectedProfile?.reference_text || selectedProfile?.preview_text || "";
```

Use selected profile defaults for render settings:

```ts
const settings: VoiceRenderSettings = useMemo(
  () => ({
    voice_id: selectedProfile?.voice_id ?? "warm_narrator",
    voice_name: selectedProfile?.voice_name ?? selectedProfile?.name ?? "",
    style_id: selectedProfile?.style_id ?? "natural",
    style_name: selectedProfile?.style_name ?? "",
    speed: selectedProfile?.speed ?? 1,
    language: selectedProfile?.language ?? "zh",
    audio_format: selectedProfile?.audio_format ?? audioFormat,
    preview_text: effectivePreviewText,
  }),
  [audioFormat, effectivePreviewText, selectedProfile],
);
```

- [ ] **Step 3: Change preview handler to require a selected profile**

Replace `handlePreview` with:

```ts
const handlePreview = async () => {
  if (!selectedProfile) {
    setError("请先从音色库选择一个音色。");
    return;
  }
  try {
    setPreviewing(true);
    setError(null);
    setPreviewRequestState({
      operation: "render_voice_preview",
      phase: "running",
      progress_percent: 0,
      message: "Rendering voice preview...",
    });
    const result = await bridge.renderVoicePreview(settings, {
      onState: setPreviewRequestState,
      sessionId: selectedSessionId,
      scriptId: selectedScriptId,
      providerOverride,
      voiceProfileId: selectedProfile.voice_profile_id,
    });
    setPreviewRequestState(result.request_state ?? null);
    setPreviewSrc(resolveAudioFileUrl(result.audio_path));
    window.setTimeout(() => {
      void previewAudioRef.current?.play().catch(() => undefined);
    }, 100);
  } catch (err) {
    setError(getErrorMessage(err, "Failed to render preview."));
    setPreviewRequestState(null);
  } finally {
    setPreviewing(false);
  }
};
```

- [ ] **Step 4: Replace profile creation handler**

Replace `handleSaveVoiceProfile` with:

```ts
const handleCreateVoiceProfile = async () => {
  if (!newProfileName.trim()) {
    setError("请填写音色名称。");
    return;
  }
  if (!newProfileAudioPath.trim()) {
    setError("请填写或选择参考音频路径。");
    return;
  }
  if (!newProfileReferenceText.trim()) {
    setError("请填写参考音频中实际说出的文本。");
    return;
  }
  try {
    setError(null);
    const profile = await bridge.createVoiceProfile({
      name: newProfileName,
      audioPath: newProfileAudioPath,
      referenceText: newProfileReferenceText,
      provider: providerOverride || ttsConfig?.provider || "local_mlx",
      model: resolvedModel,
      language,
      audioFormat,
    });
    await refreshVoiceProfiles();
    if (selectedSessionId && selectedScriptId) {
      const updated = await bridge.selectVoiceProfile(selectedSessionId, selectedScriptId, profile.voice_profile_id);
      setProject(updated);
    }
    setNewProfileName("");
    setNewProfileAudioPath("");
    setNewProfileReferenceText("");
    setMessage(`已添加并选用「${profile.name}」。`);
  } catch (err) {
    setError(getErrorMessage(err, "Failed to create voice profile."));
  }
};
```

- [ ] **Step 5: Change full generation handler to use renderAudio**

Replace `handleRenderTake` with profile-first `handleRenderPodcast`:

```ts
const handleRenderPodcast = async () => {
  setError(null);
  setMessage(null);
  if (!selectedSessionId || !selectedScriptId) {
    setError("请先选择 Session 和脚本，再生成完整音频。");
    return;
  }
  if (!selectedProfile) {
    setError("请先从音色库选择一个音色。");
    return;
  }
  if (!renderEngineReady) {
    setError("当前本地语音模型尚未准备好。请先在 Models Center 下载或选择可用模型。");
    return;
  }
  if (!scriptText) {
    setError("当前脚本没有可生成的内容，请先选择包含正文的脚本。");
    return;
  }
  try {
    setRendering(true);
    const result = await bridge.renderAudio(selectedSessionId, {
      providerOverride,
      scriptId: selectedScriptId,
      voiceSettings: settings,
      requireVoiceProfile: true,
    });
    const state = result.request_state ?? {
      operation: "render_audio",
      phase: "running",
      progress_percent: 5,
      message: "Rendering podcast audio...",
    };
    setRequestState(state);
    startPolling(result.task_id ?? `render_audio:${selectedSessionId}`);
    setMessage("已开始使用当前音色生成播客音频。");
  } catch (err) {
    setRendering(false);
    setError(getErrorMessage(err, "Failed to render podcast audio."));
  }
};
```

Update cancel to use `render_audio:${selectedSessionId}`.

- [ ] **Step 6: Remove primary UI for lock and take comparison**

Remove buttons and sections that call:

```ts
handleLockPreview
handleSaveVoiceProfile
handleRenderTake
handleSetFinal
handleDeleteTake
```

Keep `handleDeleteVoiceProfile` and `handleSelectVoiceProfile`.

Render these three panels:

```tsx
<section>
  <h2>当前音色</h2>
  <p>{selectedProfile ? selectedProfile.name : "尚未选择音色"}</p>
  <button onClick={() => void handlePreview()} disabled={!selectedProfile || previewing}>试听 5 秒</button>
  <button onClick={() => void handleRenderPodcast()} disabled={!selectedProfile || rendering}>生成播客</button>
</section>

<section>
  <h2>音色库</h2>
  {voiceProfiles.map((profile) => (
    <button key={profile.voice_profile_id} onClick={() => void handleSelectVoiceProfile(profile)}>
      {profile.name}
    </button>
  ))}
</section>

<section>
  <h2>添加音色</h2>
  <input value={newProfileName} onChange={(event) => setNewProfileName(event.target.value)} />
  <input value={newProfileAudioPath} onChange={(event) => setNewProfileAudioPath(event.target.value)} />
  <textarea value={newProfileReferenceText} onChange={(event) => setNewProfileReferenceText(event.target.value)} />
  <button onClick={() => void handleCreateVoiceProfile()}>保存音色</button>
</section>
```

Adapt styling to the existing page classes rather than using these bare elements verbatim.

- [ ] **Step 7: Run frontend typecheck**

Run:

```bash
pnpm --dir apps/desktop check
```

Expected: pass.

- [ ] **Step 8: Commit**

```bash
git add apps/desktop/src/pages/VoiceStudioPage.tsx apps/desktop/src/lib/shellOps.ts
git commit -m "Simplify Voice Studio around voice profiles

Constraint: First stable release should avoid temporary locks and take comparison in the primary UI.
Rejected: Keep advanced Voice Studio controls visible | They preserve competing voice state and confuse the profile-first model.
Confidence: medium
Scope-risk: broad
Directive: Future voice controls must apply on top of a selected profile, not replace the profile anchor.
Tested: pnpm --dir apps/desktop check
Not-tested: Manual desktop audio preview and render flow."
```

---

### Task 6: Update Docs And Compatibility Tests

**Files:**
- Modify: `docs/product/product-overview.md`
- Modify: `docs/architecture/audio-rendering.md`
- Modify: `docs/architecture/tts-pipeline.md`
- Modify: `services/python-core/tests/test_bridge_request_state_schema.py`
- Modify: `services/python-core/tests/test_http_runtime.py`

- [ ] **Step 1: Update product overview**

In `docs/product/product-overview.md`, replace the Voice Studio bullet with:

```markdown
- **Voice Studio**: `/voice-studio/:sessionId/:scriptId` is the profile-first audio production space. Users select one built-in or user-saved voice profile, preview that profile with a short sample, and render the podcast using the same reference audio and reference text. Temporary preview locks and take comparison are no longer the primary workflow.
```

- [ ] **Step 2: Update architecture docs**

In `docs/architecture/audio-rendering.md`, replace references to "lock preview" as the main path with:

```markdown
Voice profiles are the canonical voice source for profile-first rendering. Selecting a profile writes a script-scoped `artifact.voice_reference` with `source: "voice_profile"`, `voice_profile_id`, profile `audio_path`, and reference text. Preview and full script render both pass that profile audio as `ref_audio` and the profile reference text as `ref_text` for local MLX/Qwen.
```

In `docs/architecture/tts-pipeline.md`, update the diagram edge label to:

```text
renderVoicePreview(profile) / selectVoiceProfile / renderAudio(profile-first)
```

- [ ] **Step 3: Update schema test expectations**

In `services/python-core/tests/test_bridge_request_state_schema.py`, update the voice profile schema assertion:

```python
for property_name in ["voice_profile_id", "name", "source", "audio_path", "preview_text", "reference_text", "provider", "model"]:
    self.assertIn(property_name, voice_profile["properties"])
```

- [ ] **Step 4: Run backend compatibility tests**

Run:

```bash
cd services/python-core
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_http_runtime \
  tests.test_audio_rendering \
  tests.test_local_mlx_tts \
  tests.test_bridge_request_state_schema
```

Expected: all tests pass.

- [ ] **Step 5: Run frontend check**

Run:

```bash
pnpm --dir apps/desktop check
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add docs/product/product-overview.md docs/architecture/audio-rendering.md docs/architecture/tts-pipeline.md services/python-core/tests/test_bridge_request_state_schema.py services/python-core/tests/test_http_runtime.py
git commit -m "Document profile-first voice rendering

Constraint: Docs must match product flow, architecture, and bridge schema.
Rejected: Leave lock-preview docs as primary guidance | It would send future work back to the unstable state model.
Confidence: high
Scope-risk: narrow
Directive: Treat profile selection as the canonical voice-source flow in future docs.
Tested: PYTHONPATH=. .venv/bin/python -m unittest tests.test_http_runtime tests.test_audio_rendering tests.test_local_mlx_tts tests.test_bridge_request_state_schema; pnpm --dir apps/desktop check
Not-tested: Packaged Tauri build."
```

---

### Task 7: Final Verification

**Files:**
- Read: changed files from Tasks 1-6.
- No planned source edits unless verification reveals failures.

- [ ] **Step 1: Run Python compile check**

Run:

```bash
cd services/python-core
PYTHONPATH=. .venv/bin/python -m py_compile \
  app/domain/voice_profile.py \
  app/storage/voice_profile_store.py \
  app/orchestration/audio_rendering.py \
  app/api/http_runtime.py \
  app/providers/tts_local_mlx/provider.py \
  app/providers/tts_local_mlx/runner.py \
  app/providers/tts_local_mlx/worker_client.py \
  app/providers/tts_local_mlx/mlx_worker.py
```

Expected: no output and exit code `0`.

- [ ] **Step 2: Run focused backend suite**

Run:

```bash
cd services/python-core
PYTHONPATH=. .venv/bin/python -m unittest \
  tests.test_http_runtime \
  tests.test_audio_rendering \
  tests.test_local_mlx_tts \
  tests.test_bridge_request_state_schema \
  tests.test_cli_voice_studio
```

Expected: all tests pass.

- [ ] **Step 3: Run frontend typecheck**

Run:

```bash
pnpm --dir apps/desktop check
```

Expected: pass.

- [ ] **Step 4: Run web build**

Run:

```bash
pnpm --dir apps/desktop build:web
```

Expected: Vite build succeeds.

- [ ] **Step 5: Inspect diff for accidental legacy UI references**

Run:

```bash
rg -n "锁定此试音音色|临时锁定|生成组合试音|Take 对比|当前只使用 Qwen|建议先锁定试音" apps/desktop/src docs/product docs/architecture -S
```

Expected: no matches. Compatibility references to legacy bridge methods may remain only when explicitly labeled legacy/deferred.

- [ ] **Step 6: Final commit if verification required fixes**

If Step 1-5 required fixes, commit them:

```bash
git add services/python-core/app/domain/voice_profile.py services/python-core/app/storage/voice_profile_store.py services/python-core/app/orchestration/audio_rendering.py services/python-core/app/api/http_runtime.py services/python-core/app/api/serializers.py services/python-core/app/providers/tts_local_mlx/provider.py services/python-core/app/providers/tts_local_mlx/runner.py services/python-core/app/providers/tts_local_mlx/worker_client.py services/python-core/app/providers/tts_local_mlx/mlx_worker.py services/python-core/tests/test_http_runtime.py services/python-core/tests/test_audio_rendering.py services/python-core/tests/test_local_mlx_tts.py services/python-core/tests/test_bridge_request_state_schema.py services/python-core/tests/test_cli_voice_studio.py apps/desktop/src/types.ts apps/desktop/src/lib/desktopBridge.ts apps/desktop/src/lib/httpBridge.ts apps/desktop/src/pages/VoiceStudioPage.tsx docs/product/product-overview.md docs/architecture/audio-rendering.md docs/architecture/tts-pipeline.md packages/shared-schemas/artifact.schema.json packages/shared-schemas/voice-profile.schema.json
git commit -m "Stabilize profile-first voice verification

Constraint: Verification found issues after the profile-first migration.
Rejected: Leave verification-only defects for later | They block a trustworthy handoff.
Confidence: high
Scope-risk: narrow
Directive: Keep final verification commands current when changing Voice Studio contracts.
Tested: PYTHONPATH=. .venv/bin/python -m py_compile app/domain/voice_profile.py app/storage/voice_profile_store.py app/orchestration/audio_rendering.py app/api/http_runtime.py app/providers/tts_local_mlx/provider.py app/providers/tts_local_mlx/runner.py app/providers/tts_local_mlx/worker_client.py app/providers/tts_local_mlx/mlx_worker.py; PYTHONPATH=. .venv/bin/python -m unittest tests.test_http_runtime tests.test_audio_rendering tests.test_local_mlx_tts tests.test_bridge_request_state_schema tests.test_cli_voice_studio; pnpm --dir apps/desktop check; pnpm --dir apps/desktop build:web
Not-tested: Native Tauri packaging."
```

---

## Self-Review

- Spec coverage: The plan covers profile creation, profile selection, profile-conditioned preview, profile-conditioned full render, simplified UI, docs, and tests. Deferred seed/crossfade/lock/take removal beyond UI is intentionally excluded by the approved spec.
- Placeholder scan: No task depends on unspecified files or unnamed tests. Legacy compatibility remains explicit and bounded.
- Type consistency: `referenceText` is the TypeScript input field, `reference_text` is the HTTP JSON field, and `preview_text` remains the backend compatibility storage field.
