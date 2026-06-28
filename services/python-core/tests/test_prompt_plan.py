"""Phase 1 tests for the PromptPlan assembly layer.

Tests verify section decisions via metadata, not fragile full prompt text.
See design doc §10 (Testing Contract) and §14 (Acceptance Criteria).
"""

from __future__ import annotations

import unittest

from app.domain.transcript import Speaker, TranscriptRecord, TranscriptTurn
from app.orchestration.prompts.interview import (
    build_interview_prompt_plan,
    _determine_option_mode,
    _resolve_focus,
)
from app.orchestration.prompts.registry import (
    PROMPT_VERSION,
    CachePolicy,
    PromptPlan,
    PromptPlanMetadata,
    PromptSection,
    assemble_plan,
)
from app.orchestration.readiness import ReadinessReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _readiness(
    topic_context: bool = True,
    core_viewpoint: bool = True,
    example_or_detail: bool = True,
    conclusion: bool = True,
) -> ReadinessReport:
    return ReadinessReport(
        topic_context=topic_context,
        core_viewpoint=core_viewpoint,
        example_or_detail=example_or_detail,
        conclusion=conclusion,
    )


def _empty_transcript(session_id: str = "s1") -> TranscriptRecord:
    return TranscriptRecord(session_id=session_id)


def _transcript_with_turns(
    *turn_specs: tuple[str, str],
    session_id: str = "s1",
) -> TranscriptRecord:
    """Build a transcript from (speaker, content) pairs."""
    tr = TranscriptRecord(session_id=session_id)
    for speaker_str, content in turn_specs:
        tr.append(Speaker(speaker_str), content)
    return tr


def _make_plan(
    readiness: ReadinessReport | None = None,
    transcript: TranscriptRecord | None = None,
    script_exists: bool = False,
    memory_context: str = "",
) -> PromptPlan:
    r = readiness or _readiness(topic_context=False)
    tr = transcript or _empty_transcript()
    return build_interview_prompt_plan(
        topic="Test topic",
        creation_intent="Test intent",
        transcript=tr,
        readiness=r,
        script_exists=script_exists,
        memory_context=memory_context,
        transcript_text="agent: Hello\nuser: Hi",
    )


# ---------------------------------------------------------------------------
# Registry unit tests
# ---------------------------------------------------------------------------

class TestPromptSection(unittest.TestCase):
    def test_section_attributes(self) -> None:
        sec = PromptSection(
            section_id="test.section",
            content="Hello world",
            cache_policy=CachePolicy.STABLE,
            required=True,
        )
        self.assertEqual(sec.section_id, "test.section")
        self.assertEqual(sec.cache_policy, CachePolicy.STABLE)
        self.assertTrue(sec.required)

    def test_cache_policy_values(self) -> None:
        self.assertEqual(CachePolicy.STABLE.value, "stable")
        self.assertEqual(CachePolicy.SESSION_STABLE.value, "session_stable")
        self.assertEqual(CachePolicy.DYNAMIC.value, "dynamic")
        self.assertEqual(CachePolicy.PRIVATE_DYNAMIC.value, "private_dynamic")


