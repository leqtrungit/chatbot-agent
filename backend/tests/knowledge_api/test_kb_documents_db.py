"""Integration tests for knowledge bases and documents (database layer).

Tests org-scoped isolation (NFR-SEC1) and core CRUD operations.
Requires postgres running via docker compose.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import Document, KnowledgeBase, DocumentStatus
from app.knowledge.schemas import KnowledgeBaseCreate, KnowledgeBaseUpdate
from app.knowledge.service import (
    create_knowledge_base,
    get_knowledge_base,
    list_knowledge_bases,
    update_knowledge_base,
    delete_knowledge_base,
    create_document,
    get_document,
    list_documents,
    delete_document,
    KnowledgeBaseNotFoundError,
    KnowledgeBaseConflictError,
    DocumentNotFoundError,
)
from app.knowledge.storage import UnsupportedFileTypeError
from app.orgs.models import Organization


pytestmark = pytest.mark.asyncio


# ============================================================================
# Fixtures
# ============================================================================


async def _create_org(session: AsyncSession, name: str, slug: str) -> Organization:
    """Helper to create an organization."""
    org = Organization(
        id=uuid.uuid4(),
        name=name,
        slug=slug,
        status="active",
    )
    session.add(org)
    await session.commit()
    await session.refresh(org)
    return org


async def _create_kb(
    session: AsyncSession,
    org_id: uuid.UUID,
    name: str,
    slug: str | None = None,
    description: str | None = None,
) -> KnowledgeBase:
    """Helper to create a knowledge base."""
    data = KnowledgeBaseCreate(name=name, slug=slug, description=description)
    return await create_knowledge_base(session, org_id, data)


@pytest.fixture
async def org_a(db_session: AsyncSession) -> Organization:
    """Organization A for multi-org tests."""
    return await _create_org(db_session, "Org A", "org-a")


@pytest.fixture
async def org_b(db_session: AsyncSession) -> Organization:
    """Organization B for multi-org tests."""
    return await _create_org(db_session, "Org B", "org-b")


@pytest.fixture
async def kb_a(db_session: AsyncSession, org_a: Organization) -> KnowledgeBase:
    """Knowledge base in Org A."""
    return await _create_kb(db_session, org_a.id, "Product Docs", description="Products KB")


# ============================================================================
# Knowledge Base Tests
# ============================================================================


class TestKnowledgeBaseCreate:
    """Tests for creating knowledge bases."""

    async def test_create_kb_autogenerates_slug(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that slug is auto-generated from name when not provided."""
        data = KnowledgeBaseCreate(name="Product Manuals")
        kb = await create_knowledge_base(db_session, org_a.id, data)

        assert kb.name == "Product Manuals"
        assert kb.slug == "product-manuals"
        assert kb.org_id == org_a.id

    async def test_create_kb_with_explicit_slug(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that explicit slug is preserved."""
        data = KnowledgeBaseCreate(name="Docs", slug="my-custom-slug")
        kb = await create_knowledge_base(db_session, org_a.id, data)

        assert kb.slug == "my-custom-slug"
        assert kb.name == "Docs"

    async def test_create_kb_with_description(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that description is stored."""
        data = KnowledgeBaseCreate(
            name="FAQ", description="Frequently asked questions"
        )
        kb = await create_knowledge_base(db_session, org_a.id, data)

        assert kb.description == "Frequently asked questions"


class TestKnowledgeBaseConflict:
    """Tests for knowledge base conflict detection."""

    async def test_duplicate_name_same_org_raises_conflict(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that duplicate KB name in same org raises KnowledgeBaseConflictError."""
        await _create_kb(db_session, org_a.id, "Docs")

        with pytest.raises(KnowledgeBaseConflictError):
            await _create_kb(db_session, org_a.id, "Docs")

    async def test_duplicate_slug_same_org_raises_conflict(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that duplicate KB slug in same org raises KnowledgeBaseConflictError."""
        await _create_kb(db_session, org_a.id, "Documentation", slug="docs")

        with pytest.raises(KnowledgeBaseConflictError):
            await _create_kb(db_session, org_a.id, "Other Name", slug="docs")

    async def test_duplicate_name_different_orgs_allowed(
        self, db_session: AsyncSession, org_a: Organization, org_b: Organization
    ) -> None:
        """Test that same KB name in different orgs is allowed (org isolation)."""
        kb_a = await _create_kb(db_session, org_a.id, "Docs")
        kb_b = await _create_kb(db_session, org_b.id, "Docs")

        assert kb_a.id != kb_b.id
        assert kb_a.org_id == org_a.id
        assert kb_b.org_id == org_b.id


class TestKnowledgeBaseRead:
    """Tests for reading knowledge bases."""

    async def test_list_knowledge_bases_same_org(
        self, db_session: AsyncSession, org_a: Organization, org_b: Organization
    ) -> None:
        """Test that list_knowledge_bases only returns KBs from the specified org."""
        kb_a1 = await _create_kb(db_session, org_a.id, "KB A1")
        kb_a2 = await _create_kb(db_session, org_a.id, "KB A2")
        kb_b = await _create_kb(db_session, org_b.id, "KB B")

        kbs_a = await list_knowledge_bases(db_session, org_a.id)
        kbs_b = await list_knowledge_bases(db_session, org_b.id)

        assert len(kbs_a) == 2
        assert len(kbs_b) == 1
        assert kb_a1 in kbs_a
        assert kb_a2 in kbs_a
        assert kb_b not in kbs_a
        assert kb_b in kbs_b

    async def test_get_knowledge_base_org_scoped(
        self, db_session: AsyncSession, org_a: Organization, org_b: Organization
    ) -> None:
        """Test that get_knowledge_base enforces org isolation."""
        kb = await _create_kb(db_session, org_a.id, "Docs")

        # Org A can get their own KB
        retrieved = await get_knowledge_base(db_session, org_a.id, kb.id)
        assert retrieved.id == kb.id

        # Org B cannot get Org A's KB
        with pytest.raises(KnowledgeBaseNotFoundError):
            await get_knowledge_base(db_session, org_b.id, kb.id)

    async def test_get_knowledge_base_nonexistent(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that getting nonexistent KB raises KnowledgeBaseNotFoundError."""
        fake_id = uuid.uuid4()
        with pytest.raises(KnowledgeBaseNotFoundError):
            await get_knowledge_base(db_session, org_a.id, fake_id)


class TestKnowledgeBaseUpdate:
    """Tests for updating knowledge bases."""

    async def test_update_kb_name_and_slug(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that KB name and slug can be updated."""
        kb = await _create_kb(db_session, org_a.id, "Old Name", slug="old-slug")

        data = KnowledgeBaseUpdate(name="New Name", slug="new-slug")
        updated = await update_knowledge_base(db_session, org_a.id, kb.id, data)

        assert updated.name == "New Name"
        assert updated.slug == "new-slug"

        # Verify persistence
        retrieved = await get_knowledge_base(db_session, org_a.id, kb.id)
        assert retrieved.name == "New Name"
        assert retrieved.slug == "new-slug"

    async def test_update_kb_description(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that KB description can be updated."""
        kb = await _create_kb(
            db_session, org_a.id, "Docs", description="Original description"
        )

        data = KnowledgeBaseUpdate(description="Updated description")
        updated = await update_knowledge_base(db_session, org_a.id, kb.id, data)

        assert updated.description == "Updated description"

    async def test_update_kb_raises_conflict_on_duplicate_name(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that update to duplicate name raises KnowledgeBaseConflictError."""
        kb1 = await _create_kb(db_session, org_a.id, "Docs1")
        await _create_kb(db_session, org_a.id, "Docs2")

        data = KnowledgeBaseUpdate(name="Docs2")
        with pytest.raises(KnowledgeBaseConflictError):
            await update_knowledge_base(db_session, org_a.id, kb1.id, data)

    async def test_update_kb_org_scoped(
        self, db_session: AsyncSession, org_a: Organization, org_b: Organization
    ) -> None:
        """Test that KB update enforces org isolation."""
        kb = await _create_kb(db_session, org_a.id, "Docs")

        data = KnowledgeBaseUpdate(name="Updated")
        with pytest.raises(KnowledgeBaseNotFoundError):
            await update_knowledge_base(db_session, org_b.id, kb.id, data)


class TestKnowledgeBaseDelete:
    """Tests for deleting knowledge bases."""

    async def test_delete_knowledge_base(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that KB deletion works and is persisted."""
        kb = await _create_kb(db_session, org_a.id, "Docs")

        await delete_knowledge_base(db_session, org_a.id, kb.id)

        with pytest.raises(KnowledgeBaseNotFoundError):
            await get_knowledge_base(db_session, org_a.id, kb.id)

    async def test_delete_kb_org_scoped(
        self, db_session: AsyncSession, org_a: Organization, org_b: Organization
    ) -> None:
        """Test that KB deletion enforces org isolation."""
        kb = await _create_kb(db_session, org_a.id, "Docs")

        # Org B cannot delete Org A's KB
        with pytest.raises(KnowledgeBaseNotFoundError):
            await delete_knowledge_base(db_session, org_b.id, kb.id)

        # KB still exists for Org A
        retrieved = await get_knowledge_base(db_session, org_a.id, kb.id)
        assert retrieved.id == kb.id

    async def test_delete_kb_nonexistent(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that deleting nonexistent KB raises DocumentNotFoundError."""
        fake_id = uuid.uuid4()
        with pytest.raises(KnowledgeBaseNotFoundError):
            await delete_knowledge_base(db_session, org_a.id, fake_id)


# ============================================================================
# Document Tests
# ============================================================================


class TestDocumentCreate:
    """Tests for creating documents."""

    async def test_create_document_txt_file(
        self,
        db_session: AsyncSession,
        org_a: Organization,
        kb_a: KnowledgeBase,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test uploading a .txt document with status=pending."""
        # Mock storage settings to use tmp_path
        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)
        monkeypatch.setattr("app.knowledge.storage.get_settings", lambda: mock_settings)

        filename = "readme.txt"
        content = b"Hello, this is a test document."
        mime_type = "text/plain"

        doc = await create_document(
            db_session, org_a.id, kb_a.id, filename, content, mime_type
        )

        assert doc.filename == filename
        assert doc.mime_type == "text/plain"
        assert doc.status == DocumentStatus.PENDING.value
        assert doc.knowledge_base_id == kb_a.id
        assert doc.org_id == org_a.id

        # Verify file is stored on disk
        expected_path = tmp_path / str(org_a.id) / f"{doc.id}.txt"
        assert expected_path.exists()
        assert expected_path.read_bytes() == content

    async def test_create_document_pdf_file(
        self,
        db_session: AsyncSession,
        org_a: Organization,
        kb_a: KnowledgeBase,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test uploading a .pdf document."""
        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)
        monkeypatch.setattr("app.knowledge.storage.get_settings", lambda: mock_settings)

        filename = "guide.pdf"
        content = b"%PDF-1.4\n..."  # Fake PDF content
        mime_type = "application/pdf"

        doc = await create_document(
            db_session, org_a.id, kb_a.id, filename, content, mime_type
        )

        assert doc.mime_type == "application/pdf"
        expected_path = tmp_path / str(org_a.id) / f"{doc.id}.pdf"
        assert expected_path.exists()

    async def test_create_document_unsupported_file_type_raises(
        self,
        db_session: AsyncSession,
        org_a: Organization,
        kb_a: KnowledgeBase,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test that uploading unsupported file type raises UnsupportedFileTypeError."""
        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)
        monkeypatch.setattr("app.knowledge.storage.get_settings", lambda: mock_settings)

        filename = "virus.exe"
        content = b"EXECUTABLE"
        mime_type = "application/x-msdownload"

        with pytest.raises(UnsupportedFileTypeError):
            await create_document(
                db_session, org_a.id, kb_a.id, filename, content, mime_type
            )

    async def test_create_document_kb_not_found_raises(
        self,
        db_session: AsyncSession,
        org_a: Organization,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test that uploading to nonexistent KB raises KnowledgeBaseNotFoundError."""
        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)
        monkeypatch.setattr("app.knowledge.storage.get_settings", lambda: mock_settings)

        fake_kb_id = uuid.uuid4()
        with pytest.raises(KnowledgeBaseNotFoundError):
            await create_document(
                db_session, org_a.id, fake_kb_id, "doc.txt", b"content", "text/plain"
            )

    async def test_create_document_kb_from_different_org_raises(
        self,
        db_session: AsyncSession,
        org_a: Organization,
        org_b: Organization,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test that uploading to KB of different org raises KnowledgeBaseNotFoundError."""
        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)
        monkeypatch.setattr("app.knowledge.storage.get_settings", lambda: mock_settings)

        kb_a = await _create_kb(db_session, org_a.id, "Docs")

        # Org B tries to upload to Org A's KB
        with pytest.raises(KnowledgeBaseNotFoundError):
            await create_document(
                db_session, org_b.id, kb_a.id, "doc.txt", b"content", "text/plain"
            )


class TestDocumentRead:
    """Tests for reading documents."""

    async def test_list_documents_same_kb(
        self,
        db_session: AsyncSession,
        org_a: Organization,
        kb_a: KnowledgeBase,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test that list_documents only returns docs from the specified KB."""
        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)
        monkeypatch.setattr("app.knowledge.storage.get_settings", lambda: mock_settings)

        kb_b = await _create_kb(db_session, org_a.id, "Other KB")

        doc_a1 = await create_document(
            db_session, org_a.id, kb_a.id, "doc1.txt", b"content1", "text/plain"
        )
        doc_a2 = await create_document(
            db_session, org_a.id, kb_a.id, "doc2.txt", b"content2", "text/plain"
        )
        doc_b = await create_document(
            db_session, org_a.id, kb_b.id, "doc3.txt", b"content3", "text/plain"
        )

        docs_a = await list_documents(db_session, org_a.id, kb_a.id)
        docs_b = await list_documents(db_session, org_a.id, kb_b.id)

        assert len(docs_a) == 2
        assert len(docs_b) == 1
        assert doc_a1 in docs_a
        assert doc_a2 in docs_a
        assert doc_b not in docs_a
        assert doc_b in docs_b

    async def test_get_document_org_scoped(
        self,
        db_session: AsyncSession,
        org_a: Organization,
        org_b: Organization,
        kb_a: KnowledgeBase,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test that get_document enforces org isolation."""
        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)
        monkeypatch.setattr("app.knowledge.storage.get_settings", lambda: mock_settings)

        doc = await create_document(
            db_session, org_a.id, kb_a.id, "doc.txt", b"content", "text/plain"
        )

        # Org A can get their own document
        retrieved = await get_document(db_session, org_a.id, doc.id)
        assert retrieved.id == doc.id

        # Org B cannot get Org A's document
        with pytest.raises(DocumentNotFoundError):
            await get_document(db_session, org_b.id, doc.id)

    async def test_list_documents_empty_for_different_org(
        self,
        db_session: AsyncSession,
        org_a: Organization,
        org_b: Organization,
        kb_a: KnowledgeBase,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test that list_documents returns empty for org without access to KB."""
        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)
        monkeypatch.setattr("app.knowledge.storage.get_settings", lambda: mock_settings)

        await create_document(
            db_session, org_a.id, kb_a.id, "doc.txt", b"content", "text/plain"
        )

        docs_b = await list_documents(db_session, org_b.id, kb_a.id)
        # Org B cannot see documents from org A's KB (org isolation)
        assert docs_b == []

        # Verify org B has no KBs either (org isolation)
        kbs_b = await list_knowledge_bases(db_session, org_b.id)
        assert len(kbs_b) == 0

    async def test_get_document_nonexistent(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that getting nonexistent document raises DocumentNotFoundError."""
        fake_id = uuid.uuid4()
        with pytest.raises(DocumentNotFoundError):
            await get_document(db_session, org_a.id, fake_id)


class TestDocumentDelete:
    """Tests for deleting documents."""

    async def test_delete_document_removes_file_and_row(
        self,
        db_session: AsyncSession,
        org_a: Organization,
        kb_a: KnowledgeBase,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test that delete_document removes both DB row and file on disk."""
        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)
        monkeypatch.setattr("app.knowledge.storage.get_settings", lambda: mock_settings)

        doc = await create_document(
            db_session, org_a.id, kb_a.id, "doc.txt", b"content", "text/plain"
        )
        doc_id = doc.id
        expected_path = tmp_path / str(org_a.id) / f"{doc_id}.txt"

        # Verify file exists
        assert expected_path.exists()

        # Delete document
        await delete_document(db_session, org_a.id, doc_id)

        # Verify file is deleted
        assert not expected_path.exists()

        # Verify DB row is deleted
        with pytest.raises(DocumentNotFoundError):
            await get_document(db_session, org_a.id, doc_id)

    async def test_delete_document_org_scoped(
        self,
        db_session: AsyncSession,
        org_a: Organization,
        org_b: Organization,
        kb_a: KnowledgeBase,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        """Test that delete_document enforces org isolation."""
        mock_settings = MagicMock()
        mock_settings.upload_dir = str(tmp_path)
        monkeypatch.setattr("app.knowledge.storage.get_settings", lambda: mock_settings)

        doc = await create_document(
            db_session, org_a.id, kb_a.id, "doc.txt", b"content", "text/plain"
        )

        # Org B cannot delete Org A's document
        with pytest.raises(DocumentNotFoundError):
            await delete_document(db_session, org_b.id, doc.id)

        # Document still exists for Org A
        retrieved = await get_document(db_session, org_a.id, doc.id)
        assert retrieved.id == doc.id

    async def test_delete_document_nonexistent(
        self, db_session: AsyncSession, org_a: Organization
    ) -> None:
        """Test that deleting nonexistent document raises DocumentNotFoundError."""
        fake_id = uuid.uuid4()
        with pytest.raises(DocumentNotFoundError):
            await delete_document(db_session, org_a.id, fake_id)
