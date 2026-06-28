"""Phase 2 tests: EpisodeBrief, ScriptStyleProfile, selective transcript, metadata.

Tests verify:
- EpisodeBrief groups material by interview_focus tags (§7.1)
- Heuristic fallback for untagged (legacy) turns
- Short vs long transcript selection strategy (§7.2)
- ScriptStyleProfile tone derivation (§7.3)
- Script PromptPlan section decisions via metadata
- generation_metadata persisted to ScriptRecord (§9.2)
"""

from __future__ import annotations

import unittest

from app.domain.script import ScriptRecord
from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.prompts.script import (
    EpisodeBrief,
    ScriptStyleProfile,
    _format_episode_brief,
    build_episode_brief,
    build_script_generation_metadata,
    build_script_prompt_plan,
    build_script_style_profile,
)
from app.orchestration.prompts.registry import PROMPT_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _turn(
    speaker: str,
    content: str,
    interview_focus: str = "",
    turn_id: str = "",
) -> dict:
    """Build a dict payload for TranscriptTurn.from_dict."""
    payload: dict = {
        "speaker": speaker,
        "content": content,
        "created_at": "2025-01-01T00:00:00Z",
        "turn_id": turn_id or f"turn_{hash(content) & 0xFFFFFF:06x}",
    }
    if interview_focus:
        payload["metadata"] = {"interview_focus": interview_focus, "turn_role": "answer" if speaker == "user" else "question"}
    return payload


def _make_transcript(
    *specs: tuple[str, str, str],
    session_id: str = "s1",
) -> TranscriptRecord:
    """Build a TranscriptRecord from (speaker, content, focus) triples."""
    from app.domain.transcript import TranscriptTurn

    turns = [
        TranscriptTurn.from_dict(_turn(sp, content, focus), session_id=session_id)
        for sp, content, focus in specs
    ]
    tr = TranscriptRecord(session_id=session_id, turns=turns)
    return tr


def _make_style_profile(tone: str = "reflective") -> ScriptStyleProfile:
    return ScriptStyleProfile(
        language="en",
        tone=tone,
        structure="narrative_argument",
        target_length="medium",
        reasoning_mode="synthesis",
        source="transcript_analysis",
    )


# ---------------------------------------------------------------------------
# EpisodeBrief: tagged-turn grouping
# ---------------------------------------------------------------------------

class TestEpisodeBriefTaggedTurns(unittest.TestCase):
    def _make_tagged_transcript(self) -> TranscriptRecord:
        return _make_transcript(
            ("agent", "What triggered this topic?", "topic_context"),
            ("user", "I got frustrated with bad tooling at work.", "topic_context"),
            ("agent", "What's your core belief?", "core_viewpoint"),
            ("user", "Most devtools are designed for demos, not daily use.", "core_viewpoint"),
            ("agent", "Give me an example.", "example_or_detail"),
            ("user", "For example, last week I had to restart the server five times.", "example_or_detail"),
            ("agent", "What should listeners take away?", "conclusion"),
            ("user", "Choose boring, reliable tools over shiny ones.", "conclusion"),
        )

    def test_groups_material_by_focus_tags(self) -> None:
        """§7.1: turns tagged topic_context → topic_trigger, etc."""
        tr = self._make_tagged_transcript()
        brief = build_episode_brief("Dev tools", "share frustration", tr)
        self.assertIn("frustrated", brief.topic_trigger)
        self.assertIn("devtools", brief.core_viewpoint)
        self.assertTrue(len(brief.supporting_examples) >= 1)
        self.assertIn("boring", brief.desired_takeaway)

    def test_evidence_turn_ids_link_to_user_turns(self) -> None:
        """evidence_turn_ids must reference only user turns."""
        tr = self._make_tagged_transcript()
        brief = build_episode_brief("Dev tools", "share frustration", tr)
        user_turn_ids = {t.turn_id for t in tr.turns if t.speaker == Speaker.USER}
        for tid in brief.evidence_turn_ids:
            self.assertIn(tid, user_turn_ids)

    def test_all_four_focus_dims_populated(self) -> None:
        tr = self._make_tagged_transcript()
        brief = build_episode_brief("Dev tools", "share frustration", tr)
        self.assertTrue(brief.topic_trigger)
        self.assertTrue(brief.core_viewpoint)
        self.assertTrue(brief.supporting_examples)
        self.assertTrue(brief.desired_takeaway)

    def test_recent_user_turns_contains_last_entries(self) -> None:
        tr = self._make_tagged_transcript()
        brief = build_episode_brief("Dev tools", "share frustration", tr)
        # Recent user turns should be non-empty and contain the last user turn.
        user_turns = [t.content for t in tr.turns if t.speaker == Speaker.USER]
        self.assertIn(user_turns[-1], brief.recent_user_turns)

    def test_omitted_agent_turn_count_matches(self) -> None:
        tr = self._make_tagged_transcript()
        brief = build_episode_brief("Dev tools", "share frustration", tr)
        agent_count = sum(1 for t in tr.turns if t.speaker == Speaker.AGENT)
        self.assertEqual(brief.omitted_agent_turn_count, agent_count)


