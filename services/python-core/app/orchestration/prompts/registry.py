"""Prompt infrastructure types for the state-aware prompt assembly layer.

Every LLM call produces a PromptPlan with full section metadata, enabling:
- observable prompt assembly decisions
- cache-friendly stable-prefix ordering
- metadata-based tests (assert section decisions, not fragile full text)
- future provider-specific prompt-cache API integration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


# Current prompt system version — bump when section content changes materially.
PROMPT_VERSION = "interview-v2"


class CachePolicy(StrEnum):
    """Stability classification for a prompt section.

    Ordered from most stable (safe to cache across requests) to most dynamic.
    """

    STABLE = "stable"             # fixed text; same across all sessions for this profile
    SESSION_STABLE = "session_stable"  # stable within one session / script
    DYNAMIC = "dynamic"           # changes per turn / request
    PRIVATE_DYNAMIC = "private_dynamic"  # per-turn + contains user/memory text


@dataclass(frozen=True, slots=True)
class PromptSection:
    """A single named block of prompt text with observability metadata."""

    section_id: str
    content: str
    cache_policy: CachePolicy
    required: bool = False


@dataclass(frozen=True, slots=True)
class PromptPlanMetadata:
    """Non-sensitive assembly summary persisted alongside generated artefacts."""

    prompt_version: str
    operation_profile: str
    section_ids: tuple[str, ...]
    cacheable_section_ids: tuple[str, ...]
    dynamic_section_ids: tuple[str, ...]
    # Sections that were evaluated but omitted, each as {"section_id": ..., "reason": ...}.
    omitted_sections: tuple[dict[str, str], ...]
    # Runtime gate decisions that drove section inclusion/exclusion.
    gates: dict[str, object]
    # Combined character count of system + user text.
    char_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_version": self.prompt_version,
            "operation_profile": self.operation_profile,
            "section_ids": list(self.section_ids),
            "cacheable_section_ids": list(self.cacheable_section_ids),
            "dynamic_section_ids": list(self.dynamic_section_ids),
            "omitted_sections": list(self.omitted_sections),
            "gates": dict(self.gates),
            "char_count": self.char_count,
        }


@dataclass(frozen=True, slots=True)
class PromptPlan:
    """Provider-agnostic prompt assembly result.

    Providers serialize ``system`` and ``user`` into their native message format.
    ``metadata`` is used for observability, metadata-based tests, and optional
    persistence (script generation metadata, turn metadata).
    """

    system: str
    user: str
    metadata: PromptPlanMetadata


def assemble_plan(
    *,
    operation_profile: str,
    prompt_version: str = PROMPT_VERSION,
    system_sections: list[PromptSection],
    user_sections: list[PromptSection],
    gates: dict[str, object] | None = None,
    omitted_sections: list[dict[str, str]] | None = None,
) -> PromptPlan:
    """Assemble sections into a PromptPlan and compute metadata.

    Sections are joined with a blank line between each non-empty block.
    Section ordering determines the stable-prefix structure; callers must pass
    sections in the correct order (stable → dynamic).
    """
    system = "\n\n".join(s.content for s in system_sections if s.content.strip())
    user = "\n\n".join(s.content for s in user_sections if s.content.strip())

    all_sections = system_sections + user_sections
    included_ids = tuple(s.section_id for s in all_sections)
    cacheable_ids = tuple(
        s.section_id
        for s in all_sections
        if s.cache_policy in (CachePolicy.STABLE, CachePolicy.SESSION_STABLE)
    )
    dynamic_ids = tuple(
        s.section_id
        for s in all_sections
        if s.cache_policy in (CachePolicy.DYNAMIC, CachePolicy.PRIVATE_DYNAMIC)
    )
    metadata = PromptPlanMetadata(
        prompt_version=prompt_version,
        operation_profile=operation_profile,
        section_ids=included_ids,
        cacheable_section_ids=cacheable_ids,
        dynamic_section_ids=dynamic_ids,
        omitted_sections=tuple(omitted_sections or []),
        gates=gates or {},
        char_count=len(system) + len(user),
    )
    return PromptPlan(system=system, user=user, metadata=metadata)
