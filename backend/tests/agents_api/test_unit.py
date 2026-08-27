"""Unit tests for agents API: validation and basic endpoint behavior."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.agents_api.conftest import ORG_ID_1, ORG_ID_2


class TestAgentProviderValidation:
    """Test provider validation on create."""

    async def test_create_agent_with_invalid_provider_422(
        self, client_unit: AsyncClient
    ) -> None:
        """Reject unknown provider with 422."""
        resp = await client_unit.post(
            f"/v2/orgs/{ORG_ID_1}/agents",
            json={
                "name": "Bad Bot",
                "provider": "gpt4chan",
                "model_name": "x",
            },
        )
        assert resp.status_code == 422


class TestAgentOrgScoping:
    """Test that org-scoping is enforced at the API level."""

    async def test_unknown_org_404(self, client_unit: AsyncClient) -> None:
        """Request to unknown org returns 404."""
        import uuid
        unknown_org = uuid.uuid4()
        resp = await client_unit.get(
            f"/v2/orgs/{unknown_org}/agents"
        )
        assert resp.status_code == 404

    async def test_wrong_org_404(self, client_unit: AsyncClient) -> None:
        """Request from one principal to another org returns 404."""
        # ORG_ID_1 exists and is active
        # ORG_ID_2 also exists but the principal is only a member of ORG_ID_1
        # So accessing ORG_ID_2 should return 404 (indistinguishable from unknown)
        resp = await client_unit.get(f"/v2/orgs/{ORG_ID_2}/agents")
        assert resp.status_code == 404

    # Suspended-org handling lives in require_org_access and is covered by
    # tests/security/test_org_access.py::test_suspended_org_is_403.
