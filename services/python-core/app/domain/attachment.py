from __future__ import annotations

import io
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePath
from typing import Any
from uuid import uuid4

from app.domain.common import utc_now_iso

ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
MAX_ATTACHMENTS_PER_TURN = 8

IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
DOCUMENT_EXTENSIONS = {
    "text/plain": ".txt",
    "text/markdown": ".md",
    "text/csv": ".csv",
    "application/json": ".json",
    "application/pdf": ".pdf",
}
# Browsers often report "" or application/octet-stream for .md, so the file
# extension decides first and the declared type is only a fallback.
_MIME_BY_EXTENSION = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".pdf": "application/pdf",
}
_IMAGE_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
}


class AttachmentKind(StrEnum):
    IMAGE = "image"
    DOCUMENT = "document"


def new_attachment_id() -> str:
    return f"att_{uuid4().hex}"


def resolve_attachment_mime_type(filename: str, declared_type: str) -> str:
    by_extension = _MIME_BY_EXTENSION.get(PurePath(filename).suffix.lower())
    if by_extension:
        return by_extension
    declared = declared_type.split(";", 1)[0].strip().lower()
    if declared in IMAGE_EXTENSIONS or declared in DOCUMENT_EXTENSIONS:
        return declared
    raise ValueError(
        "Unsupported attachment type. Attach PNG, JPEG, WebP, or GIF images, "
        "or TXT, Markdown, CSV, JSON, or PDF documents."
    )


def attachment_kind(mime_type: str) -> AttachmentKind:
    if mime_type in IMAGE_EXTENSIONS:
        return AttachmentKind.IMAGE
    if mime_type in DOCUMENT_EXTENSIONS:
        return AttachmentKind.DOCUMENT
    raise ValueError(f"Unsupported attachment type: {mime_type}.")


def validate_image_bytes(data: bytes, mime_type: str) -> None:
    if mime_type == "image/webp":
        valid = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    else:
        valid = data.startswith(_IMAGE_SIGNATURES[mime_type])
    if not valid:
        raise ValueError(f"Attachment content is not a valid {mime_type} image.")


def extract_document_text(data: bytes, mime_type: str) -> str:
    """Return the plain text a model should read for one document attachment."""
    if mime_type == "application/pdf":
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages)
        except PdfReadError as exc:
            raise ValueError(f"PDF attachment could not be read: {exc}") from exc
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text attachments must be UTF-8 encoded.") from exc
    text = text.replace("\r\n", "\n").strip()
    if not text:
        raise ValueError(
            "Attachment contains no extractable text. Scanned PDFs are not supported; attach it as an image instead."
        )
    return text


@dataclass(frozen=True, slots=True)
class Attachment:
    session_id: str
    kind: AttachmentKind
    mime_type: str
    name: str
    size_bytes: int
    sha256: str
    attachment_id: str = field(default_factory=new_attachment_id)
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def blob_name(self) -> str:
        extension = IMAGE_EXTENSIONS.get(self.mime_type) or DOCUMENT_EXTENSIONS[self.mime_type]
        return f"{self.sha256}{extension}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "attachment_id": self.attachment_id,
            "session_id": self.session_id,
            "kind": self.kind.value,
            "mime_type": self.mime_type,
            "name": self.name,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Attachment":
        return cls(
            attachment_id=str(payload["attachment_id"]),
            session_id=str(payload["session_id"]),
            kind=AttachmentKind(str(payload["kind"])),
            mime_type=str(payload["mime_type"]),
            name=str(payload["name"]),
            size_bytes=int(payload["size_bytes"]),
            sha256=str(payload["sha256"]),
            created_at=str(payload["created_at"]),
        )
