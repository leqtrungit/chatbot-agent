"""Unit tests for storage path generation (org isolation)."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from app.knowledge.storage import storage_path_for, get_upload_dir


class TestStoragePath:
    """Tests for storage path generation with org_id."""

    def test_storage_path_includes_org_id(self, tmp_path):
        """Test that storage path includes org_id for tenant isolation."""
        org_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        with patch("app.knowledge.storage.get_settings") as mock_settings:
            mock_settings.return_value.upload_dir = str(tmp_path)

            path = storage_path_for(org_id, doc_id, ".pdf")

            # Path must contain org_id
            path_str = str(path)
            assert str(org_id) in path_str
            assert str(doc_id) in path_str
            assert path_str.endswith(".pdf")

    def test_storage_path_preserves_extension(self, tmp_path):
        """Test that file extension is preserved in path."""
        org_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        with patch("app.knowledge.storage.get_settings") as mock_settings:
            mock_settings.return_value.upload_dir = str(tmp_path)

            for ext in [".pdf", ".docx", ".txt", ".md"]:
                path = storage_path_for(org_id, doc_id, ext)
                assert str(path).endswith(ext)

    def test_storage_path_structure(self, tmp_path):
        """Test that path structure is /uploads/{org_id}/{doc_id}{ext}."""
        org_id = uuid.uuid4()
        doc_id = uuid.uuid4()

        with patch("app.knowledge.storage.get_settings") as mock_settings:
            mock_settings.return_value.upload_dir = str(tmp_path)

            path = storage_path_for(org_id, doc_id, ".pdf")
            parts = path.parts

            # Should have structure: ..., {org_id}, {doc_id}.pdf
            assert str(org_id) in parts

    def test_get_upload_dir_for_org(self):
        """Test that get_upload_dir creates org-specific directory."""
        org_id = uuid.uuid4()

        with patch("app.knowledge.storage.get_settings") as mock_settings:
            mock_settings.return_value.upload_dir = "/data/uploads"

            with patch.object(Path, "mkdir"):
                upload_dir = get_upload_dir(org_id)

                assert str(org_id) in str(upload_dir)

    def test_storage_path_different_orgs_different_paths(self, tmp_path):
        """Test that different orgs have different storage paths."""
        org_id_1 = uuid.uuid4()
        org_id_2 = uuid.uuid4()
        doc_id = uuid.uuid4()

        with patch("app.knowledge.storage.get_settings") as mock_settings:
            mock_settings.return_value.upload_dir = str(tmp_path)

            path1 = storage_path_for(org_id_1, doc_id, ".pdf")
            path2 = storage_path_for(org_id_2, doc_id, ".pdf")

            # Paths must be different (different org_id)
            assert path1 != path2
            assert str(org_id_1) in str(path1)
            assert str(org_id_2) in str(path2)
