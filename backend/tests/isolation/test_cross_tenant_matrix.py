"""Cross-tenant isolation matrix test (NFR-SEC1).

This test embodies NFR-SEC1 from the specification: organizations must be
completely isolated from each other. A tenant admin of organization A should
never be able to read, write, update, or delete any resources belonging to
organization B.

Key design: When a cross-tenant access attempt is rejected, we return 404
(indistinguishable from "resource does not exist") rather than 403, to avoid
leaking information about the existence of other organizations.

The test creates two real organizations with data (agents, knowledge bases,
documents, API keys) and verifies that:

1. Org A admin cannot LIST, GET, PUT, POST, DELETE any Org B resources
2. After denied operations, Org B data remains unchanged (no side effects)
3. Suspended organizations return 403 to their own members (different from cross-tenant 404)
4. Operator endpoints are forbidden to tenant admins (not their role)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.isolation.conftest import (
    ORG_A_ID,
    ORG_A_SLUG,
    ORG_B_ID,
    ORG_B_SLUG,
)
from app.agents.models import Agent
from app.knowledge.models import KnowledgeBase, Document


# Routes covered by this matrix (used for consistency check in test_route_coverage.py)
COVERED_ROUTES = {
    # Tenant-scoped agents endpoints
    ("GET", "/v2/orgs/{org_id}/agents"),
    ("POST", "/v2/orgs/{org_id}/agents"),
    ("GET", "/v2/orgs/{org_id}/agents/{agent_id}"),
    ("PUT", "/v2/orgs/{org_id}/agents/{agent_id}"),
    ("POST", "/v2/orgs/{org_id}/agents/{agent_id}/deactivate"),
    ("PUT", "/v2/orgs/{org_id}/agents/{agent_id}/knowledge-bases"),
    # Tenant-scoped API keys endpoints
    ("GET", "/v2/orgs/{org_id}/api-keys"),
    ("POST", "/v2/orgs/{org_id}/api-keys"),
    ("POST", "/v2/orgs/{org_id}/api-keys/{key_id}/revoke"),
    # Tenant-scoped knowledge bases endpoints
    ("GET", "/v2/orgs/{org_id}/knowledge-bases"),
    ("POST", "/v2/orgs/{org_id}/knowledge-bases"),
    ("GET", "/v2/orgs/{org_id}/knowledge-bases/{kb_id}"),
    ("PUT", "/v2/orgs/{org_id}/knowledge-bases/{kb_id}"),
    ("DELETE", "/v2/orgs/{org_id}/knowledge-bases/{kb_id}"),
    ("GET", "/v2/orgs/{org_id}/knowledge-bases/{kb_id}/documents"),
    ("POST", "/v2/orgs/{org_id}/knowledge-bases/{kb_id}/documents"),
    ("GET", "/v2/orgs/{org_id}/knowledge-bases/{kb_id}/documents/{doc_id}"),
    ("DELETE", "/v2/orgs/{org_id}/knowledge-bases/{kb_id}/documents/{doc_id}"),
    # Operator-only endpoints (tested for 403 to tenant admins)
    ("POST", "/v2/operator/orgs/{org_id}/suspend"),
    ("POST", "/v2/operator/orgs/{org_id}/reactivate"),
}


class TestCrossTenantAgentIsolation:
    """Agent endpoints must be isolated by org."""

    @pytest.mark.asyncio
    async def test_org_a_cannot_list_org_b_agents(
        self, client_org_a: AsyncClient
    ) -> None:
        """Org A admin cannot list agents in org B (returns 404)."""
        resp = await client_org_a.get(f"/v2/orgs/{ORG_B_ID}/agents")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_create_agent_in_org_b(
        self, client_org_a: AsyncClient
    ) -> None:
        """Org A admin cannot create agent in org B (returns 404)."""
        resp = await client_org_a.post(
            f"/v2/orgs/{ORG_B_ID}/agents",
            json={
                "name": "Malicious Agent",
                "provider": "ollama",
                "model_name": "qwen",
            },
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_get_org_b_agent(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot get a specific agent from org B (returns 404)."""
        agent_b_id = isolation_db_session.agent_b_id
        resp = await client_org_a.get(f"/v2/orgs/{ORG_B_ID}/agents/{agent_b_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_update_org_b_agent(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot update an agent in org B (returns 404)."""
        agent_b_id = isolation_db_session.agent_b_id
        resp = await client_org_a.put(
            f"/v2/orgs/{ORG_B_ID}/agents/{agent_b_id}",
            json={"name": "Hacked Agent"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_deactivate_org_b_agent(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot deactivate agent in org B (returns 404)."""
        agent_b_id = isolation_db_session.agent_b_id
        resp = await client_org_a.post(
            f"/v2/orgs/{ORG_B_ID}/agents/{agent_b_id}/deactivate"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_set_org_b_agent_knowledge_bases(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot set knowledge bases for org B agent (returns 404)."""
        agent_b_id = isolation_db_session.agent_b_id
        resp = await client_org_a.put(
            f"/v2/orgs/{ORG_B_ID}/agents/{agent_b_id}/knowledge-bases",
            json={"knowledge_base_ids": []},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_b_agent_data_unchanged_after_failed_update(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """After org A's failed agent update, org B agent is unchanged."""
        agent_b_id = isolation_db_session.agent_b_id
        original_agent = await isolation_db_session.get(Agent, agent_b_id)
        original_name = original_agent.name

        # Attempt update from wrong org
        resp = await client_org_a.put(
            f"/v2/orgs/{ORG_B_ID}/agents/{agent_b_id}",
            json={"name": "Hacked"},
        )
        assert resp.status_code == 404

        # Verify no change in DB
        # Refresh to ensure we see latest state
        updated_agent = await isolation_db_session.get(Agent, agent_b_id)
        assert updated_agent.name == original_name


class TestCrossTenantApiKeyIsolation:
    """API key endpoints must be isolated by org."""

    @pytest.mark.asyncio
    async def test_org_a_cannot_list_org_b_keys(
        self, client_org_a: AsyncClient
    ) -> None:
        """Org A admin cannot list API keys in org B (returns 404)."""
        resp = await client_org_a.get(f"/v2/orgs/{ORG_B_ID}/api-keys")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_create_key_in_org_b(
        self, client_org_a: AsyncClient
    ) -> None:
        """Org A admin cannot create API key in org B (returns 404)."""
        resp = await client_org_a.post(
            f"/v2/orgs/{ORG_B_ID}/api-keys",
            json={"name": "Malicious Key"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_revoke_org_b_key(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot revoke API key in org B (returns 404)."""
        key_b_id = isolation_db_session.key_b_id
        resp = await client_org_a.post(
            f"/v2/orgs/{ORG_B_ID}/api-keys/{key_b_id}/revoke"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_b_key_not_revoked_after_failed_revoke(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """After org A's failed key revoke, org B key is still active."""
        from app.apikeys.models import ApiKey

        key_b_id = isolation_db_session.key_b_id
        original_key = await isolation_db_session.get(ApiKey, key_b_id)
        assert original_key.revoked_at is None

        # Attempt revoke from wrong org
        resp = await client_org_a.post(
            f"/v2/orgs/{ORG_B_ID}/api-keys/{key_b_id}/revoke"
        )
        assert resp.status_code == 404

        # Verify key is still active
        updated_key = await isolation_db_session.get(ApiKey, key_b_id)
        assert updated_key.revoked_at is None


class TestCrossTenantKnowledgeBaseIsolation:
    """Knowledge base endpoints must be isolated by org."""

    @pytest.mark.asyncio
    async def test_org_a_cannot_list_org_b_kbs(
        self, client_org_a: AsyncClient
    ) -> None:
        """Org A admin cannot list knowledge bases in org B (returns 404)."""
        resp = await client_org_a.get(f"/v2/orgs/{ORG_B_ID}/knowledge-bases")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_create_kb_in_org_b(
        self, client_org_a: AsyncClient
    ) -> None:
        """Org A admin cannot create knowledge base in org B (returns 404)."""
        resp = await client_org_a.post(
            f"/v2/orgs/{ORG_B_ID}/knowledge-bases",
            json={"name": "Malicious KB", "slug": "malicious-kb"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_get_org_b_kb(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot get knowledge base from org B (returns 404)."""
        kb_b_id = isolation_db_session.kb_b_id
        resp = await client_org_a.get(
            f"/v2/orgs/{ORG_B_ID}/knowledge-bases/{kb_b_id}"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_update_org_b_kb(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot update knowledge base in org B (returns 404)."""
        kb_b_id = isolation_db_session.kb_b_id
        resp = await client_org_a.put(
            f"/v2/orgs/{ORG_B_ID}/knowledge-bases/{kb_b_id}",
            json={"name": "Hacked KB"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_delete_org_b_kb(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot delete knowledge base in org B (returns 404)."""
        kb_b_id = isolation_db_session.kb_b_id
        resp = await client_org_a.delete(
            f"/v2/orgs/{ORG_B_ID}/knowledge-bases/{kb_b_id}"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_b_kb_unchanged_after_failed_delete(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """After org A's failed KB delete, org B KB still exists."""
        kb_b_id = isolation_db_session.kb_b_id
        original_kb = await isolation_db_session.get(KnowledgeBase, kb_b_id)
        assert original_kb is not None

        # Attempt delete from wrong org
        resp = await client_org_a.delete(
            f"/v2/orgs/{ORG_B_ID}/knowledge-bases/{kb_b_id}"
        )
        assert resp.status_code == 404

        # Verify KB still exists
        kb_still_exists = await isolation_db_session.get(KnowledgeBase, kb_b_id)
        assert kb_still_exists is not None


class TestCrossTenantDocumentIsolation:
    """Document endpoints must be isolated by org."""

    @pytest.mark.asyncio
    async def test_org_a_cannot_list_org_b_documents(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot list documents in org B KB (returns 404)."""
        kb_b_id = isolation_db_session.kb_b_id
        resp = await client_org_a.get(
            f"/v2/orgs/{ORG_B_ID}/knowledge-bases/{kb_b_id}/documents"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_upload_doc_in_org_b_kb(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot upload document to org B KB (returns 404)."""
        kb_b_id = isolation_db_session.kb_b_id
        resp = await client_org_a.post(
            f"/v2/orgs/{ORG_B_ID}/knowledge-bases/{kb_b_id}/documents",
            files={"file": ("test.txt", b"malicious content", "text/plain")},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_get_org_b_document(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot get document from org B (returns 404)."""
        kb_b_id = isolation_db_session.kb_b_id
        doc_b_id = isolation_db_session.doc_b_id
        resp = await client_org_a.get(
            f"/v2/orgs/{ORG_B_ID}/knowledge-bases/{kb_b_id}/documents/{doc_b_id}"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_a_cannot_delete_org_b_document(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """Org A admin cannot delete document in org B (returns 404)."""
        kb_b_id = isolation_db_session.kb_b_id
        doc_b_id = isolation_db_session.doc_b_id
        resp = await client_org_a.delete(
            f"/v2/orgs/{ORG_B_ID}/knowledge-bases/{kb_b_id}/documents/{doc_b_id}"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_org_b_document_unchanged_after_failed_delete(
        self, client_org_a: AsyncClient, isolation_db_session: AsyncSession
    ) -> None:
        """After org A's failed document delete, org B document still exists."""
        kb_b_id = isolation_db_session.kb_b_id
        doc_b_id = isolation_db_session.doc_b_id
        original_doc = await isolation_db_session.get(Document, doc_b_id)
        assert original_doc is not None

        # Attempt delete from wrong org
        resp = await client_org_a.delete(
            f"/v2/orgs/{ORG_B_ID}/knowledge-bases/{kb_b_id}/documents/{doc_b_id}"
        )
        assert resp.status_code == 404

        # Verify document still exists
        doc_still_exists = await isolation_db_session.get(Document, doc_b_id)
        assert doc_still_exists is not None


class TestOperatorEndpointAccessControl:
    """Operator endpoints must reject tenant admins."""

    @pytest.mark.asyncio
    async def test_tenant_admin_cannot_create_org(
        self, client_org_a: AsyncClient
    ) -> None:
        """Tenant admin cannot create organization (returns 403)."""
        resp = await client_org_a.post(
            "/v2/operator/orgs",
            json={"name": "Evil Org", "slug": "evil-org"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_tenant_admin_cannot_list_all_orgs(
        self, client_org_a: AsyncClient
    ) -> None:
        """Tenant admin cannot list all organizations (returns 403)."""
        resp = await client_org_a.get("/v2/operator/orgs")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_tenant_admin_cannot_suspend_org(
        self, client_org_a: AsyncClient
    ) -> None:
        """Tenant admin cannot suspend organization (returns 403)."""
        # Even their own org
        resp = await client_org_a.post(f"/v2/operator/orgs/{ORG_A_ID}/suspend")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_tenant_admin_cannot_reactivate_org(
        self, client_org_a: AsyncClient
    ) -> None:
        """Tenant admin cannot reactivate organization (returns 403)."""
        resp = await client_org_a.post(f"/v2/operator/orgs/{ORG_A_ID}/reactivate")
        assert resp.status_code == 403


class TestSuspendedOrgBehavior:
    """Suspended organizations return 403 to their own members."""

    @pytest.mark.asyncio
    async def test_suspended_org_member_gets_403(
        self, isolation_db_session: AsyncSession, org_a_principal
    ) -> None:
        """Org member cannot access suspended org resources (returns 403)."""
        from app.core.db import get_session
        from app.identity.deps import require_org_member
        from app.main import create_app
        from httpx import ASGITransport, AsyncClient

        # Suspend org A
        from app.orgs.models import Organization

        org_a = await isolation_db_session.get(Organization, ORG_A_ID)
        org_a.status = "suspended"
        await isolation_db_session.commit()

        # Create app and try to access own org
        app = create_app()
        app.dependency_overrides[get_session] = lambda: isolation_db_session
        app.dependency_overrides[require_org_member] = lambda: org_a_principal

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/v2/orgs/{ORG_A_ID}/agents")
            assert resp.status_code == 403