class TestAssemblePlan(unittest.TestCase):
    def test_empty_sections_produce_empty_strings(self) -> None:
        plan = assemble_plan(
            operation_profile="test",
            system_sections=[],
            user_sections=[],
        )
        self.assertEqual(plan.system, "")
        self.assertEqual(plan.user, "")
        self.assertEqual(plan.metadata.section_ids, ())

    def test_sections_joined_with_blank_line(self) -> None:
        s1 = PromptSection("s1", "Line A", CachePolicy.STABLE)
        s2 = PromptSection("s2", "Line B", CachePolicy.DYNAMIC)
        plan = assemble_plan(
            operation_profile="test",
            system_sections=[s1, s2],
            user_sections=[],
        )
        self.assertIn("Line A\n\nLine B", plan.system)

    def test_metadata_section_ids_stable(self) -> None:
        s1 = PromptSection("alpha", "A", CachePolicy.STABLE)
        s2 = PromptSection("beta", "B", CachePolicy.DYNAMIC)
        plan = assemble_plan(
            operation_profile="test",
            system_sections=[s1],
            user_sections=[s2],
        )
        self.assertEqual(plan.metadata.section_ids, ("alpha", "beta"))
        self.assertEqual(plan.metadata.cacheable_section_ids, ("alpha",))
        self.assertEqual(plan.metadata.dynamic_section_ids, ("beta",))

    def test_char_count_matches_combined_text(self) -> None:
        s = PromptSection("s1", "ABC", CachePolicy.STABLE)
        u = PromptSection("u1", "DEF", CachePolicy.DYNAMIC)
        plan = assemble_plan(
            operation_profile="test",
            system_sections=[s],
            user_sections=[u],
        )
        self.assertEqual(plan.metadata.char_count, len(plan.system) + len(plan.user))

    def test_gates_and_omissions_persisted(self) -> None:
        plan = assemble_plan(
            operation_profile="test",
            system_sections=[],
            user_sections=[],
            gates={"option_mode": "abc", "script_exists": False},
            omitted_sections=[{"section_id": "memory_context", "reason": "empty"}],
        )
        self.assertEqual(plan.metadata.gates["option_mode"], "abc")
        self.assertEqual(len(plan.metadata.omitted_sections), 1)
        self.assertEqual(plan.metadata.omitted_sections[0]["section_id"], "memory_context")

    def test_metadata_to_dict_serializable(self) -> None:
        plan = _make_plan()
        d = plan.metadata.to_dict()
        self.assertIn("prompt_version", d)
        self.assertIn("section_ids", d)
        self.assertIsInstance(d["section_ids"], list)


# ---------------------------------------------------------------------------
# Interview profile: focus section selection
# ---------------------------------------------------------------------------

class TestFocusSectionSelection(unittest.TestCase):
    def test_missing_topic_context_loads_focus_topic_context(self) -> None:
        """§10: interview_followup missing topic_context loads only focus.topic_context."""
        r = _readiness(topic_context=False, core_viewpoint=True, example_or_detail=True, conclusion=True)
        plan = _make_plan(readiness=r)
        self.assertIn("focus.topic_context", plan.metadata.section_ids)
        self.assertNotIn("focus.core_viewpoint", plan.metadata.section_ids)
        self.assertNotIn("focus.example_or_detail", plan.metadata.section_ids)
        self.assertNotIn("focus.conclusion", plan.metadata.section_ids)

    def test_missing_core_viewpoint_loads_correct_focus(self) -> None:
        r = _readiness(topic_context=True, core_viewpoint=False, example_or_detail=True, conclusion=True)
        plan = _make_plan(readiness=r)
        self.assertIn("focus.core_viewpoint", plan.metadata.section_ids)
        self.assertNotIn("focus.topic_context", plan.metadata.section_ids)

    def test_missing_example_or_detail_loads_correct_focus(self) -> None:
        r = _readiness(topic_context=True, core_viewpoint=True, example_or_detail=False, conclusion=True)
        plan = _make_plan(readiness=r)
        self.assertIn("focus.example_or_detail", plan.metadata.section_ids)

    def test_missing_conclusion_loads_correct_focus(self) -> None:
        r = _readiness(topic_context=True, core_viewpoint=True, example_or_detail=True, conclusion=False)
        plan = _make_plan(readiness=r)
        self.assertIn("focus.conclusion", plan.metadata.section_ids)

    def test_script_exists_loads_revision_focus(self) -> None:
        """§10: existing script loads focus.revision."""
        r = _readiness(topic_context=False)
        plan = _make_plan(readiness=r, script_exists=True)
        self.assertIn("focus.revision", plan.metadata.section_ids)
        self.assertNotIn("focus.topic_context", plan.metadata.section_ids)
        self.assertNotIn("focus.core_viewpoint", plan.metadata.section_ids)

    def test_no_focus_section_when_all_ready(self) -> None:
        """When all dims complete and no script, no focus section is loaded."""
        r = _readiness()  # all True
        plan = _make_plan(readiness=r)
        for sid in plan.metadata.section_ids:
            self.assertFalse(sid.startswith("focus."), f"Unexpected focus section: {sid}")

    def test_required_core_sections_always_present(self) -> None:
        """§10: required core sections present for every profile."""
        for scenario_r, script_exists in [
            (_readiness(topic_context=False), False),
            (_readiness(), False),
            (_readiness(topic_context=False), True),
        ]:
            plan = _make_plan(readiness=scenario_r, script_exists=script_exists)
            self.assertIn("core_identity", plan.metadata.section_ids)
            self.assertIn("task_contract", plan.metadata.section_ids)
            self.assertIn("output_scope", plan.metadata.section_ids)


