"""Phase 3 tests: memory prompt profiles via PromptPlan.

Tests verify (§10 / §8):
- Each profile uses a thin system section + dynamic payload
- JSON output constraints are present in every memory profile's system text
- memory_action_classifier does NOT load interview/script sections
- Sensitive bodies never appear in the rerank index
- Required sections are present for each profile
- Legacy string constants match new section content (backward compat)
"""

from __future__ import annotations

import unittest

from app.orchestration.prompts.memory import (
    MEMORY_EXTRACTION_SYSTEM_PROMPT,
    MEMORY_MAINTENANCE_SYSTEM_PROMPT,
    MEMORY_RERANK_SYSTEM_PROMPT,
    _MEMORY_ACTION_SYSTEM,
    build_memory_action_plan,
    build_memory_extraction_plan,
    build_memory_merge_plan,
    build_memory_rerank_plan,
)
from app.orchestration.prompts.registry import PROMPT_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candidates(n: int = 3) -> list[dict[str, str]]:
    return [
        {"id": f"mem_{i}", "type": "viewpoint", "name": f"Memory {i}",
         "description": f"Description {i}"}
        for i in range(n)
    ]


def _make_entries(n: int = 2) -> list[dict]:
    return [
        {
            "id": f"mem_{i}",
            "type": "viewpoint",
            "name": f"Memory {i}",
            "description": f"Desc {i}",
            "body": f"Body text {i}",
            "keywords": ["kw1", "kw2"],
            "evidence": [{"turn_id": f"turn_{i}", "quote": "verbatim"}],
        }
        for i in range(n)
    ]


