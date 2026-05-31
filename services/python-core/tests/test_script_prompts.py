from __future__ import annotations

import unittest

from app.orchestration.prompts import (
    SCRIPT_GENERATION_SYSTEM_PROMPT,
    build_script_generation_user_prompt,
)


class ScriptPromptTests(unittest.TestCase):
    def test_system_prompt_forbids_production_markup(self) -> None:
        lowered = SCRIPT_GENERATION_SYSTEM_PROMPT.lower()
        self.assertIn("text-to-speech", lowered)
        self.assertIn("forbidden", lowered)
        self.assertIn("主播", SCRIPT_GENERATION_SYSTEM_PROMPT)

    def test_user_prompt_includes_transcript(self) -> None:
        content = build_script_generation_user_prompt(
            topic="执行力",
            creation_intent="solo reflection",
            transcript_text="user: I feel stuck.\nagent: What changed?",
        )
        self.assertIn("执行力", content)
        self.assertIn("user: I feel stuck.", content)


if __name__ == "__main__":
    unittest.main()