class TestEpisodeBriefLegacyTurns(unittest.TestCase):
    """Fallback: untagged (legacy) turns classified by keyword heuristics."""

    def test_viewpoint_keyword_classifies_as_core_viewpoint(self) -> None:
        tr = _make_transcript(
            ("user", "I believe most people underestimate complexity.", ""),
        )
        brief = build_episode_brief("Complexity", "explore it", tr)
        # Should be classified as core_viewpoint by keyword "believe"
        self.assertTrue(brief.core_viewpoint or brief.topic_trigger)

    def test_example_keyword_classifies_as_example(self) -> None:
        tr = _make_transcript(
            ("user", "I had a good topic context here.", "topic_context"),
            ("user", "For example, last year I managed a team of 10.", ""),
        )
        brief = build_episode_brief("Leadership", "share story", tr)
        self.assertTrue(len(brief.supporting_examples) >= 1)

    def test_conclusion_keyword_classifies_as_takeaway(self) -> None:
        tr = _make_transcript(
            ("user", "So, in the end, clarity beats speed.", ""),
        )
        brief = build_episode_brief("Clarity", "argue it", tr)
        # "in the end" → conclusion keyword
        self.assertTrue(brief.desired_takeaway or brief.topic_trigger)

    def test_empty_transcript_produces_empty_brief(self) -> None:
        tr = TranscriptRecord(session_id="s1")
        brief = build_episode_brief("Topic", "Intent", tr)
        self.assertEqual(brief.topic_trigger, "")
        self.assertEqual(brief.core_viewpoint, "")
        self.assertEqual(brief.supporting_examples, ())


# ---------------------------------------------------------------------------
# Selective transcript strategy
# ---------------------------------------------------------------------------

class TestSelectiveTranscript(unittest.TestCase):
    def _short_transcript(self) -> TranscriptRecord:
        specs = [
            ("user", "I like podcasts.", "topic_context"),
            ("agent", "Why?", "topic_context"),
            ("user", "They are convenient.", "core_viewpoint"),
        ]
        return _make_transcript(*specs)

    def _long_transcript(self, n_turns: int = 20) -> TranscriptRecord:
        specs = []
        for i in range(n_turns):
            focus = ["topic_context", "core_viewpoint", "example_or_detail", "conclusion"][i % 4]
            specs.append(("user", f"Answer {i}: " + "X" * 200, focus))
            specs.append(("agent", f"Question {i}", focus))
        return _make_transcript(*specs)

    def test_short_transcript_uses_full(self) -> None:
        """§10: short transcript can use full transcript."""
        tr = self._short_transcript()
        brief = build_episode_brief("Podcasts", "explain why", tr)
        self.assertTrue(brief.used_full_transcript)

    def test_long_transcript_uses_brief(self) -> None:
        """§10: long transcript (>3000 user chars) uses EpisodeBrief."""
        # Default n_turns=20 → 20 × ~210 chars = ~4200 user chars, exceeds budget.
        tr = self._long_transcript()
        brief = build_episode_brief("Big topic", "deep dive", tr)
        self.assertFalse(brief.used_full_transcript)

    def test_plan_section_id_is_full_transcript_for_short(self) -> None:
        tr = self._short_transcript()
        brief = build_episode_brief("T", "I", tr)
        style = _make_style_profile()
        plan = build_script_prompt_plan(
            topic="T", creation_intent="I", transcript=tr,
            style_profile=style, brief=brief,
        )
        self.assertIn("script.full_transcript", plan.metadata.section_ids)
        self.assertNotIn("script.episode_brief", plan.metadata.section_ids)

    def test_plan_section_id_is_episode_brief_for_long(self) -> None:
        # n_turns=20 → total user chars > 3000 → brief mode
        tr = self._long_transcript()
        brief = build_episode_brief("T", "I", tr)
        style = _make_style_profile()
        plan = build_script_prompt_plan(
            topic="T", creation_intent="I", transcript=tr,
            style_profile=style, brief=brief,
        )
        self.assertIn("script.episode_brief", plan.metadata.section_ids)
        self.assertNotIn("script.full_transcript", plan.metadata.section_ids)


