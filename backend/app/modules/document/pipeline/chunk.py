"""Character-based text chunking with overlap."""

from __future__ import annotations


def chunk_text(text: str, size: int = 1000, overlap: int = 200) -> list[str]:
    """Split ``text`` into overlapping chunks of at most ``size`` characters.

    Returns an empty list for blank input. Never returns empty/blank chunks.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be non-negative and smaller than size")

    stripped = text.strip()
    if not stripped:
        return []

    step = size - overlap
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        if end == length:
            break
        start += step
    return chunks
