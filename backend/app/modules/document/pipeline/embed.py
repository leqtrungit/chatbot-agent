"""Embed text chunks in batches via an injected EmbeddingProvider."""

from __future__ import annotations

from app.agent.providers.base import EmbeddingProvider


async def embed_chunks(
    chunks: list[str],
    provider: EmbeddingProvider,
    model: str,
    batch_size: int = 16,
) -> list[list[float]]:
    """Embed ``chunks`` using ``provider`` in batches of ``batch_size``, preserving order."""
    if not chunks:
        return []

    vectors: list[list[float]] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        batch_vectors = await provider.embed(batch, model=model)
        vectors.extend(batch_vectors)
    return vectors
