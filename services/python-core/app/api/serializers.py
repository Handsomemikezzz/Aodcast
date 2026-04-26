from __future__ import annotations

from app.domain.project import SessionProject
from app.orchestration.audio_rendering import AudioRenderResult, VoiceRenderSettings, VoiceTakeRenderResult
from app.orchestration.interview_service import InterviewTurnResult
from app.orchestration.script_generation import ScriptGenerationResult, build_generation_context


def serialize_project(project: SessionProject) -> dict[str, object]:
    return {
        "session": project.session.to_dict(),
        "transcript": project.transcript.to_dict() if project.transcript else None,
        "script": project.script.to_dict() if project.script else None,
        "artifact": project.artifact.to_dict() if project.artifact else None,
    }


def serialize_turn_result(result: InterviewTurnResult) -> dict[str, object]:
    return {
        "project": serialize_project(result.project),
        "readiness": {
            "topic_context": result.readiness.topic_context,
            "core_viewpoint": result.readiness.core_viewpoint,
            "example_or_detail": result.readiness.example_or_detail,
            "conclusion": result.readiness.conclusion,
            "is_ready": result.readiness.is_ready,
            "missing_dimensions": result.readiness.missing_dimensions(),
        },
        "prompt_input": result.prompt_input.to_dict(),
        "next_question": result.next_question,
        "ai_can_finish": result.ai_can_finish,
    }


def serialize_generation_result(result: ScriptGenerationResult) -> dict[str, object]:
    project = result.project
    payload: dict[str, object] = {
        "project": serialize_project(project),
        "provider": result.provider,
        "model": result.model,
        "generation_context": build_generation_context(project),
    }
    if project.script is not None:
        payload["script_id"] = project.script.script_id
    return payload


def serialize_voice_take_result(result: VoiceTakeRenderResult) -> dict[str, object]:
    return {
        "project": serialize_project(result.project),
        "provider": result.provider,
        "model": result.model,
        "audio_path": result.audio_path,
        "transcript_path": result.transcript_path,
        "take": result.take.to_dict(),
    }


def serialize_audio_result(result: AudioRenderResult) -> dict[str, object]:
    return {
        "project": serialize_project(result.project),
        "provider": result.provider,
        "model": result.model,
        "audio_path": result.audio_path,
        "transcript_path": result.transcript_path,
    }


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


def serialize_voice_settings(settings: VoiceRenderSettings) -> dict[str, object]:
    return {
        "voice_id": settings.voice_id,
        "voice_name": settings.voice_name,
        "style_id": settings.style_id,
        "style_name": settings.style_name,
        "speed": settings.speed,
        "language": settings.language,
        "audio_format": settings.audio_format,
        "preview_text": settings.preview_text,
    }


def serialize_script_revisions(project: SessionProject) -> list[dict[str, object]]:
    if project.script is None:
        return []
    revisions: list[dict[str, object]] = []
    for revision in project.script.list_revisions():
        revisions.append(
            {
                "revision_id": revision.revision_id,
                "session_id": project.session.session_id,
                "content": revision.final or revision.draft,
                "kind": revision.reason,
                "label": revision.reason.replace("_", " "),
                "created_at": revision.created_at,
            }
        )
    return revisions