# ---------------------------------------------------------------------------
# Interview profile: option mode
# ---------------------------------------------------------------------------

class TestOptionMode(unittest.TestCase):
    def test_abc_for_first_turn_or_short_answer(self) -> None:
        """§10: option_mode can be none without breaking the interview contract."""
        r = _readiness(topic_context=False, core_viewpoint=False)
        tr = _empty_transcript()
        mode = _determine_option_mode(r, tr, script_exists=False)
        self.assertEqual(mode, "abc")

    def test_none_for_detailed_user_answer(self) -> None:
        """Detailed last user answer (>250 chars) → option_mode=none."""
        r = _readiness(topic_context=False, core_viewpoint=False)
        long_content = "A" * 300
        tr = _transcript_with_turns(("user", long_content))
        mode = _determine_option_mode(r, tr, script_exists=False)
        self.assertEqual(mode, "none")

    def test_none_mode_not_present_in_sections_when_abc(self) -> None:
        r = _readiness(topic_context=False, core_viewpoint=False)
        tr = _transcript_with_turns(("user", "short"))
        plan = build_interview_prompt_plan(
            topic="T", creation_intent="I", transcript=tr,
            readiness=r, script_exists=False, transcript_text="user: short",
        )
        self.assertIn("option_mode.abc", plan.metadata.section_ids)
        self.assertNotIn("option_mode.none", plan.metadata.section_ids)
        self.assertNotIn("option_mode.two_actions", plan.metadata.section_ids)

    def test_none_mode_section_loaded_when_detailed_answer(self) -> None:
        """§10: dynamic option_mode=none is a valid state without breaking response."""
        r = _readiness(topic_context=False, core_viewpoint=False)
        long_content = "A" * 300
        tr = _transcript_with_turns(("user", long_content))
        plan = build_interview_prompt_plan(
            topic="T", creation_intent="I", transcript=tr,
            readiness=r, script_exists=False, transcript_text=f"user: {long_content}",
        )
        self.assertIn("option_mode.none", plan.metadata.section_ids)
        self.assertNotIn("option_mode.abc", plan.metadata.section_ids)
        self.assertNotIn("option_mode.two_actions", plan.metadata.section_ids)

    def test_two_actions_mode_when_near_ready(self) -> None:
        """3/4 dims done → two_actions option mode."""
        r = _readiness(topic_context=True, core_viewpoint=True, example_or_detail=True, conclusion=False)
        tr = _empty_transcript()
        mode = _determine_option_mode(r, tr, script_exists=False)
        self.assertEqual(mode, "two_actions")

    def test_two_actions_section_in_plan_when_near_ready(self) -> None:
        r = _readiness(topic_context=True, core_viewpoint=True, example_or_detail=True, conclusion=False)
        plan = _make_plan(readiness=r)
        self.assertIn("option_mode.two_actions", plan.metadata.section_ids)

    def test_gate_option_mode_matches_section(self) -> None:
        """option_mode gate must match the option_mode.* section loaded."""
        # 2/4 dims done → abc (large readiness gap)
        r_abc = _readiness(topic_context=False, core_viewpoint=False, example_or_detail=True, conclusion=True)
        # 3/4 dims done → two_actions (near-ready)
        r_two = _readiness(topic_context=True, core_viewpoint=True, example_or_detail=True, conclusion=False)
        for r, expected_mode in [
            (r_abc, "abc"),
            (r_two, "two_actions"),
        ]:
            plan = _make_plan(readiness=r)
            gate_mode = plan.metadata.gates.get("option_mode")
            section_ids = plan.metadata.section_ids
            self.assertEqual(gate_mode, expected_mode)
            self.assertIn(f"option_mode.{expected_mode}", section_ids)


# ---------------------------------------------------------------------------
# Transcript turn metadata
# ---------------------------------------------------------------------------

