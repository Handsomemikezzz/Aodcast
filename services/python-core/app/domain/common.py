from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_utc_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def is_within_days_since(value: str, *, days: int) -> bool:
    return datetime.now(UTC) - parse_utc_iso(value) <= timedelta(days=days)
