"""Unit tests for knowledge service logic (pure functions, no DB)."""

from __future__ import annotations

import uuid

import pytest

from app.knowledge.service import (
    slugify,
    KnowledgeBaseConflictError,
    KnowledgeBaseNotFoundError,
    DocumentNotFoundError,
    UnsupportedFileTypeError,
)
from app.knowledge.storage import validate_file_type


class TestSlugify:
    """Tests for slug generation."""

    def test_slugify_simple_name(self):
        """Test basic slug generation."""
        assert slugify("My Knowledge Base") == "my-knowledge-base"

    def test_slugify_with_special_chars(self):
        """Test slug removes special characters."""
        assert slugify("API & Tools!") == "api-tools"

    def test_slugify_with_numbers(self):
        """Test slug preserves numbers."""
        assert slugify("API v2.0") == "api-v2-0"

    def test_slugify_with_leading_trailing_spaces(self):
        """Test slug strips leading/trailing spaces."""
        assert slugify("  knowledge base  ") == "knowledge-base"

    def test_slugify_empty_fallback(self):
        """Test fallback slug for empty string."""
        assert slugify("!!!") == "knowledge-base"

    def test_slugify_lowercase(self):
        """Test slug is lowercase."""
        assert slugify("UPPERCASE") == "uppercase"


class TestFileTypeValidation:
    """Tests for file type validation."""

    def test_validate_pdf_by_mime(self):
        """Test PDF validation by MIME type."""
        mime = validate_file_type("doc.pdf", "application/pdf")
        assert mime == "application/pdf"

    def test_validate_docx_by_mime(self):
        """Test DOCX validation by MIME type."""
        mime = validate_file_type("doc.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def test_validate_txt_by_mime(self):
        """Test TXT validation by MIME type."""
        mime = validate_file_type("notes.txt", "text/plain")
        assert mime == "text/plain"

    def test_validate_markdown_by_mime(self):
        """Test Markdown validation by MIME type."""
        mime = validate_file_type("readme.md", "text/markdown")
        assert mime == "text/markdown"

    def test_validate_fallback_by_extension(self):
        """Test validation falls back to extension if MIME type is generic."""
        mime = validate_file_type("document.pdf", "application/octet-stream")
        # Should detect PDF by extension
        assert mime == "application/pdf"

    def test_validate_unsupported_type_raises(self):
        """Test unsupported type raises exception."""
        with pytest.raises(UnsupportedFileTypeError):
            validate_file_type("virus.exe", "application/x-msdownload")

    def test_validate_generic_octet_stream_without_extension_raises(self):
        """Test generic octet-stream with unknown extension raises."""
        with pytest.raises(UnsupportedFileTypeError):
            validate_file_type("upload", "application/octet-stream")


class TestExceptionMessages:
    """Tests that exceptions have meaningful messages."""

    def test_knowledge_base_conflict_error_message(self):
        """Test KnowledgeBaseConflictError message is informative."""
        exc = KnowledgeBaseConflictError("KB 'test' already exists")
        assert "test" in str(exc)

    def test_knowledge_base_not_found_error(self):
        """Test KnowledgeBaseNotFoundError can be raised."""
        with pytest.raises(KnowledgeBaseNotFoundError):
            raise KnowledgeBaseNotFoundError(str(uuid.uuid4()))

    def test_document_not_found_error(self):
        """Test DocumentNotFoundError can be raised."""
        with pytest.raises(DocumentNotFoundError):
            raise DocumentNotFoundError(str(uuid.uuid4()))

    def test_unsupported_file_type_error(self):
        """Test UnsupportedFileTypeError has message."""
        exc = UnsupportedFileTypeError("Unsupported: .xyz")
        assert "xyz" in str(exc)
