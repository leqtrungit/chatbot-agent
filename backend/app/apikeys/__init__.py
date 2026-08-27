"""API keys module: org-scoped authentication credentials (FR-T4, NFR-SEC2).

This module provides:
- API key CRUD endpoints under `/v2/orgs/{org_id}/api-keys`
- `require_api_key` dependency for validating X-API-Key headers
- Service layer for hashing, creating, listing, and revoking keys

Keys are hashed at rest (SHA-256) and revocation takes effect ≤60s via cache TTL.
"""
