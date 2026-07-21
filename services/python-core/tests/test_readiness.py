from __future__ import annotations

import unittest

from app.domain.transcript import Speaker, TranscriptRecord
from app.orchestration.readiness import (
    MIN_USER_TURNS_FOR_SCRIPT_OFFER,
    evaluate_readiness,
)


class ReadinessTurnFloorTests(unittest.TestCase):
    def test_keyword_complete_reply_is_ready_but_cannot_offer_before_floor(self) -> None:
        tr = TranscriptRecord(session_id="s1")
        tr.append(
            Speaker.USER,
            (
                "I think local-first AI tools matter because teams need reliable workflows. "
                "For example, last week I recovered a broken setup locally, "
                "and the takeaway is that tooling should fail recoverably."
            ),
        )
        report = evaluate_readiness(tr)
        self.assertTrue(report.is_ready)
        self.assertEqual(report.user_turn_count, 1)
        self.assertFalse(report.meets_turn_floor)
        self.assertFalse(report.can_offer_script)

    def test_can_offer_script_after_turn_floor(self) -> None:
        tr = TranscriptRecord(session_id="s1")
        for index in range(MIN_USER_TURNS_FOR_SCRIPT_OFFER - 1):
            tr.append(Speaker.USER, f"Prior turn {index} with enough words for context padding.")
        tr.append(
            Speaker.USER,
            (
                "I think local-first AI tools matter because teams need reliable workflows. "
                "For example, last week I recovered a broken setup locally, "
                "and the takeaway is that tooling should fail recoverably."
            ),
        )
        report = evaluate_readiness(tr)
        self.assertTrue(report.is_ready)
        self.assertEqual(report.user_turn_count, MIN_USER_TURNS_FOR_SCRIPT_OFFER)
        self.assertTrue(report.meets_turn_floor)
        self.assertTrue(report.can_offer_script)


if __name__ == "__main__":
    unittest.main()
