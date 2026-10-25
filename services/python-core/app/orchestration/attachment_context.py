from __future__ import annotations

from dataclasses import dataclass

from app.domain.attachment import AttachmentKind
from app.domain.transcript import Speaker, TranscriptRecord
from app.providers.llm.base import ImageInput
from app.storage.project_store import ProjectStore

# Every interview turn is a stateless provider call, so earlier attachments are
# re-sent; these bounds keep long conversations within request limits.
MAX_PROMPT_IMAGES = 6
DOCUMENT_CHARACTER_BUDGET = 40_000


@dataclass(frozen=True, slots=True)
class AttachmentContext:
    prompt_block: str
    images: tuple[ImageInput, ...]


def build_attachment_context(store: ProjectStore, transcript: TranscriptRecord) -> AttachmentContext:
    attachments = [
        attachment
        for turn in transcript.turns
        if turn.speaker == Speaker.USER
        for attachment in turn.attachments
    ]
    if not attachments:
        return AttachmentContext(prompt_block="", images=())

    images = [item for item in attachments if item.kind == AttachmentKind.IMAGE]
    sent_images = images[-MAX_PROMPT_IMAGES:]
    omitted_images = images[: len(images) - len(sent_images)]

    document_blocks: list[str] = []
    omitted_documents: list[str] = []
    remaining = DOCUMENT_CHARACTER_BUDGET
    # Newest documents win the budget; blocks are restored to chronological order.
    for document in reversed([item for item in attachments if item.kind == AttachmentKind.DOCUMENT]):
        if remaining <= 0:
            omitted_documents.append(document.name)
            continue
        text = store.read_attachment_text(document)
        if len(text) > remaining:
            text = text[:remaining].rstrip() + "\n[Attachment truncated for this turn.]"
        remaining -= len(text)
        document_blocks.insert(0, f"BEGIN ATTACHMENT: {document.name}\n{text}\nEND ATTACHMENT")

    lines: list[str] = []
    if sent_images:
        names = ", ".join(item.name for item in sent_images)
        lines.append(f"Images attached by the user, supplied as image input with this request in this order: {names}.")
    if omitted_images:
        names = ", ".join(item.name for item in omitted_images)
        lines.append(f"Older images not re-sent this turn (rely on earlier discussion of them): {names}.")
    if omitted_documents:
        lines.append(f"Older documents omitted for length: {', '.join(reversed(omitted_documents))}.")
    lines.extend(document_blocks)
    return AttachmentContext(
        prompt_block="\n\n".join(lines),
        images=tuple(
            ImageInput(name=item.name, mime_type=item.mime_type, data=store.read_attachment_bytes(item))
            for item in sent_images
        ),
    )
