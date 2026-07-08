from __future__ import annotations

from app.modules.document.pipeline.chunk import chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []


def test_whitespace_only_returns_no_chunks():
    assert chunk_text("   \n\t  ") == []


def test_short_text_single_chunk():
    text = "hello world"
    chunks = chunk_text(text, size=1000, overlap=200)
    assert chunks == [text]


def test_no_empty_chunks_produced():
    text = "a" * 2500
    chunks = chunk_text(text, size=1000, overlap=200)
    assert all(c.strip() for c in chunks)
    assert all(len(c) > 0 for c in chunks)


def test_chunk_sizes_bounded():
    text = "a" * 2500
    chunks = chunk_text(text, size=1000, overlap=200)
    assert all(len(c) <= 1000 for c in chunks)


def test_overlap_between_consecutive_chunks():
    text = "".join(str(i % 10) for i in range(2500))
    size, overlap = 1000, 200
    chunks = chunk_text(text, size=size, overlap=overlap)
    assert len(chunks) >= 2
    # the tail of chunk[i] overlapping region should match head of chunk[i+1]
    for i in range(len(chunks) - 1):
        tail = chunks[i][-overlap:]
        head = chunks[i + 1][:overlap]
        assert tail == head


def test_full_reconstruction_covers_text():
    text = "x" * 3500
    chunks = chunk_text(text, size=1000, overlap=200)
    # stepping by (size - overlap) should reconstruct full coverage
    step = 1000 - 200
    expected_starts = list(range(0, len(text), step))
    assert len(chunks) == len([s for s in expected_starts if s < len(text)])


def test_invalid_overlap_raises():
    import pytest

    with pytest.raises(ValueError):
        chunk_text("some text", size=100, overlap=100)

    with pytest.raises(ValueError):
        chunk_text("some text", size=100, overlap=150)
