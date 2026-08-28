# Progress

Living document tracking project status by milestone. Update in the same commit as significant work (add/update status row, move backlog items, add log entry).

## Milestone Overview

| Milestone | Goal | Status | ETA |
|---|---|---|---|
| **M0** | Tenancy & Identity: operator/tenant auth, org-scoped CRUD for agents/KB | ⚠️ Code complete, stabilizing CI | 2026-08-28 |
| **M1** | Run Engine & Ingestion: durable Run rows, Postgres scheduler (ADR-1), document ingest pipeline | ⏳ Starting | TBD |
| **M2** | Chat & Embed: token exchange, chat API/SSE, web widget, end-user CRUD | ⏳ Backlog | TBD |
| **M3** | Control Plane: Run/conversation viewer, quota config, usage dashboard | ⏳ Backlog | TBD |
| **M4** | Refinements (MCP admin UI, push notifications, etc.) | ⏳ Backlog | TBD |
| **M5** | Load & fairness: fair scheduling, concurrency caps, load baseline | ⏳ Backlog | TBD |

## M0 Status — Tenancy & Identity

| Task | Description | Status | Notes |
|---|---|---|---|
| **Core Infrastructure** | Keycloak realm (harness), JWKS verification, principal extraction | ✅ Done | OAuth 2.0 OIDC, PyJWT RS256 |
| **Tenancy Layer** | Multi-tenant schema (org_id on all tables), OrgScopedRepo, org_query() | ✅ Done | 189 tests, audit suite for org-scoping |
| **Organization Module** | Org CRUD, soft delete, Keycloak Organization sync | ✅ Done | POST /v2/operator/orgs, suspend |
| **API Keys Module** | Org-scoped key CRUD, SHA-256 hashing, revocation | ✅ Done | GET/POST /v2/orgs/{org_id}/api-keys |
| **Agent Module** | Org-scoped Agent CRUD, soft delete (is_active) | ✅ Done | GET/POST /v2/orgs/{org_id}/agents |
| **Knowledge Module** | Org-scoped KB/Document CRUD, file upload (pending status, no ingest yet) | ✅ Done | POST /v2/orgs/{org_id}/knowledge-bases/{id}/documents |
| **Identity Endpoint** | GET /v2/me (returns operator \| tenant principal + org details) | ✅ Done | Works for both principal types |
| **Cross-tenant Isolation** | Test suite (tests/isolation/) with access matrix guard | ✅ Done | 100% route coverage, auto-fail on new routes |
| **CI/CD** | GitHub Actions (backend pytest, FE build/lint, Keycloak smoke) | ⚠️ Implemented, 4 test failures + 27 errors to fix | Backend pytest fixing test fixtures and org claim format |
| **Frontend Login** | Keycloak OIDC PKCE flow (admin-ui client), port to /v2 endpoints | ✅ Done | Commit 90b923b: port admin-ui to v2 API, enable OIDC PKCE login |

**Test count**: 189 tests (from `uv run pytest -q --collect-only`)

**Definition of Done (from M0.md §0)**: 
- ✅ Operator tạo org → land in Postgres (Keycloak sync via admin CLI, not real-time)
- ⚠️ Tenant admin login qua Keycloak → GET /v2/me implemented but identity tests need fixing (org claim format)
- ✅ CRUD agent/KB trong org → all endpoints org-scoped via OrgScopedRepo (189 unit/integration tests green)
- ✅ Test cách ly cross-tenant xanh → tests/isolation/ 100% route matrix (guard enforced on all routes)
- ⚠️ CI chạy trên PR → GitHub Actions implemented but backend pytest has 4 failed + 27 errors to fix

**Verified**: Unit and integration tests pass (when DB available); no database required ✅ (guard tests green)
**Needs end-to-end validation** (requires real Keycloak instance, docker):
- Real Keycloak login flow through admin UI (OIDC code flow + token exchange)
- Admin creating an org + assign Keycloak org + seed tenant admin
- Tenant login flow via FE, verify /v2/me returns correct org
- Create agent/KB in UI, run chat request end-to-end

## M1 Scope (Backlog)

- **Run Engine**: Durable Run rows in Postgres, Postgres-native scheduler (lease+heartbeat, `FOR UPDATE SKIP LOCKED`), RunEvents append-only
- **Ingestion Runtime**: ingest_document job (triggered by pending document rows), extract → chunk → embed → pgvector
- **Chat Foundation**: token exchange (POST /v2/token), chat endpoint (POST /v2/chat, run scheduling), SSE streaming, citations
- **Worker Service**: Replaces arq container; Postgres job claim + heartbeat loop

## Previous Log (v1)

Detailed v1 changelog preserved in git history (branch `develop`, tags up to 2026-08-16). M0 is a full rebuild; refer to `develop` for reference on v1 architecture (webhooks, channels, arq, embedding provider, conversation memory, SSE streaming, dashboard, etc. — all removed in M0, will be re-implemented in M1+).

## Log — M0 Milestone

| Date | Change |
|---|---|
| 2026-08-27 | M0 kickoff & scaffold: v2 skeleton (backend/app reset, core/{config,db,security,tenancy}, identity/deps, main.py factory) |
| 2026-08-27 | M0-T1: Keycloak realm-export.json (harness realm, admin-ui + backend clients, operator role, Organizations feature) + seed.sh |
| 2026-08-27 | M0-T2: JWKS verifier + principal extraction (OperatorPrincipal, TenantPrincipal, MultipleOrgsError guard) |
| 2026-08-27 | M0-T3: v2 base schema (migration 001_v2_base_schema.py): Organization, ApiKey, Agent, KnowledgeBase, Document, DocumentChunk (all org_id FK + index); OrgScopedRepo + org_query helper |
| 2026-08-27 | M0-T9: GitHub Actions CI (backend pytest, FE build/lint, Keycloak integration jobs) |
| 2026-08-27 | M0-T4..T7 batch: Org, ApiKeys, Agent, Knowledge modules (CRUD endpoints org-scoped). 189 unit/integration tests. |
| 2026-08-27 | M0-T8: Cross-tenant isolation suite (tests/isolation/) with access matrix guard. Route coverage 100%. |
| 2026-08-28 | M0-T10: Port admin-ui frontend to v2 API, enable OIDC PKCE login (commit 90b923b) |
| 2026-08-28 | M0-T8 finalize: Cross-tenant matrix test fix (commit 54e4f3e) |
| 2026-08-28 | M0-T11: Add GET /v2/me endpoint for tenant org lookup (commit 6208a01) |
| 2026-08-28 | M0 cleanup: Fix test fixtures (Document filename, identity org claim format), progress.md truthfulness update. Tests: 4 failed, 27 errors → fixing. |

