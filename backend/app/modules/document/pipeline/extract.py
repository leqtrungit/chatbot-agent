"""Extract plain text from uploaded documents by mime type."""

from __future__ import annotations

from docx import Document as DocxDocument
from pypdf import PdfReader

_PDF_MIME = "application/pdf"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_TEXT_MIMES = {"text/plain", "text/markdown"}


def extract_text(path: str, mime_type: str) -> str:
    """Extract text content from the file at ``path`` given its ``mime_type``."""
    if mime_type == _PDF_MIME:
        return _extract_pdf(path)
    if mime_type == _DOCX_MIME:
        return _extract_docx(path)
    if mime_type in _TEXT_MIMES:
        return _extract_plain(path)
    raise ValueError(f"Unsupported mime type: {mime_type}")


def _extract_pdf(path: str) -> str:
    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def _extract_docx(path: str) -> str:
    doc = DocxDocument(path)
    return "\n".join(p.text for p in doc.paragraphs)


def _extract_plain(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()