class TestTranscriptTurnMetadata(unittest.TestCase):
    def test_turn_metadata_round_trips_through_to_dict(self) -> None:
        """Metadata is persisted in to_dict and recovered in from_dict."""
        tr = TranscriptRecord(session_id="s1")
        turn = tr.append(Speaker.AGENT, "Hello?", metadata={
            "interview_focus": "topic_context",
            "turn_role": "question",
            "prompt_version": PROMPT_VERSION,
        })
        payload = turn.to_dict()
        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["interview_focus"], "topic_context")

        recovered = TranscriptTurn.from_dict(payload, session_id="s1")
        self.assertEqual(recovered.metadata["interview_focus"], "topic_context")
        self.assertEqual(recovered.metadata["turn_role"], "question")

    def test_legacy_turn_without_metadata_loads_as_empty_dict(self) -> None:
        """§10: legacy turns without metadata field load correctly."""
        legacy_payload = {
            "speaker": "agent",
            "content": "What is your topic?",
            "created_at": "2025-01-01T00:00:00Z",
            "turn_id": "turn_abc123",
        }
        turn = TranscriptTurn.from_dict(legacy_payload, session_id="s1")
        self.assertIsInstance(turn.metadata, dict)
        self.assertEqual(turn.metadata, {})

    def test_empty_metadata_omitted_from_to_dict(self) -> None:
        """Empty metadata is not persisted to keep JSON compact."""
        tr = TranscriptRecord(session_id="s1")
        turn = tr.append(Speaker.USER, "Hi")
        payload = turn.to_dict()
        self.assertNotIn("metadata", payload)

    def test_metadata_not_included_in_transcript_record_to_dict_when_empty(self) -> None:
        tr = TranscriptRecord(session_id="s1")
        tr.append(Speaker.USER, "Hello")
        tr.append(Speaker.AGENT, "Hi there")
        d = tr.to_dict()
        for turn_dict in d["turns"]:
            self.assertNotIn("metadata", turn_dict)


# ---------------------------------------------------------------------------
# PromptPlan metadata: operation_profile and section order
# ---------------------------------------------------------------------------

class TestPlanMetadata(unittest.TestCase):
    def test_operation_profile_is_interview_followup(self) -> None:
        plan = _make_plan()
        self.assertEqual(plan.metadata.operation_profile, "interview_followup")

    def test_prompt_version_matches_constant(self) -> None:
        plan = _make_plan()
        self.assertEqual(plan.metadata.prompt_version, PROMPT_VERSION)

    def test_stable_sections_before_dynamic_in_section_ids(self) -> None:
        """Cache-friendly ordering: stable sections appear before dynamic ones."""
        plan = _make_plan()
        ids = list(plan.metadata.section_ids)
        # core_identity and task_contract are stable system sections and should be early.
        ci_idx = ids.index("core_identity")
        tc_idx = ids.index("task_contract")
        tr_idx = ids.index("transcript")
        self.assertLess(ci_idx, tr_idx)
        self.assertLess(tc_idx, tr_idx)

    def test_memory_context_omitted_when_empty(self) -> None:
        """§10: memory disabled omits memory sections."""
        plan = _make_plan(memory_context="")
        self.assertNotIn("memory_context", plan.metadata.section_ids)
        omitted_ids = [o["section_id"] for o in plan.metadata.omitted_sections]
        self.assertIn("memory_context", omitted_ids)

    def test_memory_context_included_when_present(self) -> None:
        plan = _make_plan(memory_context="User prefers short episodes.")
        self.assertIn("memory_context", plan.metadata.section_ids)

    def test_gates_include_all_expected_keys(self) -> None:
        plan = _make_plan()
        gates = plan.metadata.gates
        self.assertIn("script_exists", gates)
        self.assertIn("option_mode", gates)
        self.assertIn("suggested_focus", gates)
        self.assertIn("missing_dimensions", gates)
        self.assertIn("has_memory_context", gates)

    def test_system_and_user_non_empty(self) -> None:
        """Plan must always produce non-empty system and user text."""
        plan = _make_plan()
        self.assertTrue(plan.system.strip())
        self.assertTrue(plan.user.strip())


# ---------------------------------------------------------------------------
# _resolve_focus helper
# ---------------------------------------------------------------------------

class TestResolveFocus(unittest.TestCase):
    def test_first_missing_dimension_is_focus(self) -> None:
        self.assertEqual(_resolve_focus(["topic_context", "core_viewpoint"], False), "topic_context")

    def test_revision_when_script_exists(self) -> None:
        self.assertEqual(_resolve_focus(["topic_context"], True), "revision")

    def test_ready_to_generate_when_no_missing(self) -> None:
        self.assertEqual(_resolve_focus([], False), "ready_to_generate")


if __name__ == "__main__":
    unittest.main()
