from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import AppConfig
from app.domain.project import SessionProject
from app.domain.provider_config import LLMProviderConfig
from app.domain.script import ScriptRecord
from app.domain.session import SessionRecord
from app.orchestration.speech_director import (
    RawSpeechSegment,
    SpeechDirectorService,
    build_speech_segment,
    split_script_for_speech,
)
from app.storage.config_store import ConfigStore


class SpeechPlanTests(unittest.TestCase):
    def test_director_preserves_script_text_and_builds_versioned_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = AppConfig.from_cwd(Path(tmp))
            config_store = ConfigStore(config.config_dir)
            config_store.bootstrap()
            config_store.save_llm_config(LLMProviderConfig(provider="mock"))
            session = SessionRecord(topic="自然表达", creation_intent="解释一个观点")
            script = ScriptRecord(
                session_id=session.session_id,
                final="我最近一直在想一个问题。我们真的需要这么着急吗？\n\n后来我慢慢意识到，答案并不复杂。",
            )
            project = SessionProject(session=session, script=script)

            plan = SpeechDirectorService(config_store).create_plan(project)

        self.assertEqual(plan.version, 1)
        self.assertTrue(plan.is_current_for(script.final))
        self.assertEqual("".join(segment.text for segment in plan.segments).replace("\n", ""), script.final.replace("\n", ""))
        self.assertGreaterEqual(plan.segments[-1].pause_after_ms, 500)
        self.assertEqual(plan.to_dict(), type(plan).from_dict(plan.to_dict()).to_dict())

    def test_context_window_rerenders_b_c_d_and_handles_edges(self) -> None:
        spans = split_script_for_speech(
            "第一段内容已经足够完整，可以独立表达一个清楚的判断。"
            "第二段内容同样足够完整，继续解释这个判断为什么重要。"
            "第三段继续说明问题，并且加入一个可以被听众记住的细节。"
            "第四段给出一个足够具体的例子，让抽象内容变得容易理解。"
            "第五段负责克制地收尾，并为听众保留一点继续思考的空间。"
        )
        self.assertEqual(len(spans), 5)

    def test_paragraph_boundaries_are_not_discarded(self) -> None:
        segments = split_script_for_speech("第一段有自己的呼吸。\n\n第二段重新开始。")
        self.assertEqual(len(segments), 2)
        self.assertTrue(segments[0].paragraph_end)
        self.assertTrue(segments[1].paragraph_end)

    def test_pathological_long_paragraph_is_split_into_renderable_segments(self) -> None:
        segments = split_script_for_speech("这是一个很长的分句，" * 80)

        self.assertGreater(len(segments), 1)
        self.assertTrue(all(len(item.text) <= 280 for item in segments))

    def test_ambiguous_anchors_and_overlapping_pronunciations_are_not_applied(self) -> None:
        text = "OpenAI 很重要，OpenAI 也需要被准确读出。"
        segment = build_speech_segment(
            "script-id",
            0,
            RawSpeechSegment(text=text, start=0, end=len(text), paragraph_end=True),
            {
                "breaks": [{"after_text": "OpenAI", "duration_ms": 500}],
                "pronunciations": [
                    {"text": "OpenAI", "spoken_as": "欧盆艾"},
                    {"text": "AI", "spoken_as": "诶爱"},
                ],
            },
        )

        self.assertEqual(segment.breaks, ())
        self.assertEqual(segment.pronunciations, ())

        unique_text = "OpenAI 很重要。"
        unique_segment = build_speech_segment(
            "script-id",
            0,
            RawSpeechSegment(
                text=unique_text,
                start=0,
                end=len(unique_text),
                paragraph_end=True,
            ),
            {
                "pronunciations": [
                    {"text": "OpenAI", "spoken_as": "欧盆艾"},
                    {"text": "AI", "spoken_as": "诶爱"},
                ],
            },
        )
        self.assertEqual(len(unique_segment.pronunciations), 1)
        self.assertEqual(unique_segment.pronunciations[0].spoken_as, "欧盆艾")


if __name__ == "__main__":
    unittest.main()
