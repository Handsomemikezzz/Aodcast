from __future__ import annotations

from dataclasses import dataclass

from app.domain.project import SessionProject
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
        script = project.script
        if transcript is None:
            raise ValueError("Cannot generate a script without a transcript.")
        if script is None:
            raise ValueError("Cannot generate a script without a script record.")
        if project.session.state not in (SessionState.READY_TO_GENERATE, SessionState.FAILED):
            raise ValueError(
                f"Session must be in ready_to_generate or failed state before script generation, got '{project.session.state.value}'."
            )

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

        try:
            response = provider.generate_script(request)
        except Exception as exc:
            project.session.set_error(str(exc))
            self.store.save_project(project)
            raise

        script.update_draft(response.draft)
        if (not script.final.strip()) or script.final == "Draft script pending real generation.":
            script.update_final(response.draft)

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
