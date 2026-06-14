from __future__ import annotations

from app.providers.llm.base import (
    InterviewQuestionRequest,
    ScriptGenerationRequest,
    ScriptGenerationResponse,
)
from typing import Iterator
import time


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
        draft = "\n\n".join([opening, body, closing])
        return ScriptGenerationResponse(
            draft=draft,
            provider_name=self.provider_name,
            model_name=self.model_name,
        )

    def _build_interview_question(self, request: InterviewQuestionRequest) -> str:
        if request.script_exists:
            reflection = (
                f"[mock interviewer] That addition will help shape a new script version for '{request.topic}'."
            )
            question = "What would you like to expand next for this revised episode?"
            options = (
                "A. Add a new concrete example\n"
                "B. Adjust the core argument\n"
                "C. Explain how you want this version to differ from the previous script"
            )
            recommendation = "I suggest starting with A, as fresh examples often sharpen the new draft. "
        else:
            focus = request.suggested_focus
            reflection = f"[mock interviewer] I hear you on '{request.topic}'."
            question = f"Let's focus on exploring your {focus} next."
            options = (
                f"A. Share a concrete detail or story about {focus}\n"
                f"B. Tell me how {focus} shapes your viewpoint\n"
                f"C. Focus on the final takeaway regarding {focus}"
            )
            recommendation = "I suggest starting with A, as a concrete example will ground the topic. "
        ignore_msg = "Of course, feel free to ignore these options and answer in your own way."

        return f"{reflection} {question}\n\n{options}\n\n{recommendation}{ignore_msg}"

    def stream_interview_question(self, request: InterviewQuestionRequest) -> Iterator[str]:
        full_response = self._build_interview_question(request)
        for word in full_response.split(" "):
            yield word + " "
            time.sleep(0.05)
