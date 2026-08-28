# Progress

Living document tracking project status by milestone. Update in the same commit as significant work (add/update status row, move backlog items, add log entry).

## Milestone Overview

| Milestone | Goal | Status | ETA |
|---|---|---|---|
| **M0** | Tenancy & Identity: operator/tenant auth, org-scoped CRUD for agents/KB | ⚠️ CI green; awaiting live stack validation | 2026-08-28 |
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
| **Identity Endpoint** | GET /v2/me (returns operator \| tenant principal + org details) | ✅ Done | Both principal types; DB-backed tests now hit chatbot_test |
| **Cross-tenant Isolation** | Test suite (tests/isolation/) with access matrix guard | ✅ Done | 100% route coverage, auto-fail on new routes |
| **CI/CD** | GitHub Actions (backend pytest, FE build/lint, Keycloak smoke) | ✅ Green | Run #17 (0270eaf): all 3 jobs pass, 189 tests |
| **Frontend Login** | Keycloak OIDC PKCE flow (admin-ui client), port to /v2 endpoints | ✅ Done | Commit 90b923b: port admin-ui to v2 API, enable OIDC PKCE login |

**Test count**: 189 tests (from `uv run pytest -q --collect-only`)

**Definition of Done (from M0.md §0)**: 
- ✅ Operator tạo org → land in Postgres (Keycloak sync via admin CLI, not real-time)
- ⚠️ Tenant admin login qua Keycloak → GET /v2/me works under test; the live path is unproven (see below)
- ✅ CRUD agent/KB trong org → all endpoints org-scoped via OrgScopedRepo
- ✅ Test cách ly cross-tenant xanh → tests/isolation/ 100% route matrix, and the operator-endpoint cases now authenticate a real tenant instead of asserting against an unauthenticated request
- ✅ CI chạy trên PR → run #17 green (backend 189 passed, FE build/lint, Keycloak JWKS smoke)

**Verified**: 189 tests green in CI against real Postgres + pgvector; Keycloak realm imports and serves JWKS in the CI smoke job.

**NOT verified — `docker compose up` has never been run end to end by anyone.** This sandbox's egress policy refuses every container image pull (quay.io and Docker Hub's blob CDN both answer 403), so the compose path cannot be exercised here at all. Two blocking defects were found by reading rather than running, and both are fixed but unproven live:
- `seed.sh` logged to stdout while three functions returned ids on stdout, so every captured id was log text glued to the id; `set_user_password` then built a malformed URL, curl failed, and `set -euo pipefail` killed the seed at exit 3 — three lines into `main`. No password, no operator role, no tenant admin, no demo org. A one-shot service exiting nonzero is invisible to `docker compose up -d`.
- Nothing ever added the tenant admin to the Keycloak **Organization**, so its token would carry no `organization` claim and every `/v2` route would 403.

Outstanding, needs a machine that can pull images:
- `docker compose up` → `kc-seed` exits 0 and prints its summary
- Tenant token carries `organization: demo`; `GET /v2/me` returns 200
- Real Keycloak login through the admin UI (OIDC code flow + PKCE)
- Create agent/KB in the UI

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
| 2026-08-28 | M0 cleanup: Fix test fixtures (Document filename, identity org claim format), progress.md truthfulness update (commit 44846b2) |
| 2026-08-28 | M0-fix8: single `authenticated_principal` seam in identity/deps.py so role checks are testable; `_make_app` now overrides get_session. CI run #17 green, 189 passed (commit 0270eaf) |
| 2026-08-28 | M0-fix9: seed.sh logs to stderr (id capture was corrupt, seed died at exit 3), joins tenant admin to the Keycloak Organization, fails loudly instead of warning. Not verified live — image pulls blocked here (commit 0808578) |

