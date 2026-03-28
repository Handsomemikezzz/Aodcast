from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.common import utc_now_iso


@dataclass(slots=True)
class ScriptRecord:
    session_id: str
    draft: str = ""
    final: str = ""
    updated_at: str = field(default_factory=utc_now_iso)

    def update_draft(self, content: str) -> None:
        self.draft = content
        self.updated_at = utc_now_iso()

    def update_final(self, content: str) -> None:
        self.final = content
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "draft": self.draft,
            "final": self.final,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScriptRecord":
        return cls(
            session_id=payload["session_id"],
            draft=payload.get("draft", ""),
            final=payload.get("final", ""),
            updated_at=payload["updated_at"],
        )
