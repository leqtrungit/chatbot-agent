"""Route coverage audit for cross-tenant isolation (NFR-SEC1).

This test ensures that all org-scoped routes in the application are covered
by the isolation test matrix. When new org-scoped routes are added to the app,
this test will fail until they are added to COVERED_ROUTES in
test_cross_tenant_matrix.py.

This prevents accidental security regressions where a new route is added but
not tested for cross-tenant isolation.

The test runs without a database - it only inspects the app's route registry.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute, _IncludedRouter

from app.main import create_app
from tests.isolation.test_cross_tenant_matrix import COVERED_ROUTES


def extract_org_scoped_routes() -> set[tuple[str, str]]:
    """Extract all org-scoped routes from the app.

    Returns:
        Set of (method, path_template) tuples for routes with {org_id}.
        Examples:
            ("GET", "/v2/orgs/{org_id}/agents")
            ("POST", "/v2/orgs/{org_id}/agents")
            ("DELETE", "/v2/orgs/{org_id}/knowledge-bases/{kb_id}")
    """

    def traverse_routes(
        routes, prefix: str = ""
    ) -> set[tuple[str, str]]:
        """Recursively traverse app routes."""
        all_routes = set()
        for route in routes:
            if isinstance(route, APIRoute):
                path = prefix + route.path
                # Skip non-org-scoped routes
                if "{org_id}" not in path:
                    continue
                methods = route.methods or {"GET"}
                for method in methods:
                    all_routes.add((method, path))
            elif isinstance(route, _IncludedRouter):
                router_prefix = prefix + route.include_context.prefix
                all_routes.update(
                    traverse_routes(route.original_router.routes, router_prefix)
                )
        return all_routes

    app = create_app()
    return traverse_routes(app.routes)


class TestRouteIsolationCoverage:
    """Verify all org-scoped routes are in the isolation matrix."""

    def test_all_org_scoped_routes_are_covered(self) -> None:
        """All org-scoped routes must be covered by isolation tests.

        When this test fails, it means a new org-scoped route was added but not
        yet tested for cross-tenant isolation. Add it to COVERED_ROUTES in
        test_cross_tenant_matrix.py.
        """
        actual_routes = extract_org_scoped_routes()
        missing_routes = actual_routes - COVERED_ROUTES

        assert (
            not missing_routes
        ), (
            f"Route(s) not in isolation test coverage matrix:\n"
            + "\n".join(
                f"  ({method!r}, {path!r})"
                for method, path in sorted(missing_routes)
            )
            + "\n\nAdd these routes to COVERED_ROUTES in "
            + "tests/isolation/test_cross_tenant_matrix.py"
        )

    def test_covered_routes_actually_exist(self) -> None:
        """COVERED_ROUTES should not have stale entries.

        Warns if COVERED_ROUTES contains routes that no longer exist
        (helps keep test maintenance clean).
        """
        actual_routes = extract_org_scoped_routes()
        stale_routes = COVERED_ROUTES - actual_routes

        assert (
            not stale_routes
        ), (
            f"Routes in COVERED_ROUTES that no longer exist:\n"
            + "\n".join(
                f"  ({method!r}, {path!r})"
                for method, path in sorted(stale_routes)
            )
            + "\n\nRemove these from COVERED_ROUTES in "
            + "tests/isolation/test_cross_tenant_matrix.py"
        )

    def test_route_coverage_summary(self) -> None:
        """Print summary of route coverage (informational)."""
        actual_routes = extract_org_scoped_routes()
        print(f"\nOrg-scoped route coverage: {len(COVERED_ROUTES)}/{len(actual_routes)}")
        print(
            "Covered routes:\n"
            + "\n".join(
                f"  {method:6} {path}"
                for method, path in sorted(COVERED_ROUTES)
            )
        )
