"""File storage for documents (tenant-isolated)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.core.config import get_settings


def get_upload_dir(org_id: uuid.UUID) -> Path:
    """Get the upload directory for an org.

    Files are stored under backend/data/uploads/{org_id}/ for tenant isolation.

    Args:
        org_id: Organization UUID.

    Returns:
        Path to the org's uploads directory.
    """
    settings = get_settings()
    path = Path(settings.upload_dir) / str(org_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def storage_path_for(org_id: uuid.UUID, document_id: uuid.UUID, extension: str) -> Path:
    """Get the storage path for a document file.

    Args:
        org_id: Organization UUID.
        document_id: Document UUID.
        extension: File extension (e.g., ".pdf", ".txt").

    Returns:
        Full path to where the file should be stored.
    """
    return get_upload_dir(org_id) / f"{document_id}{extension}"


ALLOWED_MIME_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/markdown": ".md",
}

ALLOWED_EXTENSIONS: dict[str, str] = {
    v: k for k, v in ALLOWED_MIME_TYPES.items()
}


class UnsupportedFileTypeError(Exception):
    """Raised when file type is not supported."""

    pass


def validate_file_type(filename: str, mime_type: str) -> str:
    """Validate file type and return canonical mime type.

    Args:
        filename: Original filename from upload.
        mime_type: Declared MIME type from HTTP Content-Type.

    Returns:
        Canonical MIME type.

    Raises:
        UnsupportedFileTypeError: If file type is not supported.
    """
    # Check by MIME type first
    if mime_type in ALLOWED_MIME_TYPES:
        return mime_type

    # Fall back to checking file extension
    extension = os.path.splitext(filename)[1].lower()
    if extension in ALLOWED_EXTENSIONS:
        return ALLOWED_EXTENSIONS[extension]

    raise UnsupportedFileTypeError(
        f"Unsupported file type: {mime_type} (extension: {extension})"
    )