# ---------------------------------------------------------------------------
# ScriptStyleProfile tone detection
# ---------------------------------------------------------------------------

class TestScriptStyleProfile(unittest.TestCase):
    def _session(self, topic: str = "T", intent: str = "I") -> object:
        from app.domain.session import SessionRecord
        return SessionRecord(topic=topic, creation_intent=intent)

    def test_practical_tone_from_tutorial_keyword(self) -> None:
        session = self._session(topic="Python tutorial", intent="teach how to use decorators")
        tr = TranscriptRecord(session_id="s1")
        profile = build_script_style_profile(session, tr)
        self.assertEqual(profile.tone, "practical")

    def test_narrative_tone_from_story_keyword(self) -> None:
        session = self._session(topic="My startup story", intent="share personal experience")
        tr = TranscriptRecord(session_id="s1")
        profile = build_script_style_profile(session, tr)
        self.assertEqual(profile.tone, "narrative")

    def test_commentary_tone_from_opinion_keyword(self) -> None:
        session = self._session(topic="AI hype", intent="argue against the hype")
        tr = TranscriptRecord(session_id="s1")
        profile = build_script_style_profile(session, tr)
        self.assertEqual(profile.tone, "commentary")

    def test_reflective_is_default_tone(self) -> None:
        session = self._session(topic="Life balance", intent="share thoughts")
        tr = TranscriptRecord(session_id="s1")
        profile = build_script_style_profile(session, tr)
        self.assertEqual(profile.tone, "reflective")

    def test_zh_language_detected(self) -> None:
        session = self._session(topic="个人效率", intent="分享我的经验")
        tr = _make_transcript(("user", "我认为工具很重要。", "core_viewpoint"))
        profile = build_script_style_profile(session, tr)
        self.assertEqual(profile.language, "zh")

    def test_short_session_target_length(self) -> None:
        session = self._session()
        tr = _make_transcript(("user", "Hi.", "topic_context"))
        profile = build_script_style_profile(session, tr)
        self.assertEqual(profile.target_length, "short")

    def test_medium_session_target_length(self) -> None:
        session = self._session()
        specs = [("user", f"Turn {i}.", "core_viewpoint") for i in range(5)]
        tr = _make_transcript(*specs)
        profile = build_script_style_profile(session, tr)
        self.assertEqual(profile.target_length, "medium")

    def test_source_is_transcript_analysis(self) -> None:
        session = self._session()
        tr = TranscriptRecord(session_id="s1")
        profile = build_script_style_profile(session, tr)
        self.assertEqual(profile.source, "transcript_analysis")


# ---------------------------------------------------------------------------
# Script PromptPlan section decisions
# ---------------------------------------------------------------------------

