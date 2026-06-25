from __future__ import annotations

import re

# High-sensitivity secrets that must NEVER be stored, even on explicit request.
# Detection is deterministic and runs both in the extraction prompt (as rules)
# and here as a hard server-side gate. Do not rely on the model alone.

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # API keys / tokens / private keys
    ("api_key", re.compile(r"\b(sk|pk|rk|api|key|token|secret|bearer)[-_]?[A-Za-z0-9]{16,}\b", re.IGNORECASE)),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    # Bank / payment cards (13-19 digit sequences, optionally grouped)
    ("payment_card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
    # Chinese resident ID (18 chars: 17 digits + digit/X)
    ("national_id", re.compile(r"\b\d{17}[\dXx]\b")),
    # Generic passport-like full id (8-9 alphanumerics following a passport hint)
    ("passport", re.compile(r"(护照|passport)\s*[:：#]?\s*[A-Za-z0-9]{6,9}", re.IGNORECASE)),
)

# Phrases that explicitly introduce a secret value, paired with an assignment.
_PASSWORD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(密码|口令|password|passwd|pwd)\s*(是|为|:|：|=)\s*\S+", re.IGNORECASE),
    re.compile(r"(home address|家庭住址|家庭地址|住址)\s*(是|为|:|：)\s*\S+", re.IGNORECASE),
)


def detect_forbidden(text: str) -> list[str]:
    """Return the list of forbidden-pattern labels found in `text`.

    Empty list means no high-sensitivity secret was detected.
    """
    if not text:
        return []
    hits: list[str] = []
    for label, pattern in _PATTERNS:
        if pattern.search(text):
            hits.append(label)
    for pattern in _PASSWORD_PATTERNS:
        if pattern.search(text):
            hits.append("secret_assignment")
            break
    return hits


def contains_forbidden(text: str) -> bool:
    return bool(detect_forbidden(text))
