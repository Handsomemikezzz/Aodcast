from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from app.domain.common import is_within_days_since, utc_now_iso


@dataclass(slots=True)
class ScriptRevision:
    revision_id: str
    draft: str
    final: str
    reason: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "draft": self.draft,
            "final": self.final,
            "reason": self.reason,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScriptRevision":
        return cls(
            revision_id=str(payload["revision_id"]),
            draft=str(payload.get("draft", "")),
            final=str(payload.get("final", "")),
            reason=str(payload.get("reason", "legacy")),
            created_at=str(payload.get("created_at") or utc_now_iso()),
        )


@dataclass(slots=True)
class ScriptRecord:
    session_id: str
    draft: str = ""
    final: str = ""
    deleted_at: str | None = None
    revisions: list[ScriptRevision] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now_iso)

    def _snapshot(self, *, reason: str) -> None:
        self.revisions.append(
            ScriptRevision(
                revision_id=str(uuid4()),
                draft=self.draft,
                final=self.final,
                reason=reason,
                created_at=utc_now_iso(),
            )
        )

    def update_draft(self, content: str) -> None:
        self.draft = content
        self.updated_at = utc_now_iso()

    def update_final(self, content: str) -> None:
        self.final = content
        self.updated_at = utc_now_iso()

    def save_final(self, content: str, *, reason: str = "final_edit") -> None:
        if content != self.final:
            self._snapshot(reason=reason)
        self.final = content
        self.updated_at = utc_now_iso()

    def soft_delete(self, *, reason: str = "script_delete") -> None:
        if not self.is_deleted():
            self._snapshot(reason=reason)
        now = utc_now_iso()
        self.draft = ""
        self.final = ""
        self.deleted_at = now
        self.updated_at = now

    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def can_restore(self, *, within_days: int = 30) -> bool:
        if self.deleted_at is None:
            return True
        return is_within_days_since(self.deleted_at, days=within_days)

    def restore(self, *, within_days: int = 30) -> None:
        if not self.is_deleted():
            return
        if not self.can_restore(within_days=within_days):
            raise ValueError(f"Script restore window exceeded ({within_days} days).")
        if not self.revisions:
            raise ValueError("No revision found to restore script content.")
        previous = self.revisions[-1]
        self.draft = previous.draft
        self.final = previous.final
        self.deleted_at = None
        self.updated_at = utc_now_iso()

    def list_revisions(self) -> list[ScriptRevision]:
        return list(self.revisions)

    def rollback_to_revision(self, revision_id: str) -> None:
        matched = next((item for item in self.revisions if item.revision_id == revision_id), None)
        if matched is None:
            raise ValueError(f"Unknown revision '{revision_id}'.")
        if self.is_deleted():
            raise ValueError("Restore the script before rolling back revisions.")
        self._snapshot(reason="rollback_backup")
        self.draft = matched.draft
        self.final = matched.final
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "draft": self.draft,
            "final": self.final,
            "deleted_at": self.deleted_at,
            "revisions": [item.to_dict() for item in self.revisions],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScriptRecord":
        return cls(
            session_id=payload["session_id"],
            draft=payload.get("draft", ""),
            final=payload.get("final", ""),
            deleted_at=payload.get("deleted_at") or None,
            revisions=[ScriptRevision.from_dict(item) for item in payload.get("revisions", [])],
            updated_at=payload["updated_at"],
        )