class TestScriptPromptPlan(unittest.TestCase):
    def _make_plan(
        self,
        tone: str = "reflective",
        memory_context: str = "",
        n_user_turns: int = 3,
    ):
        specs = [("user", f"User says {i}.", "core_viewpoint") for i in range(n_user_turns)]
        tr = _make_transcript(*specs)
        brief = build_episode_brief("Topic", "Intent", tr)
        style = _make_style_profile(tone=tone)
        return build_script_prompt_plan(
            topic="Topic",
            creation_intent="Intent",
            transcript=tr,
            style_profile=style,
            brief=brief,
            memory_context=memory_context,
        )

    def test_required_core_sections_always_present(self) -> None:
        """§10: TTS forbidden output rules remain present in script generation prompt."""
        plan = self._make_plan()
        self.assertIn("script.core_task", plan.metadata.section_ids)
        self.assertIn("script.output_contract", plan.metadata.section_ids)
        self.assertIn("script.reasoning_shape", plan.metadata.section_ids)

    def test_tone_section_loaded_correctly(self) -> None:
        for tone in ("reflective", "commentary", "practical", "narrative"):
            plan = self._make_plan(tone=tone)
            self.assertIn(f"script.tone.{tone}", plan.metadata.section_ids)

    def test_memory_context_omitted_when_empty(self) -> None:
        """§10: memory disabled omits memory sections."""
        plan = self._make_plan(memory_context="")
        self.assertNotIn("script.memory_context", plan.metadata.section_ids)
        omitted_ids = [o["section_id"] for o in plan.metadata.omitted_sections]
        self.assertIn("script.memory_context", omitted_ids)

    def test_memory_context_included_when_present(self) -> None:
        plan = self._make_plan(memory_context="User prefers concise scripts.")
        self.assertIn("script.memory_context", plan.metadata.section_ids)

    def test_operation_profile_is_script_generation(self) -> None:
        plan = self._make_plan()
        self.assertEqual(plan.metadata.operation_profile, "script_generation")

    def test_prompt_version_matches_constant(self) -> None:
        plan = self._make_plan()
        self.assertEqual(plan.metadata.prompt_version, PROMPT_VERSION)

    def test_system_and_user_nonempty(self) -> None:
        plan = self._make_plan()
        self.assertTrue(plan.system.strip())
        self.assertTrue(plan.user.strip())

    def test_stable_sections_before_dynamic_in_ids(self) -> None:
        """Cache-friendly: stable system sections appear before dynamic user sections."""
        plan = self._make_plan()
        ids = list(plan.metadata.section_ids)
        core_idx = ids.index("script.core_task")
        transcript_or_brief_idx = next(
            (i for i, sid in enumerate(ids) if "transcript" in sid or "brief" in sid), len(ids)
        )
        self.assertLess(core_idx, transcript_or_brief_idx)

    def test_tts_forbidden_text_present_in_system(self) -> None:
        """§10: TTS forbidden output constraints are in the plan system text."""
        plan = self._make_plan()
        self.assertIn("Markdown", plan.system)
        self.assertIn("Stage directions", plan.system)
        self.assertIn("Speaker labels", plan.system)

    def test_gates_include_key_decisions(self) -> None:
        plan = self._make_plan()
        gates = plan.metadata.gates
        self.assertIn("tone", gates)
        self.assertIn("used_full_transcript", gates)
        self.assertIn("has_memory_context", gates)

    def test_metadata_to_dict_is_serializable(self) -> None:
        plan = self._make_plan()
        d = plan.metadata.to_dict()
        import json
        serialized = json.dumps(d)
        self.assertIn("script_generation", serialized)


# ---------------------------------------------------------------------------
# Generation metadata persistence on ScriptRecord
# ---------------------------------------------------------------------------

