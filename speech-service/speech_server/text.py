import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    text: str
    paragraph_end: bool


def split_paragraph(text: str) -> list[str]:
    """Prefer sentence boundaries, then commas; always keep every character <=120.

    Use the minimum number of slices. When 80..120 is mathematically possible,
    every slice is in that range. Otherwise balance the short remainder.
    Short sentences (<20 chars) lose their ending boundary and merge forward.
    """
    if len(text) <= 120:
        return [text]
    primary = set()
    offset = 0
    pending = ""
    for match in re.finditer(r"[^。！？；]+[。！？；]*|[。！？；]+", text):
        sentence = match.group()
        pending += sentence
        offset += len(sentence)
        # A short sentence must join its following sentence, not end a slice.
        if len(sentence) >= 20 and len(pending) >= 20:
            primary.add(offset)
            pending = ""
    secondary = {m.end() for m in re.finditer(r"[，、,]", text)}
    count = math.ceil(len(text) / 120)
    minimum = min(80, len(text) // count)
    parts = []
    start = 0
    for remaining in range(count, 1, -1):
        length = len(text) - start
        low = max(minimum, length - (remaining - 1) * 120)
        high = min(120, length - (remaining - 1) * minimum)
        ideal = length / remaining

        def score(size: int, start: int = start, ideal: float = ideal) -> float:
            end = start + size
            boundary_cost = 0 if end in primary else 12 if end in secondary else 30
            return boundary_cost + abs(size - ideal) / 4

        size = min(range(low, high + 1), key=score)
        parts.append(text[start : start + size])
        start += size
    parts.append(text[start:])
    return parts


def split_text(text: str) -> list[TextChunk]:
    paragraphs = [re.sub(r"[^\S\n]+", " ", p).strip() for p in text.splitlines()]
    paragraphs = [p for p in paragraphs if p]
    merged = []
    pending = ""
    for paragraph in paragraphs:
        pending += (" " if pending else "") + paragraph
        if len(pending) >= 20:
            merged.append(pending)
            pending = ""
    if pending:
        if merged:
            merged[-1] += " " + pending
        else:
            merged.append(pending)
    result = []
    for paragraph in merged:
        parts = split_paragraph(paragraph)
        result.extend(TextChunk(p, i == len(parts) - 1) for i, p in enumerate(parts))
    return result
