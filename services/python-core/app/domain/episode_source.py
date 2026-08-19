from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from markdown_it import MarkdownIt

from app.domain.common import utc_now_iso


MAX_MARKDOWN_CHARACTERS = 300_000


class SourceImportKind(StrEnum):
    FILE = "file"
    PASTE = "paste"


class SourceConversionMode(StrEnum):
    ADAPT = "adapt"
    NARRATE = "narrate"


class SourceTargetLength(StrEnum):
    AUTO = "auto"
    SHORT = "short"
    STANDARD = "standard"
    LONG = "long"


def _strip_front_matter(markdown: str) -> tuple[str, str]:
    if not markdown.startswith("---\n"):
        return markdown, ""
    end = markdown.find("\n---", 4)
    if end < 0:
        return markdown, ""
    block = markdown[4:end]
    title = ""
    for line in block.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip().lower() == "title":
            title = value.strip().strip("\"'")
            break
    return markdown[end + 4 :].lstrip("\n"), title


def _inline_text(token) -> tuple[str, int]:
    if not token.children:
        return token.content.strip(), 0
    chunks: list[str] = []
    image_count = 0
    for child in token.children:
        if child.type in {"text", "code_inline"}:
            chunks.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            chunks.append("\n")
        elif child.type == "image":
            image_count += 1
    return "".join(chunks).strip(), image_count


def normalize_markdown(raw_markdown: str, *, fallback_title: str) -> tuple[str, str, list[str]]:
    cleaned, front_matter_title = _strip_front_matter(raw_markdown)
    tokens = MarkdownIt("commonmark").parse(cleaned)
    paragraphs: list[str] = []
    first_heading = ""
    skipped_code_blocks = 0
    skipped_html_blocks = 0
    skipped_images = 0

    previous_type = ""
    for token in tokens:
        if token.type in {"fence", "code_block"}:
            skipped_code_blocks += 1
            previous_type = token.type
            continue
        if token.type == "html_block":
            skipped_html_blocks += 1
            previous_type = token.type
            continue
        if token.type != "inline":
            previous_type = token.type
            continue
        text, image_count = _inline_text(token)
        skipped_images += image_count
        if not text:
            continue
        if not first_heading and previous_type == "heading_open":
            first_heading = text
        paragraphs.append(text)
        previous_type = token.type

    normalized = "\n\n".join(paragraphs).strip()
    title = (front_matter_title or first_heading or fallback_title).strip() or "Untitled Episode"
    warnings: list[str] = []
    if skipped_code_blocks:
        warnings.append(f"{skipped_code_blocks} code block(s) will not be spoken.")
    if skipped_html_blocks:
        warnings.append(f"{skipped_html_blocks} HTML block(s) will not be spoken.")
    if skipped_images:
        warnings.append(f"{skipped_images} image(s) will not be spoken.")
    if re.search(r"^\s*\|.+\|\s*$", cleaned, flags=re.MULTILINE):
        warnings.append("Markdown tables may be simplified in the spoken script.")
    return title[:200], normalized, warnings


def _content_counts(text: str) -> tuple[int, float]:
    cjk_chars = len(re.findall(r"[\u3400-\u9fff\uf900-\ufaff]", text))
    latin_words = len(re.findall(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", text))
    count = max(1, cjk_chars + latin_words)
    minutes = max(0.1, cjk_chars / 300 + latin_words / 160)
    return count, round(minutes, 1)


@dataclass(slots=True)
class EpisodeSource:
    session_id: str
    name: str
    title: str
    raw_markdown: str
    normalized_text: str
    import_kind: SourceImportKind
    conversion_mode: SourceConversionMode = SourceConversionMode.ADAPT
    target_length: SourceTargetLength = SourceTargetLength.AUTO
    focus_instructions: str = ""
    source_id: str = field(default_factory=lambda: str(uuid4()))
    source_kind: str = "markdown"
    content_hash: str = ""
    version: int = 1
    word_count: int = 1
    estimated_audio_minutes: float = 0.1
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_markdown(
        cls,
        *,
        session_id: str,
        raw_markdown: str,
        name: str,
        import_kind: SourceImportKind,
        conversion_mode: SourceConversionMode = SourceConversionMode.ADAPT,
        target_length: SourceTargetLength = SourceTargetLength.AUTO,
        focus_instructions: str = "",
        previous: "EpisodeSource | None" = None,
    ) -> "EpisodeSource":
        raw = raw_markdown.strip()
        if not raw:
            raise ValueError("Markdown source cannot be empty.")
        if len(raw) > MAX_MARKDOWN_CHARACTERS:
            raise ValueError(f"Markdown source exceeds the {MAX_MARKDOWN_CHARACTERS:,}-character limit.")
        clean_name = Path(name.strip() or "Pasted Markdown").name[:200] or "Pasted Markdown"
        fallback_title = Path(clean_name).stem if clean_name else "Untitled Episode"
        title, normalized, warnings = normalize_markdown(raw, fallback_title=fallback_title)
        if len(normalized) < 20:
            raise ValueError("Markdown source must contain at least 20 readable characters.")
        word_count, minutes = _content_counts(normalized)
        now = utc_now_iso()
        effective_target_length = (
            SourceTargetLength.AUTO
            if conversion_mode == SourceConversionMode.NARRATE
            else target_length
        )
        return cls(
            source_id=previous.source_id if previous else str(uuid4()),
            session_id=session_id,
            name=clean_name,
            title=title,
            raw_markdown=raw,
            normalized_text=normalized,
            import_kind=import_kind,
            conversion_mode=conversion_mode,
            target_length=effective_target_length,
            focus_instructions=focus_instructions.strip()[:1000],
            content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            version=(previous.version + 1) if previous else 1,
            word_count=word_count,
            estimated_audio_minutes=minutes,
            warnings=warnings,
            created_at=previous.created_at if previous else now,
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "session_id": self.session_id,
            "source_kind": self.source_kind,
            "import_kind": self.import_kind.value,
            "name": self.name,
            "title": self.title,
            "raw_markdown": self.raw_markdown,
            "normalized_text": self.normalized_text,
            "content_hash": self.content_hash,
            "version": self.version,
            "word_count": self.word_count,
            "estimated_audio_minutes": self.estimated_audio_minutes,
            "conversion_mode": self.conversion_mode.value,
            "target_length": self.target_length.value,
            "focus_instructions": self.focus_instructions,
            "warnings": list(self.warnings),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EpisodeSource":
        return cls(
            source_id=str(payload["source_id"]),
            session_id=str(payload["session_id"]),
            source_kind="markdown",
            import_kind=SourceImportKind(payload["import_kind"]),
            name=str(payload["name"]),
            title=str(payload["title"]),
            raw_markdown=str(payload["raw_markdown"]),
            normalized_text=str(payload["normalized_text"]),
            content_hash=str(payload["content_hash"]),
            version=int(payload["version"]),
            word_count=int(payload["word_count"]),
            estimated_audio_minutes=float(payload["estimated_audio_minutes"]),
            conversion_mode=SourceConversionMode(payload["conversion_mode"]),
            target_length=SourceTargetLength(payload["target_length"]),
            focus_instructions=str(payload.get("focus_instructions") or ""),
            warnings=[str(item) for item in payload.get("warnings", [])],
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
        )
