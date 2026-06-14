from __future__ import annotations

import unittest

from app.orchestration.prompts import (
    INTERVIEW_STREAM_SYSTEM_PROMPT,
    SCRIPT_GENERATION_SYSTEM_PROMPT,
    build_interview_stream_instructions,
    build_interview_stream_user_content,
    build_script_generation_user_prompt,
)


class ScriptPromptTests(unittest.TestCase):
    def test_system_prompt_forbids_production_markup(self) -> None:
        lowered = SCRIPT_GENERATION_SYSTEM_PROMPT.lower()
        self.assertIn("text-to-speech", lowered)
        self.assertIn("forbidden", lowered)
        self.assertIn("主播", SCRIPT_GENERATION_SYSTEM_PROMPT)
        self.assertIn("essay", lowered)
        self.assertIn("tension", lowered)
        self.assertIn("outline", lowered)
        self.assertIn("synthes", lowered)
        self.assertIn("logical", lowered)
        self.assertIn("concrete example", lowered)
        self.assertIn("do not output these outline labels", lowered)
        self.assertIn("markdown", lowered)

    def test_user_prompt_includes_transcript(self) -> None:
        content = build_script_generation_user_prompt(
            topic="执行力",
            creation_intent="solo reflection",
            transcript_text="user: I feel stuck.\nagent: What changed?",
        )
        self.assertIn("执行力", content)
        self.assertIn("user: I feel stuck.", content)

    def test_interview_stream_system_prompt_requires_abc_structure(self) -> None:
        lowered = INTERVIEW_STREAM_SYSTEM_PROMPT.lower()
        self.assertIn("a, b, and c", lowered)
        self.assertIn("recommend", lowered)
        self.assertIn("respond freely", lowered)

    def test_interview_stream_instructions_vary_by_script_exists(self) -> None:
        instructions_no_script = build_interview_stream_instructions(
            script_exists=False,
            suggested_focus="topic_context",
        )
        self.assertIn("topic_context", instructions_no_script)
        self.assertIn("A, B, and C", instructions_no_script)
        self.assertIn("Recommend one option", instructions_no_script)
        self.assertIn("ignore the options", instructions_no_script)

        instructions_with_script = build_interview_stream_instructions(
            script_exists=True,
            suggested_focus="ready_to_generate",
        )
        self.assertIn("NEW script version", instructions_with_script)
        self.assertIn("A. Add a new concrete example", instructions_with_script)
        self.assertNotIn("Priority dimension to explore next", instructions_with_script)

    def test_interview_stream_user_content_embeds_instructions(self) -> None:
        content = build_interview_stream_user_content(
            topic="Local tools",
            creation_intent="Explain a workflow",
            missing_dimensions=["example_or_detail"],
            transcript_text="user: I rebuilt my setup locally.",
            script_exists=False,
            suggested_focus="example_or_detail",
        )
        self.assertIn("Session topic: Local tools", content)
        self.assertIn("example_or_detail", content)
        self.assertIn("A, B, and C", content)
        self.assertIn("Do not write the podcast script.", content)


if __name__ == "__main__":
    unittest.main()
