from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import unicodedata
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_utc_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def is_within_days_since(value: str, *, days: int) -> bool:
    return datetime.now(UTC) - parse_utc_iso(value) <= timedelta(days=days)


def normalize_text_for_hash(value: str) -> str:
    """Return the canonical text form used by persisted content hashes."""

    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(normalize_text_for_hash(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
