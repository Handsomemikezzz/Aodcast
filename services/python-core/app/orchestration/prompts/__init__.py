"""Prompt assembly package for Aodcast (Phase 1).

Provides backward-compatible re-exports so existing imports such as:
    from app.orchestration.prompts import INTERVIEW_STREAM_SYSTEM_PROMPT
    from app.orchestration.prompts import InterviewPromptInput, build_prompt_input
    from app.orchestration.prompts import MEMORY_EXTRACTION_SYSTEM_PROMPT
continue to work without changes.

New code should import directly from the sub-modules:
    from app.orchestration.prompts.registry import PromptPlan, PromptSection
    from app.orchestration.prompts.interview import build_interview_prompt_plan
"""

# Infrastructure types
from app.orchestration.prompts.registry import (
    PROMPT_VERSION,
    CachePolicy,
    PromptPlan,
    PromptPlanMetadata,
    PromptSection,
    assemble_plan,
)

# Interview profile (Phase 1)
from app.orchestration.prompts.interview import (
    INTERVIEW_STREAM_SYSTEM_PROMPT,
    InterviewPromptInput,
    build_interview_prompt_plan,
    build_interview_stream_instructions,
    build_interview_stream_user_content,
    build_prompt_input,
    build_question,
)

# Script profile (Phase 2)
from app.orchestration.prompts.script import (
    SCRIPT_GENERATION_SYSTEM_PROMPT,
    EpisodeBrief,
    ScriptStyleProfile,
    build_episode_brief,
    build_script_generation_metadata,
    build_script_generation_user_prompt,
    build_script_prompt_plan,
    build_script_style_profile,
)

# Memory profiles (Phase 3)
from app.orchestration.prompts.memory import (
    MEMORY_EXTRACTION_SYSTEM_PROMPT,
    MEMORY_MAINTENANCE_SYSTEM_PROMPT,
    MEMORY_RERANK_SYSTEM_PROMPT,
    _MEMORY_ACTION_SYSTEM,
    build_memory_action_classification_prompt,
    build_memory_action_plan,
    build_memory_extraction_plan,
    build_memory_extraction_user_content,
    build_memory_maintenance_user_content,
    build_memory_merge_plan,
    build_memory_rerank_plan,
    build_memory_rerank_user_content,
)

__all__ = [
    # Registry
    "PROMPT_VERSION",
    "CachePolicy",
    "PromptPlan",
    "PromptPlanMetadata",
    "PromptSection",
    "assemble_plan",
    # Interview
    "INTERVIEW_STREAM_SYSTEM_PROMPT",
    "InterviewPromptInput",
    "build_interview_prompt_plan",
    "build_interview_stream_instructions",
    "build_interview_stream_user_content",
    "build_prompt_input",
    "build_question",
    # Script (Phase 2)
    "SCRIPT_GENERATION_SYSTEM_PROMPT",
    "EpisodeBrief",
    "ScriptStyleProfile",
    "build_episode_brief",
    "build_script_generation_metadata",
    "build_script_generation_user_prompt",
    "build_script_prompt_plan",
    "build_script_style_profile",
    # Memory (Phase 3)
    "MEMORY_EXTRACTION_SYSTEM_PROMPT",
    "MEMORY_MAINTENANCE_SYSTEM_PROMPT",
    "MEMORY_RERANK_SYSTEM_PROMPT",
    "_MEMORY_ACTION_SYSTEM",
    "build_memory_action_classification_prompt",
    "build_memory_action_plan",
    "build_memory_extraction_plan",
    "build_memory_extraction_user_content",
    "build_memory_maintenance_user_content",
    "build_memory_merge_plan",
    "build_memory_rerank_plan",
    "build_memory_rerank_user_content",
]
