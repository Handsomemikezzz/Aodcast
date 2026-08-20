from __future__ import annotations

import json
import re
import shutil
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

from app.domain.artifact import ArtifactRecord
from app.domain.common import sha256_text, utc_now_iso
from app.domain.episode_source import (
    EpisodeSource,
    SourceConversionMode,
    SourceImportKind,
    SourceTargetLength,
)
from app.domain.project import SessionProject
from app.domain.render_manifest import RenderManifest
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord, SessionState
from app.domain.speech_plan import SpeechPlan
from app.domain.transcript import TranscriptRecord


def _script_sort_key(script: ScriptRecord) -> str:
    return script.created_at


_SNAPSHOT_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _snapshot_file_name(record_id: str) -> str:
    cleaned = record_id.strip()
    if not _SNAPSHOT_ID.fullmatch(cleaned):
        raise ValueError("Snapshot ids may contain only letters, numbers, '_' and '-'.")
    return f"{cleaned}.json"


def _speaker_reference_snapshot(payload: dict[str, object] | None) -> dict[str, str] | None:
    if not payload:
        return None
    keys = (
        "speaker_reference_id",
        "reference_hash",
        "audio_path",
        "audio_hash",
        "reference_text",
        "language",
    )
    return {key: str(payload.get(key) or "") for key in keys}


class StaleRenderPublishError(RuntimeError):
    """Raised when a completed render no longer matches current project state."""


class ProjectStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.sessions_dir = self.data_dir / "sessions"
        self._source_lock = threading.RLock()
        self._project_lock = threading.RLock()

    def bootstrap(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def session_dir(self, session_id: str) -> Path:
        return self.sessions_dir / session_id

    def session_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "session.json"

    def transcript_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "transcript.json"

    def source_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "source.json"

    def source_versions_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "sources"

    def source_version_file(self, session_id: str, version: int) -> Path:
        return self.source_versions_dir(session_id) / f"v{version:04d}.json"

    def legacy_script_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "script.json"

    def scripts_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "scripts"

    def script_blob_file(self, session_id: str, script_id: str) -> Path:
        return self.scripts_dir(session_id) / f"{script_id}.json"

    def artifact_file(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "artifact.json"

    def speech_plans_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "speech-plans"

    def speech_plan_script_dir(self, session_id: str, script_id: str) -> Path:
        return self.speech_plans_dir(session_id) / script_id

    def speech_plan_file(self, session_id: str, script_id: str) -> Path:
        return self.speech_plan_script_dir(session_id, script_id) / "current.json"

    def speech_plan_version_file(self, session_id: str, script_id: str, plan_id: str) -> Path:
        return self.speech_plan_script_dir(session_id, script_id) / _snapshot_file_name(plan_id)

    def render_manifests_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "render-manifests"

    def render_manifest_script_dir(self, session_id: str, script_id: str) -> Path:
        return self.render_manifests_dir(session_id) / script_id

    def render_manifest_file(self, session_id: str, script_id: str) -> Path:
        return self.render_manifest_script_dir(session_id, script_id) / "current.json"

    def render_manifest_version_file(self, session_id: str, script_id: str, render_id: str) -> Path:
        return self.render_manifest_script_dir(session_id, script_id) / _snapshot_file_name(render_id)

    @contextmanager
    def _project_guard(self, session_id: str):
        with self._project_lock:
            if fcntl is None:
                yield
                return
            lock_path = self.session_dir(session_id) / ".project.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _write_json(self, path: Path, payload: dict[str, object]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f"{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
                temporary = Path(handle.name)
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path

    def _read_json(self, path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8"))

    def save_session(self, session: SessionRecord) -> Path:
        return self._write_json(self.session_file(session.session_id), session.to_dict())

    def load_session(self, session_id: str) -> SessionRecord:
        return SessionRecord.from_dict(self._read_json(self.session_file(session_id)))

    def save_transcript(self, transcript: TranscriptRecord) -> Path:
        return self._write_json(
            self.transcript_file(transcript.session_id),
            transcript.to_dict(),
        )

    def load_transcript(self, session_id: str) -> TranscriptRecord:
        return TranscriptRecord.from_dict(self._read_json(self.transcript_file(session_id)))

    def save_source(self, source: EpisodeSource) -> Path:
        with self._source_lock:
            current_path = self.source_file(source.session_id)
            if current_path.exists():
                current = EpisodeSource.from_dict(self._read_json(current_path))
                if current.version >= source.version:
                    return current_path
            payload = source.to_dict()
            self._write_json(self.source_version_file(source.session_id, source.version), payload)
            return self._write_json(current_path, payload)

    def replace_source(
        self,
        *,
        session_id: str,
        raw_markdown: str,
        name: str,
        import_kind: SourceImportKind,
        conversion_mode: SourceConversionMode,
        target_length: SourceTargetLength,
        focus_instructions: str,
    ) -> EpisodeSource:
        """Atomically allocate the next source version and persist its immutable snapshot."""
        with self._source_lock:
            previous = self.load_source(session_id)
            source = EpisodeSource.from_markdown(
                session_id=session_id,
                raw_markdown=raw_markdown,
                name=name,
                import_kind=import_kind,
                conversion_mode=conversion_mode,
                target_length=target_length,
                focus_instructions=focus_instructions,
                previous=previous,
            )
            payload = source.to_dict()
            self._write_json(self.source_version_file(session_id, source.version), payload)
            self._write_json(self.source_file(session_id), payload)
            return source

    def load_source(self, session_id: str) -> EpisodeSource:
        return EpisodeSource.from_dict(self._read_json(self.source_file(session_id)))

    def save_script(self, script: ScriptRecord) -> Path:
        """Persist a script to scripts/{script_id}.json."""
        return self._write_json(self.script_blob_file(script.session_id, script.script_id), script.to_dict())

    def load_script(self, session_id: str) -> ScriptRecord:
        """Deprecated single-file layout; use load_latest_script or load_script_by_id."""
        return ScriptRecord.from_dict(self._read_json(self.legacy_script_file(session_id)))

    def _maybe_migrate_legacy_script(self, session_id: str) -> None:
        legacy = self.legacy_script_file(session_id)
        if not legacy.exists():
            return
        bucket = self.scripts_dir(session_id)
        if bucket.exists() and any(bucket.glob("*.json")):
            return
        payload = self._read_json(legacy)
        payload["session_id"] = session_id
        if not payload.get("script_id"):
            payload["script_id"] = str(uuid4())
        if not payload.get("name"):
            try:
                session = self.load_session(session_id)
                topic = session.topic.strip() or "Untitled"
            except OSError:
                topic = "Untitled"
            ts = str(payload.get("updated_at") or payload.get("created_at") or utc_now_iso())
            payload["name"] = f"{topic}-{ts[:16].replace('T', ' ')}" if len(ts) >= 16 else f"{topic}-migrated"
        if not payload.get("created_at"):
            payload["created_at"] = payload.get("updated_at") or utc_now_iso()
        script = ScriptRecord.from_dict(payload)
        self._write_json(self.script_blob_file(session_id, script.script_id), script.to_dict())
        legacy.unlink()

    def list_scripts(self, session_id: str) -> list[ScriptRecord]:
        self._maybe_migrate_legacy_script(session_id)
        bucket = self.scripts_dir(session_id)
        if not bucket.exists():
            return []
        scripts: list[ScriptRecord] = []
        for path in sorted(bucket.glob("*.json")):
            scripts.append(ScriptRecord.from_dict(self._read_json(path)))
        scripts.sort(key=_script_sort_key, reverse=True)
        return scripts

    def load_script_by_id(self, session_id: str, script_id: str) -> ScriptRecord:
        self._maybe_migrate_legacy_script(session_id)
        path = self.script_blob_file(session_id, script_id)
        if not path.exists():
            raise ValueError(f"Unknown script_id '{script_id}' for session {session_id}.")
        return ScriptRecord.from_dict(self._read_json(path))

    def load_latest_script(self, session_id: str) -> ScriptRecord | None:
        scripts = self.list_scripts(session_id)
        return scripts[0] if scripts else None

    def save_artifact(self, artifact: ArtifactRecord) -> Path:
        return self._write_json(
            self.artifact_file(artifact.session_id),
            artifact.to_dict(),
        )

    def load_artifact(self, session_id: str) -> ArtifactRecord:
        return ArtifactRecord.from_dict(self._read_json(self.artifact_file(session_id)))

    def save_speech_plan(self, plan: SpeechPlan) -> Path:
        payload = plan.to_dict()
        version_path = self.speech_plan_version_file(plan.session_id, plan.script_id, plan.plan_id)
        self._write_immutable_json(version_path, payload)
        return self._write_json(self.speech_plan_file(plan.session_id, plan.script_id), payload)

    def load_speech_plan(self, session_id: str, script_id: str) -> SpeechPlan:
        return SpeechPlan.from_dict(self._read_json(self.speech_plan_file(session_id, script_id)))

    def save_render_manifest(self, manifest: RenderManifest) -> Path:
        payload = manifest.to_dict()
        version_path = self.render_manifest_version_file(
            manifest.session_id,
            manifest.script_id,
            manifest.render_id,
        )
        self._write_immutable_json(version_path, payload)
        return self._write_json(self.render_manifest_file(manifest.session_id, manifest.script_id), payload)

    def load_render_manifest(self, session_id: str, script_id: str) -> RenderManifest:
        return RenderManifest.from_dict(self._read_json(self.render_manifest_file(session_id, script_id)))

    def load_render_manifest_version(self, session_id: str, script_id: str, render_id: str) -> RenderManifest:
        return RenderManifest.from_dict(
            self._read_json(self.render_manifest_version_file(session_id, script_id, render_id))
        )

    def list_render_manifests(self, session_id: str, script_id: str) -> list[RenderManifest]:
        directory = self.render_manifest_script_dir(session_id, script_id)
        if not directory.exists():
            return []
        manifests = [
            RenderManifest.from_dict(self._read_json(path))
            for path in sorted(directory.glob("*.json"))
            if path.name != "current.json"
        ]
        manifests.sort(key=lambda item: item.created_at)
        return manifests

    def count_speaker_reference_dependencies(self, speaker_reference_id: str) -> int:
        cleaned = speaker_reference_id.strip()
        if not cleaned:
            return 0
        dependencies: set[tuple[str, str, str]] = set()
        for artifact_path in self.sessions_dir.glob("*/artifact.json"):
            try:
                artifact = ArtifactRecord.from_dict(self._read_json(artifact_path))
            except (OSError, KeyError, TypeError, ValueError):
                continue
            session_id = artifact.session_id
            matched_script_selection = False
            for script_id, payload in artifact.script_artifacts.items():
                reference = payload.get("speaker_reference")
                if isinstance(reference, dict) and str(reference.get("speaker_reference_id") or "") == cleaned:
                    dependencies.add(("selection", session_id, script_id))
                    matched_script_selection = True
            top_reference = artifact.speaker_reference or {}
            if not matched_script_selection and str(top_reference.get("speaker_reference_id") or "") == cleaned:
                dependencies.add(("selection", session_id, "current"))
        for path in self.sessions_dir.glob("*/render-manifests/*/*.json"):
            if path.name == "current.json":
                continue
            try:
                manifest = RenderManifest.from_dict(self._read_json(path))
            except (OSError, KeyError, TypeError, ValueError):
                continue
            reference = manifest.speaker_reference or {}
            if str(reference.get("speaker_reference_id") or "") == cleaned:
                dependencies.add(("render", manifest.session_id, manifest.render_id))
        return len(dependencies)

    def delete_render_manifest(self, session_id: str, script_id: str) -> None:
        directory = self.render_manifest_script_dir(session_id, script_id)
        if directory.exists():
            shutil.rmtree(directory)

    def _write_immutable_json(self, path: Path, payload: dict[str, object]) -> Path:
        if path.exists():
            if self._read_json(path) != payload:
                raise ValueError(f"Immutable snapshot already exists with different content: {path.name}")
            return path
        return self._write_json(path, payload)

    def save_project(self, project: SessionProject) -> None:
        with self._project_guard(project.session.session_id):
            self.save_session(project.session)
            if project.source is not None:
                self.save_source(project.source)
            if project.transcript is not None:
                self.save_transcript(project.transcript)
            if project.script is not None:
                self.save_script(project.script)
            if project.speech_plan is not None:
                self.save_speech_plan(project.speech_plan)
            if project.render_manifest is not None:
                self.save_render_manifest(project.render_manifest)
            if project.artifact is not None:
                self.save_artifact(project.artifact)

    def save_script_and_session(self, session: SessionRecord, script: ScriptRecord) -> None:
        if session.session_id != script.session_id:
            raise ValueError("Script and session ids must match.")
        with self._project_guard(session.session_id):
            self.save_session(session)
            self.save_script(script)

    def update_script_audio_preferences(
        self,
        session_id: str,
        script_id: str,
        *,
        voice_settings: dict[str, object] | None = None,
        speaker_reference: dict[str, object] | None = None,
        replace_speaker_reference: bool = False,
    ) -> ArtifactRecord:
        with self._project_guard(session_id):
            if self.artifact_file(session_id).exists():
                artifact = self.load_artifact(session_id).for_script(script_id)
            else:
                artifact = ArtifactRecord(
                    session_id=session_id,
                    transcript_path=f"sessions/{session_id}/transcript.json",
                    active_script_id=script_id,
                )
            if voice_settings is not None:
                artifact.voice_settings = dict(voice_settings)
            if replace_speaker_reference:
                artifact.speaker_reference = (
                    dict(speaker_reference) if speaker_reference is not None else None
                )
            self.save_artifact(artifact)
            return artifact

    def begin_audio_render(self, session_id: str) -> SessionState:
        with self._project_guard(session_id):
            session = self.load_session(session_id)
            if session.state == SessionState.AUDIO_RENDERING:
                raise ValueError("Cannot render audio while another audio render is already in progress.")
            previous_state = session.state
            session.transition(SessionState.AUDIO_RENDERING)
            self.save_session(session)
            return previous_state

    def restore_after_audio_render(
        self,
        session_id: str,
        *,
        previous_state: SessionState,
        error_message: str = "",
    ) -> SessionRecord:
        with self._project_guard(session_id):
            session = self.load_session(session_id)
            if session.state == SessionState.AUDIO_RENDERING:
                session.transition(previous_state)
            if error_message.strip():
                session.record_error(error_message.strip())
            self.save_session(session)
            return session

    def publish_render(
        self,
        rendered: SessionProject,
        *,
        expected_script_hash: str,
        expected_active_render_id: str,
        tts_provider: str,
        next_session_state: SessionState,
    ) -> SessionProject:
        """Atomically publish only render-owned fields after a final state check.

        The renderer works on a detached project snapshot. Re-reading here
        prevents a long-running job from overwriting script edits, reference
        selection, or another render that completed while it was running.
        """

        if rendered.script is None or rendered.speech_plan is None or rendered.render_manifest is None:
            raise ValueError("A render publication requires script, Speech Plan, and Render Manifest.")
        if rendered.artifact is None:
            raise ValueError("A render publication requires artifact metadata.")
        session_id = rendered.session.session_id
        script_id = rendered.script.script_id
        with self._project_guard(session_id):
            current = self.load_project_for_script(session_id, script_id)
            if current.script is None:
                raise StaleRenderPublishError("The rendered script no longer exists.")
            current_text = current.script.final.strip() or current.script.draft.strip()
            if sha256_text(current_text) != expected_script_hash:
                raise StaleRenderPublishError(
                    "The script changed while audio was rendering. The completed audio was not published."
                )
            current_render_id = current.render_manifest.render_id if current.render_manifest else ""
            if current_render_id != expected_active_render_id:
                raise StaleRenderPublishError(
                    "A newer render became active while audio was rendering. The older result was not published."
                )
            current_reference = _speaker_reference_snapshot(
                current.artifact.speaker_reference if current.artifact else None
            )
            if current_reference != rendered.render_manifest.speaker_reference:
                raise StaleRenderPublishError(
                    "The Speaker Reference changed while audio was rendering. The completed audio was not published."
                )
            if rendered.speech_plan.script_hash != expected_script_hash:
                raise ValueError("Speech Plan does not match the rendered script hash.")
            if rendered.render_manifest.script_hash != expected_script_hash:
                raise ValueError("Render Manifest does not match the rendered script hash.")

            target_artifact = current.artifact or ArtifactRecord(
                session_id=session_id,
                active_script_id=script_id,
            )
            source_artifact = rendered.artifact
            target_artifact.transcript_path = source_artifact.transcript_path
            target_artifact.audio_path = source_artifact.audio_path
            target_artifact.provider = source_artifact.provider
            target_artifact.takes = list(source_artifact.takes)
            target_artifact.final_take_id = source_artifact.final_take_id
            target_artifact.voice_settings = dict(source_artifact.voice_settings)

            current.speech_plan = rendered.speech_plan
            current.render_manifest = rendered.render_manifest
            current.artifact = target_artifact
            current.session.tts_provider = tts_provider
            current.session.transition(next_session_state)
            self.save_speech_plan(current.speech_plan)
            self.save_render_manifest(current.render_manifest)
            self.save_artifact(current.artifact)
            self.save_session(current.session)
            return current

    def load_project(self, session_id: str) -> SessionProject:
        session = self.load_session(session_id)
        source = None
        transcript = None
        artifact = None

        transcript_path = self.transcript_file(session_id)
        source_path = self.source_file(session_id)
        artifact_path = self.artifact_file(session_id)

        if source_path.exists():
            source = self.load_source(session_id)
        if transcript_path.exists():
            transcript = self.load_transcript(session_id)
        script = self.load_latest_script(session_id)
        if artifact_path.exists():
            artifact = self.load_artifact(session_id)
            if script is not None:
                artifact = artifact.for_script(script.script_id)

        speech_plan = None
        render_manifest = None
        if script is not None:
            speech_plan_path = self.speech_plan_file(session_id, script.script_id)
            render_manifest_path = self.render_manifest_file(session_id, script.script_id)
            if speech_plan_path.exists():
                speech_plan = self.load_speech_plan(session_id, script.script_id)
            if render_manifest_path.exists():
                render_manifest = self.load_render_manifest(session_id, script.script_id)
            if render_manifest is not None and artifact is not None and artifact.final_take_id != render_manifest.render_id:
                render_manifest = None

        return SessionProject(
            session=session,
            source=source,
            transcript=transcript,
            script=script,
            artifact=artifact,
            speech_plan=speech_plan,
            render_manifest=render_manifest,
        )

    def load_project_for_script(self, session_id: str, script_id: str) -> SessionProject:
        session = self.load_session(session_id)
        source = None
        transcript = None
        artifact = None
        if self.source_file(session_id).exists():
            source = self.load_source(session_id)
        if self.transcript_file(session_id).exists():
            transcript = self.load_transcript(session_id)
        script = self.load_script_by_id(session_id, script_id)
        if self.artifact_file(session_id).exists():
            artifact = self.load_artifact(session_id)
            artifact = artifact.for_script(script.script_id)
        speech_plan = None
        render_manifest = None
        if self.speech_plan_file(session_id, script.script_id).exists():
            speech_plan = self.load_speech_plan(session_id, script.script_id)
        if self.render_manifest_file(session_id, script.script_id).exists():
            render_manifest = self.load_render_manifest(session_id, script.script_id)
        if render_manifest is not None and artifact is not None and artifact.final_take_id != render_manifest.render_id:
            render_manifest = None
        return SessionProject(
            session=session,
            source=source,
            transcript=transcript,
            script=script,
            artifact=artifact,
            speech_plan=speech_plan,
            render_manifest=render_manifest,
        )

    def list_sessions(
        self,
        *,
        include_deleted: bool = False,
        search_query: str = "",
    ) -> list[SessionRecord]:
        if not self.sessions_dir.exists():
            return []
        query_value = search_query.strip().lower()
        sessions: list[SessionRecord] = []
        for session_file in sorted(self.sessions_dir.glob("*/session.json")):
            session = SessionRecord.from_dict(self._read_json(session_file))
            if not include_deleted and session.is_deleted():
                continue
            if query_value and query_value not in f"{session.topic} {session.creation_intent}".lower():
                continue
            sessions.append(session)
        return sessions

    def list_projects(
        self,
        *,
        include_deleted: bool = False,
        search_query: str = "",
    ) -> list[SessionProject]:
        return [
            SessionProject(
                session=session,
                source=None,
                transcript=None,
                script=None,
                artifact=None,
            )
            for session in self.list_sessions(
                include_deleted=include_deleted,
                search_query=search_query,
            )
        ]