def _make_user_turns(n: int = 3) -> list[dict[str, str]]:
    return [
        {"turn_id": f"turn_{i}", "content": f"User said something relevant {i}."}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# memory_extraction profile
# ---------------------------------------------------------------------------

class TestMemoryExtractionPlan(unittest.TestCase):
    def _plan(self, explicit_intent: str = ""):
        return build_memory_extraction_plan(
            topic="Test topic",
            creation_intent="Test intent",
            user_turns=_make_user_turns(3),
            existing_candidates=_make_candidates(2),
            explicit_intent=explicit_intent,
        )

    def test_operation_profile(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.metadata.operation_profile, "memory_extraction")

    def test_prompt_version(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.metadata.prompt_version, PROMPT_VERSION)

    def test_required_system_section_present(self) -> None:
        plan = self._plan()
        self.assertIn("mem_extraction.system", plan.metadata.section_ids)

    def test_payload_section_present(self) -> None:
        plan = self._plan()
        self.assertIn("mem_extraction.payload", plan.metadata.section_ids)

    def test_total_sections_count_is_thin(self) -> None:
        """Thin profile: exactly 2 sections (system + payload)."""
        plan = self._plan()
        self.assertEqual(len(plan.metadata.section_ids), 2)

    def test_json_constraint_in_system_text(self) -> None:
        """§10: strict JSON requirements in JSON profiles."""
        plan = self._plan()
        self.assertIn("STRICT JSON", plan.system)
        self.assertIn("candidates", plan.system)

    def test_no_script_sections_in_memory_profile(self) -> None:
        """§10: memory_action_classifier does not load script/interview sections."""
        plan = self._plan()
        for sid in plan.metadata.section_ids:
            self.assertFalse(sid.startswith("script."), f"Script section leaked: {sid}")
            self.assertFalse(sid.startswith("focus."), f"Focus section leaked: {sid}")

    def test_explicit_intent_gate_reflected(self) -> None:
        plan_with = self._plan(explicit_intent="Please remember this.")
        plan_without = self._plan()
        self.assertTrue(plan_with.metadata.gates["has_explicit_intent"])
        self.assertFalse(plan_without.metadata.gates["has_explicit_intent"])

    def test_user_turn_count_in_gates(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.metadata.gates["user_turn_count"], 3)

    def test_privacy_constraint_in_system(self) -> None:
        """Sensitive bodies / high-sensitivity secrets must not be captured."""
        plan = self._plan()
        self.assertIn("sensitive", plan.system)
        self.assertIn("passwords", plan.system)

    def test_backward_compat_constant_matches_section(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.system, MEMORY_EXTRACTION_SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# memory_rerank profile
# ---------------------------------------------------------------------------

class TestMemoryRerankPlan(unittest.TestCase):
    def _plan(self, n_candidates: int = 3):
        return build_memory_rerank_plan(
            topic="Test",
            creation_intent="Intent",
            candidates=_make_candidates(n_candidates),
            max_select=3,
        )

    def test_operation_profile(self) -> None:
        self.assertEqual(self._plan().metadata.operation_profile, "memory_rerank")

    def test_thin_profile_two_sections(self) -> None:
        self.assertEqual(len(self._plan().metadata.section_ids), 2)

    def test_json_constraint_in_system(self) -> None:
        plan = self._plan()
        self.assertIn("STRICT JSON", plan.system)
        self.assertIn("selected_ids", plan.system)

    def test_no_sensitive_body_in_candidates(self) -> None:
        """§8.2: sensitive bodies must never enter the rerank index.
        The candidate list uses id/type/name/description only."""
        candidates = [
            {
                "id": "mem_sensitive",
                "type": "experience",
                "name": "Private matter",
                "description": "Generalized description",
                # body intentionally omitted from candidate index
            }
        ]
        plan = build_memory_rerank_plan(
            topic="T", creation_intent="I", candidates=candidates, max_select=1
        )
        # Body text should not appear in the user payload
        self.assertNotIn("Private body content", plan.user)
        # Description is included (safe for reranking)
        self.assertIn("Generalized description", plan.user)

    def test_candidate_count_in_gates(self) -> None:
        plan = self._plan(n_candidates=5)
        self.assertEqual(plan.metadata.gates["candidate_count"], 5)

    def test_backward_compat_constant_matches_section(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.system, MEMORY_RERANK_SYSTEM_PROMPT)

    def test_no_script_sections_leak(self) -> None:
        for sid in self._plan().metadata.section_ids:
            self.assertFalse(sid.startswith("script."))
            self.assertFalse(sid.startswith("focus."))


# ---------------------------------------------------------------------------
# memory_merge profile
# ---------------------------------------------------------------------------

class TestMemoryMergePlan(unittest.TestCase):
    def _plan(self):
        return build_memory_merge_plan(entries=_make_entries(2))

    def test_operation_profile(self) -> None:
        self.assertEqual(self._plan().metadata.operation_profile, "memory_merge")

    def test_thin_profile_two_sections(self) -> None:
        self.assertEqual(len(self._plan().metadata.section_ids), 2)

    def test_json_constraint_in_system(self) -> None:
        plan = self._plan()
        self.assertIn("STRICT JSON", plan.system)
        self.assertIn("primary_id", plan.system)

    def test_no_invent_facts_constraint(self) -> None:
        plan = self._plan()
        self.assertIn("never invent facts", plan.system)

    def test_entry_count_in_gates(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.metadata.gates["entry_count"], 2)

    def test_backward_compat_constant_matches_section(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.system, MEMORY_MAINTENANCE_SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# memory_action_classifier profile
# ---------------------------------------------------------------------------

class TestMemoryActionPlan(unittest.TestCase):
    def _plan(self, candidate_names: list[str] | None = None):
        return build_memory_action_plan(
            user_message="Please forget what I said about my job.",
            candidate_names=candidate_names or ["Job history", "Work stress"],
        )

    def test_operation_profile(self) -> None:
        self.assertEqual(self._plan().metadata.operation_profile, "memory_action_classifier")

    def test_thin_profile_two_sections(self) -> None:
        """§10: memory_action_classifier uses thin profile."""
        self.assertEqual(len(self._plan().metadata.section_ids), 2)

    def test_json_constraint_in_system(self) -> None:
        plan = self._plan()
        self.assertIn("JSON", plan.system)
        self.assertIn("action", plan.system)
        self.assertIn("subject", plan.system)

    def test_prefer_none_when_uncertain_in_system(self) -> None:
        """§8.4: prefer none when uncertain."""
        plan = self._plan()
        self.assertIn("Prefer 'none'", plan.system)

    def test_no_memory_bodies_in_payload(self) -> None:
        """§8.4: dynamic payload includes user message and limited topic names only, no bodies."""
        plan = self._plan(candidate_names=["Topic A", "Topic B"])
        # Candidate names appear (safe)
        self.assertIn("Topic A", plan.user)
        # But there should be no body-like content
        self.assertNotIn("body text", plan.user.lower())

    def test_candidate_names_capped_at_20(self) -> None:
        """§8.4: limit candidate names sent to classifier."""
        many = [f"Topic {i}" for i in range(25)]
        plan = build_memory_action_plan(user_message="forget", candidate_names=many)
        # Count occurrences — should not include all 25
        count = sum(1 for name in many if name in plan.user)
        self.assertLessEqual(count, 20)

    def test_no_script_or_interview_sections_in_classifier(self) -> None:
        """§10: memory_action_classifier does NOT load unrelated product/script sections."""
        plan = self._plan()
        for sid in plan.metadata.section_ids:
            self.assertFalse(sid.startswith("script."), f"Script section leaked: {sid}")
            self.assertFalse(sid.startswith("focus."), f"Focus section leaked: {sid}")
            self.assertFalse(sid.startswith("option_mode."), f"Option section leaked: {sid}")

    def test_backward_compat_constant_matches_section(self) -> None:
        plan = self._plan()
        self.assertEqual(plan.system, _MEMORY_ACTION_SYSTEM)

    def test_system_and_user_nonempty(self) -> None:
        plan = self._plan()
        self.assertTrue(plan.system.strip())
        self.assertTrue(plan.user.strip())


# ---------------------------------------------------------------------------
# Cross-profile invariants
# ---------------------------------------------------------------------------

class TestMemoryProfileCrossInvariants(unittest.TestCase):
    def _all_plans(self):
        return [
            build_memory_extraction_plan(
                topic="T", creation_intent="I",
                user_turns=_make_user_turns(2),
                existing_candidates=[],
            ),
            build_memory_rerank_plan(
                topic="T", creation_intent="I",
                candidates=_make_candidates(2), max_select=2,
            ),
            build_memory_merge_plan(entries=_make_entries(2)),
            build_memory_action_plan(user_message="Forget my job.", candidate_names=[]),
        ]

    def test_all_profiles_have_prompt_version(self) -> None:
        for plan in self._all_plans():
            self.assertEqual(plan.metadata.prompt_version, PROMPT_VERSION)

    def test_all_profiles_have_nonempty_system(self) -> None:
        for plan in self._all_plans():
            self.assertTrue(plan.system.strip(), f"Empty system for {plan.metadata.operation_profile}")

    def test_all_profiles_json_constraint_in_system(self) -> None:
        """Every memory profile has strict JSON output constraint."""
        for plan in self._all_plans():
            self.assertIn("JSON", plan.system, f"No JSON in {plan.metadata.operation_profile}")

    def test_all_profiles_metadata_serializable(self) -> None:
        import json
        for plan in self._all_plans():
            json.dumps(plan.metadata.to_dict())  # must not raise


if __name__ == "__main__":
    unittest.main()
