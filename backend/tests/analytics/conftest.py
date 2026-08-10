"""Fixtures specific to the app.modules.analytics test suite."""

from __future__ import annotations

# Reuse the real-Postgres test database fixtures from tests/modules/conftest.py
# (test_engine, session_maker, db_session, client, admin_auth_header) instead
# of duplicating DB setup.
from tests.modules.conftest import (  # noqa: F401
    admin_auth_header,
    client,
    db_session,
    session_maker,
    test_engine,
)
