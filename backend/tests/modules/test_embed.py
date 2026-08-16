from __future__ import annotations

import pytest

from app.modules.document.pipeline.embed import EmbeddingDimensionMismatch, embed_chunks
from tests.conftest import MockEmbeddingProvider


async def test_embed_chunks_preserves_order_and_count(mock_embedding):
    chunks = [f"chunk {i}" for i in range(5)]
    vectors = await embed_chunks(chunks, mock_embedding, model="nomic-embed-text")
    assert len(vectors) == 5
    assert mock_embedding.embedded == chunks


async def test_embed_chunks_batches(mock_embedding):
    chunks = [f"chunk {i}" for i in range(10)]
    vectors = await embed_chunks(chunks, mock_embedding, model="nomic-embed-text", batch_size=3)
    assert len(vectors) == 10
    assert mock_embedding.embedded == chunks


async def test_embed_chunks_empty_list(mock_embedding):
    vectors = await embed_chunks([], mock_embedding, model="nomic-embed-text")
    assert vectors == []


async def test_embed_chunks_accepts_vectors_matching_expected_dim(mock_embedding):
    vectors = await embed_chunks(
        ["a", "b"], mock_embedding, model="nomic-embed-text", expected_dim=768
    )
    assert len(vectors) == 2


async def test_embed_chunks_rejects_vectors_with_wrong_dim():
    """A model whose dimension differs from the Vector() column must fail loudly
    here rather than be rejected opaquely by Postgres on insert."""
    provider = MockEmbeddingProvider(dim=1536)
    with pytest.raises(EmbeddingDimensionMismatch) as excinfo:
        await embed_chunks(["a"], provider, model="text-embedding-3-small", expected_dim=768)
    assert "1536" in str(excinfo.value)
    assert "768" in str(excinfo.value)


async def test_embed_chunks_skips_dim_check_when_expected_dim_is_none():
    provider = MockEmbeddingProvider(dim=1536)
    vectors = await embed_chunks(["a"], provider, model="whatever")
    assert len(vectors[0]) == 1536
