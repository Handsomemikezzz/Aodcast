from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4

from app.domain.common import utc_now_iso


class MemoryType(StrEnum):
    PROFILE = "profile"
    EXPERIENCE = "experience"
    VIEWPOINT = "viewpoint"
    PREFERENCE = "preference"


class MemoryOrigin(StrEnum):
    AUTO = "auto"
    EXPLICIT = "explicit"


class PendingJobKind(StrEnum):
    EXTRACT_TURNS = "extract_turns"
    NORMALIZE_EXPLICIT_MEMORY = "normalize_explicit_memory"
    REBUILD_INDEXES = "rebuild_indexes"


class WorkerStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"


def new_memory_id() -> str:
    return f"mem_{uuid4().hex[:8]}"


def new_job_id() -> str:
    return f"job_{uuid4().hex}"


@dataclass(slots=True)
class MemoryEvidence:
    session_id: str
    turn_id: str
    quote: str
    observed_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryEvidence":
        return cls(
            session_id=payload.get("session_id", ""),
            turn_id=payload.get("turn_id", ""),
            quote=payload.get("quote", ""),
            observed_at=payload.get("observed_at", utc_now_iso()),
        )


@dataclass(slots=True)
class MemoryEntry:
    name: str
    description: str
    type: MemoryType
    body: str
    id: str = field(default_factory=new_memory_id)
    origin: MemoryOrigin = MemoryOrigin.AUTO
    sensitive: bool = False
    keywords: list[str] = field(default_factory=list)
    evidence: list[MemoryEvidence] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    last_used_at: str | None = None
    use_count: int = 0

    @property
    def source_count(self) -> int:
        return len(self.evidence)

    def touch_used(self) -> None:
        self.last_used_at = utc_now_iso()
        self.use_count += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.type.value,
            "origin": self.origin.value,
            "sensitive": self.sensitive,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used_at": self.last_used_at,
            "use_count": self.use_count,
            "source_count": self.source_count,
            "body": self.body,
            "keywords": list(self.keywords),
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryEntry":
        return cls(
            id=payload.get("id") or new_memory_id(),
            name=payload.get("name", ""),
            description=payload.get("description", ""),
            type=MemoryType(payload["type"]),
            origin=MemoryOrigin(payload.get("origin", "auto")),
            sensitive=bool(payload.get("sensitive", False)),
            body=payload.get("body", ""),
            keywords=list(payload.get("keywords", []) or []),
            evidence=[MemoryEvidence.from_dict(item) for item in payload.get("evidence", []) or []],
            created_at=payload.get("created_at", utc_now_iso()),
            updated_at=payload.get("updated_at", utc_now_iso()),
            last_used_at=payload.get("last_used_at") or None,
            use_count=int(payload.get("use_count", 0) or 0),
        )


@dataclass(slots=True)
class MemorySettings:
    first_run_acknowledged: bool = False
    writing_enabled: bool = False
    usage_enabled: bool = False
    last_maintenance_at: str | None = None
    changes_since_maintenance: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemorySettings":
        return cls(
            first_run_acknowledged=bool(payload.get("first_run_acknowledged", False)),
            writing_enabled=bool(payload.get("writing_enabled", False)),
            usage_enabled=bool(payload.get("usage_enabled", False)),
            last_maintenance_at=payload.get("last_maintenance_at") or None,
            changes_since_maintenance=int(payload.get("changes_since_maintenance", 0) or 0),
        )


@dataclass(slots=True)
class WorkerState:
    status: WorkerStatus = WorkerStatus.IDLE
    last_error: str = ""
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "last_error": self.last_error,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkerState":
        return cls(
            status=WorkerStatus(payload.get("status", "idle")),
            last_error=payload.get("last_error", ""),
            updated_at=payload.get("updated_at") or None,
        )


@dataclass(slots=True)
class MemoryState:
    """Full contents of state.json: settings + worker status."""

    settings: MemorySettings = field(default_factory=MemorySettings)
    worker: WorkerState = field(default_factory=WorkerState)

    def to_dict(self) -> dict[str, Any]:
        return {"settings": self.settings.to_dict(), "worker": self.worker.to_dict()}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryState":
        return cls(
            settings=MemorySettings.from_dict(payload.get("settings", {}) or {}),
            worker=WorkerState.from_dict(payload.get("worker", {}) or {}),
        )


@dataclass(slots=True)
class PendingJob:
    kind: PendingJobKind
    session_id: str = ""
    from_turn_id: str = ""
    to_turn_id: str = ""
    raw_intent: str = ""
    source_turn_id: str = ""
    job_id: str = field(default_factory=new_job_id)
    retry_count: int = 0
    last_error: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PendingJob":
        return cls(
            job_id=payload.get("job_id") or new_job_id(),
            kind=PendingJobKind(payload["kind"]),
            session_id=payload.get("session_id", ""),
            from_turn_id=payload.get("from_turn_id", ""),
            to_turn_id=payload.get("to_turn_id", ""),
            raw_intent=payload.get("raw_intent", ""),
            source_turn_id=payload.get("source_turn_id", ""),
            retry_count=int(payload.get("retry_count", 0) or 0),
            last_error=payload.get("last_error", ""),
            created_at=payload.get("created_at", utc_now_iso()),
        )


@dataclass(slots=True)
class ForgetFingerprint:
    """Irreversible forget marker. Stores no body — only what is needed to
    prevent the same old evidence from regenerating a deleted memory."""

    content_hash: str
    turn_ids: list[str]
    deleted_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ForgetFingerprint":
        return cls(
            content_hash=payload.get("content_hash", ""),
            turn_ids=list(payload.get("turn_ids", []) or []),
            deleted_at=payload.get("deleted_at", utc_now_iso()),
        )


@dataclass(slots=True)
class RetrievedMemoryContext:
    prompt_block: str
    memory_ids: tuple[str, ...]
    item_count: int

    @classmethod
    def empty(cls) -> "RetrievedMemoryContext":
        return cls(prompt_block="", memory_ids=(), item_count=0)
