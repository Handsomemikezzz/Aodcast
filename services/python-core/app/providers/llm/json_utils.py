from __future__ import annotations

import json
from typing import Any


def parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if not text:
        return {}
    if "```" in text:
        for segment in text.split("```"):
            candidate = segment.strip()
            if candidate.startswith("json"):
                candidate = candidate[len("json") :].strip()
            if candidate.startswith("{"):
                text = candidate
                break
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_candidates(content: str) -> list[dict[str, Any]]:
    candidates = parse_json_object(content).get("candidates")
    if not isinstance(candidates, list):
        return []
    return [item for item in candidates if isinstance(item, dict)]


def parse_selected_ids(content: str) -> list[str]:
    selected = parse_json_object(content).get("selected_ids")
    if not isinstance(selected, list):
        return []
    return [str(item) for item in selected if isinstance(item, (str, int))]
