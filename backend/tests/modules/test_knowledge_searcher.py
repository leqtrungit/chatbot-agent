from __future__ import annotations

from app.modules.document.models import Document, DocumentChunk, DocumentStatus
from app.modules.domain.models import Domain
from app.modules.knowledge.searcher import PgVectorKnowledgeSearcher

DIM = 768


def _vector(*nonzero: tuple[int, float]) -> list[float]:
    v = [0.0] * DIM
    for index, value in nonzero:
        v[index] = value
    return v


class _StubQueryEmbedding:
    """Returns a fixed, caller-chosen vector regardless of the query text."""

    def __init__(self, vector: list[float]):
        self.vector = vector
        self.embedded: list[str] = []

    async def embed(self, texts: list[str], *, model: str) -> list[list[float]]:
        self.embedded.extend(texts)
        return [self.vector for _ in texts]


async def _seed(session_maker):
    async with session_maker() as session:
        domain_a = Domain(name="Domain A", slug="domain-a")
        domain_b = Domain(name="Domain B", slug="domain-b")
        session.add_all([domain_a, domain_b])
        await session.flush()

        doc_a = Document(
            domain_id=domain_a.id,
            filename="a.txt",
            mime_type="text/plain",
            status=DocumentStatus.COMPLETED.value,
        )
        doc_a_pending = Document(
            domain_id=domain_a.id,
            filename="pending.txt",
            mime_type="text/plain",
            status=DocumentStatus.PENDING.value,
        )
        doc_b = Document(
            domain_id=domain_b.id,
            filename="b.txt",
            mime_type="text/plain",
            status=DocumentStatus.COMPLETED.value,
        )
        session.add_all([doc_a, doc_a_pending, doc_b])
        await session.flush()

        # Domain A chunks: closest to closest to query vector [1,0,...]
        chunk_closest = DocumentChunk(
            document_id=doc_a.id,
            chunk_index=0,
            content="closest chunk",
            embedding=_vector((0, 1.0)),
        )
        chunk_mid = DocumentChunk(
            document_id=doc_a.id,
            chunk_index=1,
            content="mid chunk",
            embedding=_vector((0, 0.8), (1, 0.6)),
        )
        chunk_far = DocumentChunk(
            document_id=doc_a.id,
            chunk_index=2,
            content="far chunk",
            embedding=_vector((1, 1.0)),
        )
        # A pending document's chunk must never show up.
        chunk_pending = DocumentChunk(
            document_id=doc_a_pending.id,
            chunk_index=0,
            content="pending chunk",
            embedding=_vector((0, 1.0)),
        )
        # Domain B chunk must never leak into a Domain A search.
        chunk_other_domain = DocumentChunk(
            document_id=doc_b.id,
            chunk_index=0,
            content="other domain chunk",
            embedding=_vector((0, 1.0)),
        )
        session.add_all(
            [chunk_closest, chunk_mid, chunk_far, chunk_pending, chunk_other_domain]
        )
        await session.commit()

        return {"domain_a": domain_a.id, "domain_b": domain_b.id}


async def test_search_orders_by_cosine_similarity_and_scopes_to_domain(session_maker):
    ids = await _seed(session_maker)

    query_embedding = _StubQueryEmbedding(_vector((0, 1.0)))
    searcher = PgVectorKnowledgeSearcher(session_maker, query_embedding, "test-model")

    hits = await searcher.search("what is it", str(ids["domain_a"]), limit=5)

    assert query_embedding.embedded == ["what is it"]
    contents = [hit.content for hit in hits]
    # only completed-document chunks from domain A, ordered nearest-first
    assert contents == ["closest chunk", "mid chunk", "far chunk"]
    assert hits[0].score > hits[1].score > hits[2].score
    assert hits[0].metadata["filename"] == "a.txt"
    assert hits[0].metadata["chunk_index"] == 0
    assert "document_id" in hits[0].metadata


async def test_search_respects_limit(session_maker):
    ids = await _seed(session_maker)

    query_embedding = _StubQueryEmbedding(_vector((0, 1.0)))
    searcher = PgVectorKnowledgeSearcher(session_maker, query_embedding, "test-model")

    hits = await searcher.search("q", str(ids["domain_a"]), limit=1)
    assert len(hits) == 1
    assert hits[0].content == "closest chunk"


async def test_search_domain_with_no_chunks_returns_empty(session_maker):
    ids = await _seed(session_maker)
    query_embedding = _StubQueryEmbedding(_vector((0, 1.0)))
    searcher = PgVectorKnowledgeSearcher(session_maker, query_embedding, "test-model")

    hits = await searcher.search("q", str(ids["domain_b"]), limit=5)
    assert [h.content for h in hits] == ["other domain chunk"]
