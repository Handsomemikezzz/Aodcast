from __future__ import annotations

import re
from dataclasses import dataclass

# Sentence-ending punctuation (CJK + ASCII + half-width variants).
_SENTENCE_END = "。！？!?…；;\n"
_CLOSING_QUOTES = "\"'””’』」)）】』]"

# Minimum characters to keep a chunk on its own. Shorter fragments are glued
# to the neighbouring chunk to avoid single-word micro-renders that would
# produce choppy audio and waste model overhead.
_MIN_CHUNK_CHARS = 28
# Soft upper bound; once a pending chunk crosses this we flush even if the
# current sentence has not ended, so the MLX model never chokes on a single
# 5k-character paragraph.
_SOFT_MAX_CHUNK_CHARS = 320


@dataclass(frozen=True, slots=True)
class ScriptChunk:
    index: int
    text: str


def split_script_into_chunks(script: str) -> list[ScriptChunk]:
    """Split a podcast script into sentence-level chunks ready for TTS.

    The split is intentionally conservative:

    - each returned chunk is a coherent sentence (or a short paragraph)
    - fragments shorter than the minimum character budget are merged with
      their neighbour, so prosody stays natural
    - runs longer than the soft maximum fall back to a whitespace split so
      we never pipe a pathological paragraph into a single synthesis call
    - empty lines and stripped whitespace are discarded, but paragraph
      boundaries are implicit in the sentence ordering
    """

    cleaned = script.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return []

    raw_sentences = _split_on_sentence_boundaries(cleaned)
    merged = _merge_short_sentences(raw_sentences)
    final = _enforce_soft_max_length(merged)
    return [ScriptChunk(index=i, text=text) for i, text in enumerate(final) if text.strip()]


def _split_on_sentence_boundaries(text: str) -> list[str]:
    sentences: list[str] = []
    buffer: list[str] = []
    length = len(text)
    i = 0
    while i < length:
        ch = text[i]
        buffer.append(ch)
        if ch in _SENTENCE_END:
            # Keep any trailing closing quotes attached to the sentence.
            j = i + 1
            while j < length and text[j] in _CLOSING_QUOTES:
                buffer.append(text[j])
                j += 1
            sentence = "".join(buffer).strip()
            if sentence:
                sentences.append(sentence)
            buffer = []
            i = j
            continue
        i += 1

    remainder = "".join(buffer).strip()
    if remainder:
        sentences.append(remainder)
    return sentences


def _merge_short_sentences(sentences: list[str]) -> list[str]:
    if not sentences:
        return []
    merged: list[str] = []
    for sentence in sentences:
        if merged and len(merged[-1]) < _MIN_CHUNK_CHARS:
            merged[-1] = _join_with_space(merged[-1], sentence)
        else:
            merged.append(sentence)
    if len(merged) >= 2 and len(merged[-1]) < _MIN_CHUNK_CHARS:
        tail = merged.pop()
        merged[-1] = _join_with_space(merged[-1], tail)
    return merged


def _enforce_soft_max_length(sentences: list[str]) -> list[str]:
    out: list[str] = []
    for sentence in sentences:
        if len(sentence) <= _SOFT_MAX_CHUNK_CHARS:
            out.append(sentence)
            continue
        out.extend(_wrap_long_sentence(sentence))
    return out


def _wrap_long_sentence(sentence: str) -> list[str]:
    # Prefer splitting on commas, semicolons or whitespace to avoid cutting
    # inside a word. We never split inside ASCII tokens because that would
    # produce broken phonemes.
    tokens = re.split(r"([，,、:：\s])", sentence)
    chunks: list[str] = []
    current = ""
    for token in tokens:
        if not token:
            continue
        if len(current) + len(token) > _SOFT_MAX_CHUNK_CHARS and current.strip():
            chunks.append(current.strip())
            current = token.lstrip()
        else:
            current += token
    if current.strip():
        chunks.append(current.strip())
    return chunks or [sentence]


def _join_with_space(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if left[-1].isspace() or right[0].isspace():
        return f"{left}{right}"
    # Only insert a space if both sides are latin-ish; CJK stays glued.
    if _is_latin(left[-1]) and _is_latin(right[0]):
        return f"{left} {right}"
    return f"{left}{right}"


def _is_latin(ch: str) -> bool:
    return bool(ch) and ord(ch) < 0x3000
