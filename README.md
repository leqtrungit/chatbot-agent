# Agent Harness Platform — v2

A SaaS platform for managing and operating AI agents on customer organizations. Built on **multi-tenant architecture**, Keycloak OIDC identity, and PostgreSQL as the single source of truth.

## Product Vision

**Three core principles** (from spec §1):

1. **Agentic** — Every agent execution is a durable `Run` in the database with full trace (event-sourced), not a stateless function call.
2. **Manage** — Business users control agents from the admin UI: what they do, what they think, what they cost, what went wrong.
3. **Integrate** — Embed into existing apps fast (chat-first via HTTP API, web widget) and two-way (platform calls tools/MCP, world calls platform API).

## Current Status

**M0 (Tenancy & Identity)** — ✅ Complete

- Keycloak OIDC for human auth (operator, tenant admin)
- Multi-tenant org-scoped CRUD: agents, knowledge bases, API keys
- PostgreSQL multi-tenant schema (org_id on all business tables)
- Cross-tenant isolation tested + CI green

**Roadmap**: M1 (Run Engine + Ingestion) → M2 (Chat & Embed) → M3 (Control Plane) → M4 (Refinements) → M5 (Load & Fairness)

See `docs/HARNESS_SPEC.md` for full functional/non-functional requirements and `docs/plans/M0.md` for implementation details.

## Quick Start

