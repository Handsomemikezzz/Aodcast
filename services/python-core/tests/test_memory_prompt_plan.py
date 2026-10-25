"""Phase 3 tests: memory prompt profiles via PromptPlan.

Tests verify (§10 / §8):
- Each profile uses a thin system section + dynamic payload
- JSON output constraints are present in every memory profile's system text
- Memory profiles do NOT load interview/script sections
- Sensitive bodies never appear in the rerank index
- Required sections are present for each profile
"""

from __future__ import annotations

import unittest

from app.orchestration.prompts.memory import (
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
        """§10: memory extraction does not load script/interview sections."""
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