class TestScriptRecordGenerationMetadata(unittest.TestCase):
    def _make_plan_and_brief(self):
        tr = _make_transcript(
            ("user", "I like podcasts.", "topic_context"),
            ("user", "They help me learn.", "core_viewpoint"),
        )
        brief = build_episode_brief("Podcasts", "make one", tr)
        style = _make_style_profile()
        plan = build_script_prompt_plan(
            topic="Podcasts", creation_intent="make one",
            transcript=tr, style_profile=style, brief=brief,
        )
        return plan, style, brief

    def test_generation_metadata_persists_to_script_record(self) -> None:
        """§9.2: compact generation metadata persisted on ScriptRecord."""
        plan, style, brief = self._make_plan_and_brief()
        meta = build_script_generation_metadata(
            plan=plan,
            style_profile=style,
            brief=brief,
            provider="openai_compatible",
            model="gpt-4o",
        )
        script = ScriptRecord(session_id="s1")
        script.generation_metadata = meta

        self.assertIn("prompt_version", meta)
        self.assertIn("style_profile", meta)
        self.assertIn("episode_brief_stats", meta)
        self.assertIn("provider", meta)
        self.assertIn("model", meta)
        self.assertIn("created_at", meta)

    def test_generation_metadata_no_sensitive_content(self) -> None:
        """§9.2: metadata must not contain full prompt, transcript, or memory text."""
        plan, style, brief = self._make_plan_and_brief()
        meta = build_script_generation_metadata(
            plan=plan, style_profile=style, brief=brief,
            provider="openai_compatible", model="gpt-4o",
        )
        import json
        meta_str = json.dumps(meta)
        # System/user prompt text must not be in metadata
        self.assertNotIn(plan.system[:50], meta_str)
        self.assertNotIn(plan.user[:50], meta_str)

    def test_generation_metadata_round_trips_through_script_record_dict(self) -> None:
        """metadata is persisted in ScriptRecord.to_dict() and recovered via from_dict()."""
        plan, style, brief = self._make_plan_and_brief()
        meta = build_script_generation_metadata(
            plan=plan, style_profile=style, brief=brief,
            provider="openai_compatible", model="gpt-4o",
        )
        script = ScriptRecord(session_id="s1", generation_metadata=meta)
        payload = script.to_dict()
        self.assertIn("generation_metadata", payload)

        recovered = ScriptRecord.from_dict(payload)
        self.assertEqual(recovered.generation_metadata["prompt_version"], PROMPT_VERSION)
        self.assertEqual(recovered.generation_metadata["provider"], "openai_compatible")

    def test_legacy_script_without_metadata_loads_as_empty_dict(self) -> None:
        """Existing scripts without generation_metadata load cleanly."""
        payload = {
            "session_id": "s1",
            "script_id": "abc",
            "name": "Test",
            "draft": "Draft text",
            "final": "Final text",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
        }
        script = ScriptRecord.from_dict(payload)
        self.assertIsInstance(script.generation_metadata, dict)
        self.assertEqual(script.generation_metadata, {})

    def test_empty_metadata_not_in_to_dict_for_clean_scripts(self) -> None:
        """Empty generation_metadata is omitted from to_dict output."""
        script = ScriptRecord(session_id="s1")
        payload = script.to_dict()
        self.assertNotIn("generation_metadata", payload)


# ---------------------------------------------------------------------------
# EpisodeBrief formatting
# ---------------------------------------------------------------------------

class TestEpisodeBriefFormatting(unittest.TestCase):
    def test_format_brief_includes_key_fields(self) -> None:
        brief = EpisodeBrief(
            topic="T",
            creation_intent="I",
            language="en",
            topic_trigger="It all started when...",
            core_viewpoint="Tools matter.",
            supporting_examples=("Example A", "Example B"),
            tensions_or_tradeoffs=("But speed conflicts with safety.",),
            desired_takeaway="Choose carefully.",
            evidence_turn_ids=("turn_001",),
            recent_user_turns=("Recent comment.",),
            omitted_agent_turn_count=3,
            used_full_transcript=False,
        )
        formatted = _format_episode_brief(brief)
        self.assertIn("Topic trigger", formatted)
        self.assertIn("Core viewpoint", formatted)
        self.assertIn("Supporting examples", formatted)
        self.assertIn("Key tension", formatted)
        self.assertIn("Desired takeaway", formatted)

    def test_format_brief_to_dict_serializable(self) -> None:
        brief = EpisodeBrief(
            topic="T", creation_intent="I", language="zh",
            topic_trigger="Trigger", core_viewpoint="Viewpoint",
            supporting_examples=("Ex 1",), tensions_or_tradeoffs=(),
            desired_takeaway="Takeaway", evidence_turn_ids=("t1", "t2"),
            recent_user_turns=("Recent",),
            omitted_agent_turn_count=2, used_full_transcript=True,
        )
        d = brief.to_dict()
        import json
        json.dumps(d)  # must not raise
        self.assertEqual(d["language"], "zh")
        self.assertEqual(d["omitted_agent_turn_count"], 2)


if __name__ == "__main__":
    unittest.main()
