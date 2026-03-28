from __future__ import annotations

from app.providers.llm.base import ScriptGenerationRequest, ScriptGenerationResponse


class MockLLMProvider:
    provider_name = "mock"
    model_name = "mock-solo-writer"

    def generate_script(self, request: ScriptGenerationRequest) -> ScriptGenerationResponse:
        transcript_lines = [
            line.strip()
            for line in request.transcript_text.splitlines()
            if line.strip()
        ]
        supporting_detail = transcript_lines[-1] if transcript_lines else "The interview transcript is still sparse."
        opening = (
            f"Today I want to talk about {request.topic.lower()} and why it matters right now."
        )
        body = (
            f"My core intent for this episode is: {request.creation_intent}. "
            f"One useful detail from the interview is: {supporting_detail}"
        )
        closing = (
            "If there is one takeaway from this conversation, it is that good tools "
            "should make complex work more understandable and recoverable."
        )
        draft = "\n\n".join(
            [
                "Opening",
                opening,
                "Body",
                body,
                "Closing",
                closing,
            ]
        )
        return ScriptGenerationResponse(
            draft=draft,
            provider_name=self.provider_name,
            model_name=self.model_name,
        )