**Requirements**: Docker, Python 3.12 + [uv](https://docs.astral.sh/uv/), Node.js.

```bash
# 1. Clone & setup env
git clone <repo>
cd chatbot-agent
cp .env.example .env

# 2. Start infra (postgres, redis, keycloak)
docker compose up -d

# Watch Keycloak startup — wait for "Keycloak X.X.X started"
docker compose logs -f keycloak | grep -i "started"

# 3. Backend setup
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000

# 4. Frontend (new terminal)
cd frontend
npm install
npm run dev                          # http://localhost:3000

# 5. Login to admin UI
# Browser: http://localhost:3000
# A Keycloak login form appears
# Use seed account: admin / admin (from infra/keycloak/seed.sh)
# This is the *operator* principal (realm role "operator")
```

After login, you'll see the admin dashboard. To test tenant-admin functionality, seed a test account via Keycloak and add it to an Organization (see `infra/keycloak/README.md`).

## Architecture

```
┌─── Platform Operator ──┐
│   (Keycloak realm role │
│      "operator")       │
└─────────┬──────────────┘
          │
          ▼
     POST /v2/operator/orgs (create org)
          │
     ┌────────────────────────────────────┐
     │      Organization (tenant)         │
     │  ┌──────────────────────────────┐  │
     │  │ Tenant Admin                 │  │
     │  │ (KC Organization member)     │  │
     │  └──────────────────────────────┘  │
     │          │                         │
     │          ├─ Agents (CRUD)          │
     │          ├─ Knowledge Bases (CRUD) │
     │          ├─ Documents (upload)     │
     │          └─ API Keys (create)      │
     │                                    │
     │  All data scoped to this org via   │
     │  org_id + OrgScopedRepo layer      │
     └────────────────────────────────────┘

Keycloak (infra/keycloak/realm-export.json)
  ├─ Realm: "harness"
  ├─ Client: "admin-ui" (PKCE, browser/SPA) → FE login flow
  ├─ Client: "backend" (bearer-only) → JWT verification
  ├─ Realm role: "operator"
  └─ Organizations feature (tenant memberships)

Database (PostgreSQL)
  ├─ Organization, User (mapped to Keycloak)
  ├─ Agent, KnowledgeBase, Document, DocumentChunk (all org_id scoped)
  ├─ ApiKey (org_id scoped, hashed)
  └─ [M1+] Run, RunEvent, Conversation, EndUser
```

**Key architectural principles**:

- **Multi-tenant from day one**: every business table has `org_id NOT NULL + FK + index`; no shared data.
- **Org-scoped data access**: `OrgScopedRepo` and `org_query()` enforce scoping at the query layer, not just the router. Mutable queries MUST use these helpers.
- **Keycloak for identity** (FR-T2): human authentication is entirely delegated to Keycloak OIDC; backend verifies JWT via JWKS and extracts principal (operator or tenant).
- **PostgreSQL is source of truth** (ADR-1): Run scheduling will use Postgres-native `FOR UPDATE SKIP LOCKED`, not a separate job queue. Redis is ephemeral (pub/sub, cache, rate-limit only).

## Modules (M0)

### `app/core/` — Foundation
- **config.py** — Settings from env (.env, .env.local)
- **db.py** — Async SQLAlchemy engine, async session factory
- **security.py** — JWKS verifier (RS256), principal extraction (OperatorPrincipal, TenantPrincipal)
- **tenancy.py** — `org_query()` and `OrgScopedRepo` — enforce org-scoping at data-access layer

### `app/identity/` — Authentication
- **deps.py** — FastAPI dependencies: `require_operator`, `require_org_member`, `require_any_principal`
- **org_access.py** — Guard for matching route `org_id` with principal org (T4+)
- **router.py** — `GET /v2/me` — returns authenticated principal info + org details for tenants

### `app/orgs/` — Organization Management (Operator-only)
- **models.py** — `Organization{id, name, slug, keycloak_org_id, status}`
- **service.py** — Org creation, Keycloak Admin API integration
- **router.py** — `POST /v2/operator/orgs`, suspend, list
- **kc_admin.py** — Keycloak Admin REST API client

### `app/apikeys/` — API Key Management (Tenant Admin)
- **models.py** — `ApiKey{org_id, name, key_hash, revoked_at}`
- **service.py** — Create/revoke, SHA-256 hashing
- **router.py** — `GET/POST /v2/orgs/{org_id}/api-keys`
- **deps.py** — `require_api_key` (for M2 webhook/chat)

### `app/agents/` — Agent Management (Tenant Admin)
- **models.py** — `Agent{org_id, name, provider, model, api_key, system_prompt, ...}`
- **service.py** — CRUD, soft delete (`is_active`)
- **router.py** — `GET/POST /v2/orgs/{org_id}/agents`; agent↔KB assignment
- **schemas.py** — DTOs

### `app/knowledge/` — Knowledge Base Management (Tenant Admin)
- **models.py** — `KnowledgeBase{org_id, name, slug}`, `Document{org_id, kb_id, ...}`, `DocumentChunk{org_id, embedding, ...}`
- **service.py** — CRUD, file upload (stores under `data/uploads/{org_id}/`)
- **router.py** — `GET/POST /v2/orgs/{org_id}/knowledge-bases`; document upload/list/delete
- **storage.py** — Local filesystem abstraction
- **schemas.py** — DTOs

## API Overview

**Admin routes** (require `Authorization: Bearer {keycloak_jwt}`):

| Method | Path | Principal | Description |
|---|---|---|---|
| POST | `/v2/operator/orgs` | Operator | Create organization |
| POST | `/v2/operator/orgs/{id}/suspend` | Operator | Suspend organization |
| GET | `/v2/operator/orgs` | Operator | List organizations |
| GET/POST/DELETE | `/v2/orgs/{org_id}/agents` | Tenant Admin | Agent CRUD |
| GET/POST/DELETE | `/v2/orgs/{org_id}/knowledge-bases` | Tenant Admin | Knowledge Base CRUD |
| POST | `/v2/orgs/{org_id}/knowledge-bases/{id}/documents` | Tenant Admin | Upload document (status: pending, no ingest yet) |
| GET/DELETE | `/v2/orgs/{org_id}/documents/{id}` | Tenant Admin | Document management |
| GET/POST/DELETE | `/v2/orgs/{org_id}/api-keys` | Tenant Admin | API key CRUD |
| GET | `/v2/me` | Any Auth | Get authenticated principal + org details |

**Public routes** (require `X-API-Key: <api_key>`):

Not yet implemented (M2+): `/v2/token` (token exchange), `/v2/chat`, `/v2/chat/stream`.

## Development

```bash
cd backend && uv run pytest -q     # 189 tests, TDD, fully mocked
cd backend && uv run pytest tests/isolation -q  # cross-tenant isolation
cd frontend && npm run build && npm run lint
```

### Key testing conventions

- **No real LLM/embedding in tests**: Use mock fixtures. Ollama/OpenAI are runtime-only.
- **Org-scoping is mandatory**: Every new org-scoped module must add cases to `tests/isolation/` (the guard will fail the suite if routes are missing).
- **All tables must have org_id**: `tests/test_suite_quality.py` auto-checks.
- **TDD**: Test first, implement second.

### Adding a new module

1. **Define models** in `backend/app/newmodule/models.py` with `org_id` (always!).
2. **Write service** in `backend/app/newmodule/service.py` using `OrgScopedRepo(session, org_id)` for all data access.
3. **Write router** in `backend/app/newmodule/router.py` mounted at `/v2/orgs/{org_id}/...`.
4. **Guard**: Add the new routes to `tests/isolation/` matrix (the test will remind you).
5. **Add to main.py** `app.include_router(...)`.

## Deployment

**Development**:

```bash
docker compose up -d     # All services including Keycloak
```

**Production** (`docker-compose.prod.yml`):

- **No published host ports** (intentional — attach your own ingress/proxy to the internal network).
- Images: `api` (backend), `frontend`, `worker` (M1+), `postgres`, `redis`, `keycloak`.
- `migrate` service runs `alembic upgrade head` on startup, gates api/worker.

See `docker-compose.prod.yml` for detail; ingress/TLS is out of scope — bring your own (Nginx, Cloudflare, etc.).

## Git Workflow

Two protected branches:

- **`develop`** — day-to-day. Direct push allowed (no force-push/deletion); no PR required.
- **`main`** — release. PR required for all changes (enforced for admins); no force-push/deletion.

Typical flow:

```bash
git checkout develop && git pull
git checkout -b feature/my-feature
# ... work ...
git push -u origin feature/my-feature
gh pr create --base develop
```

When ready to release: open `develop` → `main` PR as the release gate.

## Documentation

- **`CLAUDE.md`** — Project conventions for Claude Code. Read first.
- **`docs/HARNESS_SPEC.md`** — Product spec (principals, FR/NFR, milestones M0–M5). Reference for why things are designed this way.
- **`docs/plans/M0.md`** — M0 implementation plan (task breakdown, risks, DoD evaluation).
- **`infra/keycloak/README.md`** — Keycloak realm setup, seed account, test accounts, Organizations.

## Known Limitations & Roadmap

**M0 (Done)**: Tenancy, identity, org-scoped CRUD.

**M1 (Next)**: 
- Run engine (durable Runs in Postgres, Postgres scheduler).
- Document ingestion (extract → chunk → embed → pgvector).
- Chat foundation (SSE, token exchange, citations).

**M2+**: End-user chat, widget embed, conversations, audit, quota, escalation, push notifications, channel adapters.

See `docs/HARNESS_SPEC.md` §5.2 (non-goals) for out-of-scope features (LLM hosting, billing, HITL, multi-agent, etc.).

