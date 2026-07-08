from __future__ import annotations

import io

import pytest


@pytest.fixture(autouse=True)
def stub_enqueue(monkeypatch):
    calls: list[str] = []

    async def _fake_enqueue(document_id) -> None:
        calls.append(str(document_id))

    monkeypatch.setattr(
        "app.modules.document.service.enqueue_ingest_job", _fake_enqueue
    )
    return calls


async def _create_domain(client, admin_auth_header, name="Docs Domain"):
    resp = await client.post("/api/domains", json={"name": name}, headers=admin_auth_header)
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_upload_document_requires_auth(client):
    domain_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(
        f"/api/domains/{domain_id}/documents",
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 401


async def test_upload_document_success(client, admin_auth_header, stub_enqueue):
    domain_id = await _create_domain(client, admin_auth_header)

    resp = await client.post(
        f"/api/domains/{domain_id}/documents",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        headers=admin_auth_header,
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["filename"] == "notes.txt"
    assert body["domain_id"] == domain_id
    assert len(stub_enqueue) == 1

    # file persisted to disk
    from app.modules.document.service import file_path_for
    import uuid

    path = file_path_for(uuid.UUID(body["id"]), ".txt")
    assert path.exists()
    assert path.read_bytes() == b"hello world"
    path.unlink()


async def test_upload_unsupported_type_returns_415(client, admin_auth_header):
    domain_id = await _create_domain(client, admin_auth_header)

    resp = await client.post(
        f"/api/domains/{domain_id}/documents",
        files={"file": ("virus.exe", b"MZ", "application/octet-stream")},
        headers=admin_auth_header,
    )
    assert resp.status_code == 415


async def test_upload_unknown_domain_returns_404(client, admin_auth_header):
    resp = await client.post(
        "/api/domains/00000000-0000-0000-0000-000000000000/documents",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=admin_auth_header,
    )
    assert resp.status_code == 404


async def test_list_documents(client, admin_auth_header):
    domain_id = await _create_domain(client, admin_auth_header)
    await client.post(
        f"/api/domains/{domain_id}/documents",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=admin_auth_header,
    )

    resp = await client.get(f"/api/domains/{domain_id}/documents", headers=admin_auth_header)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["filename"] == "a.txt"


async def test_get_and_delete_document(client, admin_auth_header):
    domain_id = await _create_domain(client, admin_auth_header)
    create = await client.post(
        f"/api/domains/{domain_id}/documents",
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=admin_auth_header,
    )
    doc_id = create.json()["id"]

    resp = await client.get(f"/api/documents/{doc_id}", headers=admin_auth_header)
    assert resp.status_code == 200

    resp = await client.delete(f"/api/documents/{doc_id}", headers=admin_auth_header)
    assert resp.status_code == 204

    resp = await client.get(f"/api/documents/{doc_id}", headers=admin_auth_header)
    assert resp.status_code == 404


async def test_get_document_not_found(client, admin_auth_header):
    resp = await client.get(
        "/api/documents/00000000-0000-0000-0000-000000000000", headers=admin_auth_header
    )
    assert resp.status_code == 404
