from __future__ import annotations

import unittest

from app.domain.session import SessionRecord


class SessionRecordTests(unittest.TestCase):
    def test_rename_topic_does_not_change_updated_at(self) -> None:
        session = SessionRecord(topic="Old Topic", creation_intent="Testing rename behavior")
        updated_at_before = session.updated_at

        session.rename_topic("New Topic")

        self.assertEqual(session.topic, "New Topic")
        self.assertEqual(session.updated_at, updated_at_before)


if __name__ == "__main__":
    unittest.main()
