"""Embed text chunks in batches via an injected EmbeddingProvider."""

from __future__ import annotations

from app.agent.providers.base import EmbeddingProvider


class EmbeddingDimensionMismatch(ValueError):
    """Raised when a model returns vectors the ``embedding`` column cannot store."""


async def embed_chunks(
    chunks: list[str],
    provider: EmbeddingProvider,
    model: str,
    batch_size: int = 16,
    expected_dim: int | None = None,
) -> list[list[float]]:
    """Embed ``chunks`` using ``provider`` in batches of ``batch_size``, preserving order.

    ``expected_dim`` guards against a configured model whose output width does
    not match the fixed ``Vector(EMBEDDING_DIM)`` column: failing here names the
    model and both dimensions, where Postgres would only reject the insert.
    """
    if not chunks:
        return []

    vectors: list[list[float]] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        batch_vectors = await provider.embed(batch, model=model)
        if expected_dim is not None:
            for vector in batch_vectors:
                if len(vector) != expected_dim:
                    raise EmbeddingDimensionMismatch(
                        f"model {model!r} returned {len(vector)}-dimensional vectors, "
                        f"but the embedding column stores {expected_dim} dimensions. "
                        "Changing embedding dimension requires a migration and a re-ingest "
                        "of every document."
                    )
        vectors.extend(batch_vectors)
    return vectors
