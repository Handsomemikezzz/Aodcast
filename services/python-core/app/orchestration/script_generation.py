from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.domain.common import utc_now_iso
from app.domain.project import SessionProject
from app.domain.script import ScriptRecord
from app.domain.session import SessionState
from app.orchestration.prompts import build_prompt_input
from app.orchestration.readiness import evaluate_readiness
from app.providers.llm.base import ScriptGenerationRequest
from app.providers.llm.factory import build_llm_provider
from app.storage.config_store import ConfigStore
from app.storage.project_store import ProjectStore


@dataclass(frozen=True, slots=True)
class ScriptGenerationResult:
    project: SessionProject
    provider: str
    model: str


class ScriptGenerationService:
    def __init__(self, store: ProjectStore, config_store: ConfigStore) -> None:
        self.store = store
        self.config_store = config_store

    def generate_draft(
        self,
        session_id: str,
        *,
        override_provider: str = "",
    ) -> ScriptGenerationResult:
        project = self.store.load_project(session_id)
        transcript = project.transcript
        if transcript is None:
            raise ValueError("Cannot generate a script without a transcript.")
        if project.session.state == SessionState.AUDIO_RENDERING:
            raise ValueError("Cannot generate a script while audio rendering is in progress.")

        llm_config = self.config_store.load_llm_config()
        if override_provider:
            llm_config.provider = override_provider

        provider = build_llm_provider(llm_config)
        request = ScriptGenerationRequest(
            session_id=session_id,
            topic=project.session.topic,
            creation_intent=project.session.creation_intent,
            transcript_text=_transcript_text(transcript),
        )

        script = ScriptRecord(
            session_id=session_id,
            script_id=str(uuid4()),
            name=_format_new_script_name(project.session.topic),
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )

        try:
            response = provider.generate_script(request)
        except Exception as exc:
            project.session.set_error(str(exc))
            self.store.save_project(project)
            raise

        script.replace_with_generated_draft(response.draft)
        project.script = script

        project.session.llm_provider = response.provider_name
        project.session.transition(SessionState.SCRIPT_GENERATED)
        self.store.save_project(project)
        return ScriptGenerationResult(
            project=project,
            provider=response.provider_name,
            model=response.model_name,
        )


def build_generation_context(project: SessionProject) -> dict[str, object]:
    if project.transcript is None:
        raise ValueError("Project transcript is required.")
    readiness = evaluate_readiness(project.transcript)
    prompt_input = build_prompt_input(project.session, project.transcript, readiness)
    return {
        "transcript_text": _transcript_text(project.transcript),
        "readiness": {
            "is_ready": readiness.is_ready,
            "missing_dimensions": readiness.missing_dimensions(),
        },
        "prompt_input": prompt_input.to_dict(),
    }


def _transcript_text(transcript) -> str:
    return "\n".join(f"{turn.speaker.value}: {turn.content}" for turn in transcript.turns)


def _format_new_script_name(topic: str) -> str:
    local = datetime.now().astimezone()
    # Second precision so back-to-back generations in the same minute get distinct labels.
    stamp = local.strftime("%Y-%m-%d %H:%M:%S")
    base = (topic or "").strip() or "Untitled"
    return f"{base}-{stamp}"
