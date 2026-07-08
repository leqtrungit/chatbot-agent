from __future__ import annotations

from app.modules.document.pipeline.embed import embed_chunks


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
