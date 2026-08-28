# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Agent Harness Platform** — a SaaS platform for creating, managing, and running AI agents on customer organizations' own infrastructure. Built on **multi-tenant architecture from day one**, with Keycloak OIDC for identity, PostgreSQL as the single source of truth, and Redis as ephemeral transport only (pub/sub, cache, rate-limit).

Monorepo structure:
- `backend/` — FastAPI (Python 3.12, async SQLAlchemy, managed by `uv`)
- `frontend/` — Next.js 16 admin UI (TypeScript, shadcn/ui)
- `infra/` — Docker Compose, Keycloak realm as-code

**M0 scope (current branch: `refactor/build-harness`)**: Tenancy & Identity layer — org-scoped CRUD for agents and knowledge bases, Keycloak OIDC authentication, multi-tenant isolation. Document ingestion, chat, and Run engine belong to M1+.

## Architecture — Principals & Modules

Four authenticated principals (§3 HARNESS_SPEC.md):

1. **Operator** (realm role `operator`) — Platform operator, creates/suspends organizations, views platform health.
2. **Tenant Admin** (Keycloak Organization member) — Manages their organization: agents, knowledge bases, API keys, quota, trace.
3. **Integration** (API key, server-side only) — Tenant's backend; token exchange, server-to-server chat (M2+).
4. **End-user** (JWT from token exchange) — End-user chat; session data isolation (M2+).

**Module layout** (`backend/app/`):

```
core/
  ├── config.py — Settings from env (.env, .env.local)
  ├── db.py — Async SQLAlchemy engine/session
  ├── security.py — JWKS verifier, principal extraction (OperatorPrincipal, TenantPrincipal)
  └── tenancy.py — org_query(), OrgScopedRepo (enforce org-scoping at data-access layer, NFR-SEC1)

identity/
  ├── deps.py — FastAPI dependencies: require_operator, require_org_member, require_any_principal
  ├── org_access.py — Guard for route org_id matching (T4+)
  └── router.py — GET /v2/me (operator / tenant info + org details)

orgs/
  ├── models.py — Organization{id, name, slug, keycloak_org_id, status}
  ├── service.py — Org creation, KC Admin API integration
  ├── router.py — POST /v2/operator/orgs (create), suspend, list
  └── kc_admin.py — Keycloak Admin REST API client

apikeys/
  ├── models.py — ApiKey{org_id, name, key_hash, revoked_at}
  ├── service.py — Create/revoke, hash validation
  ├── router.py — GET/POST /v2/orgs/{org_id}/api-keys
  └── deps.py — require_api_key (for M2 chat/webhook)

agents/
  ├── models.py — Agent{org_id, name, provider, model, base_url, api_key, system_prompt, ...}
  ├── service.py — CRUD, soft delete (is_active)
  ├── router.py — GET/POST /v2/orgs/{org_id}/agents; agent↔KB assignment
  └── schemas.py — Request/response DTOs

knowledge/
  ├── models.py — KnowledgeBase{org_id, name, slug}, Document{org_id, kb_id, ...}, DocumentChunk{org_id, embedding}
  ├── service.py — CRUD, file upload (stores under data/uploads/{org_id}/)
  ├── router.py — GET/POST /v2/orgs/{org_id}/knowledge-bases; documents upload/list/delete
  ├── storage.py — Local filesystem storage abstraction
  └── schemas.py — DTOs

main.py — App factory, /health, router mounting
```

**Database** — Single async SQLAlchemy session per request; **mutable query MUST go through `OrgScopedRepo` or `org_query()`**. Every business table has `org_id NOT NULL + FK + index`.

## Commands

**Infra** (from repo root):

```bash
cp .env.example .env
docker compose up -d                # postgres:5432, redis:6379, keycloak:8080, kc-postgres
docker compose logs keycloak        # watch Keycloak startup; realm import logged
docker compose exec postgres psql -U chatbot -d chatbot -c "\dt"  # verify tables
```

Keycloak starts with realm `harness` pre-imported:
- Admin user: `admin` / `admin` (credentials in `infra/keycloak/seed.sh`; change in production)
- Client `admin-ui` (public, PKCE, redirect `http://localhost:3000/callback`)
- Client `backend` (bearer-only, audience `backend`)
- Realm role `operator` (for platform operator principal)
- Organizations feature enabled

**Backend** (from `backend/`; `uv` at `~/.local/bin`):

```bash
uv sync                              # install deps (incl. dev, test groups)
uv run pytest -q                     # 189 tests, TDD, no real LLM/embedding calls
uv run pytest tests/isolation -q     # cross-tenant isolation suite (NFR-SEC1)
uv run pytest tests/test_suite_quality.py -q  # guard: no empty tests, all tables scoped by org_id
uv run alembic upgrade head          # migrate docker postgres
uv run uvicorn app.main:app --port 8000  # API server
```

**Frontend** (from `frontend/`):

```bash
npm install
npm run dev      # http://localhost:3000 → Keycloak login flow
npm run build    # must pass before FE work is done
npm run lint
```

**Keycloak tenant admin account** (for testing FE login):

Seed a user in realm `harness` with Organization membership:

```bash
docker compose exec keycloak \
  /opt/keycloak/bin/kcadm.sh create users \
  -r harness \
  -s username=alice \
  -s email=alice@example.com \
  -s 'emailVerified=true' \
  -s 'enabled=true' \
  -s 'credentials=[{"type":"password","value":"alice-pass"}]'
```

Then add Alice to a Keycloak Organization (via KC UI admin console at `http://localhost:8080/admin` or API in infra/keycloak/README.md).

## Hard rules

- **TDD**: write failing tests first, then implement. Every backend change ships with tests.
- **No real LLM/embedding in tests**. Use `MockLLMProvider`/`MockEmbeddingProvider` fixtures from `tests/conftest.py`. Ollama/OpenAI are runtime-only.
- **Org-scoping is mandatory for all business data**: mutable queries MUST use `OrgScopedRepo(session, org_id).get/list/add/delete` or `org_query(Model, org_id)`. Grep audit: `tests/test_suite_quality.py` auto-fails any `select(Model)` in `app/*/` modules (not in `core/`). **Build the habit now** — every new module inherits this guard.
- **`app/agent/` is a pure library** (reserved for M1+, currently empty): it must never import FastAPI, SQLAlchemy, `app.core`, or `app.modules`. External capabilities (LLM, vector search) enter via protocols. Concrete implementations live outside and are injected at runtime.
- **Every business table must have `org_id`**: schema review checks it; test infrastructure enforces it (`tests/test_suite_quality.py`). If a colleague adds a table without `org_id`, the suite fails before merge.
- **Cross-tenant isolation test is mandatory** for every new org-scoped route: add a case to `tests/isolation/` matrix. Build system will fail if a route is missing from the matrix (introspection-based guard — see `tests/isolation/conftest.py`). This is the single best defense against accidental cross-tenant leaks.
- **Keycloak issuer vs JWKS URL are intentionally different**:
  - `KEYCLOAK_ISSUER=http://localhost:8080/realms/harness` — what the token *claims* as the issuer (from browser perspective, the token says "issued by localhost:8080")
  - `KEYCLOAK_JWKS_URL=http://keycloak:8080/realms/harness/protocol/openid-connect/certs` — where the backend *fetches* the signing keys (uses internal Docker Compose service name `keycloak`, not routable from the browser)
  - Token issuer is set by Keycloak at token generation time; backend must verify against the token's issuer claim, so `KEYCLOAK_ISSUER` must match exactly what the token says. For local dev, both are localhost (api service also runs on host); for compose, ISSUER stays localhost (browser-facing) while JWKS_URL uses the container service name.
- **Realm config is minimal and read-only**: `infra/keycloak/realm-export.json` is hand-maintained, not auto-exported. Keycloak rejects import if there are unknown fields — keep it sparse. Bootstrap any new test accounts or Organizations via API (`kc_admin.py`) or `seed.sh`, not by editing the export.
- **Async SQLAlchemy relationships require `lazy="selectin"`**: lazy-load mismatch on async cause `MissingGreenlet` errors. See `backend/app/orgs/models.py` for the pattern.
- **In tests, do not let helper functions call `mkdir()` on fixed paths**: use `tmp_path` fixture (pytest magic temp dir). Code that's green on dev (`/tmp` exists, writable) fails on CI (container sandbox, stricter). Same for file I/O: always scope to `tmp_path`.
- **Don't import test conftest from sibling packages**: pytest registers conftest plugins, and importing from `tests.other_package.conftest` causes fixture double-registration → test collection crashes. Shared fixtures go in root `tests/conftest.py` only.
- **Docker `next.config.ts` rewrites are for `/api/*` AND `/v2/*`** but **NOT `/auth/*` (Keycloak)**: browser talks to Keycloak directly at `http://localhost:8080`, bypassing the proxy. The rewrite setup in `frontend/next.config.ts` points these paths to `http://api:8000` (internal compose service name). This is load-bearing — Keycloak hostnames in the FE build bundle must never appear (we verified via grep of `dist/` chunks), else cross-origin fails. CORS applies to browser API calls only; admin UI traffic is same-origin via the rewrite.
- **Known gap recorded here for future reference**: `document_chunks` does not record which embedding model produced a vector. Swapping `EMBEDDING_MODEL` to a different model of the same vector width silently returns nonsense search hits on pre-existing documents (different models = different vector spaces). Fix requires a `documents.embedding_model` column + searcher guard + re-ingest job — deferred by design, will be done in M1/M2 during the embeddings/ingestion work.

## Project skills (`.claude/skills/`)

- `/verify` — layered stack verification (pytest, FE build, docker-compose smoke, Keycloak realm import). **Status**: Updated for v2 in this milestone.
- `/add-channel-adapter` — integrate a new platform (Telegram/Slack/etc.) via `ChannelAdapter`. **Status**: Obsolete (ChannelAdapter, webhook routes, arq jobs all removed in M0). Skill file remains but will be rewritten in M2 when chat surface is live.
- `/extend-agent` — add an LLM provider, tool, skill. **Status**: Obsolete (agent loop, tools, `app/agent/` all removed in M0). Skill remains for reference; will be revived in M1 when Run engine lands.
- `/db-migration` — Alembic workflow with pgvector safety checks. **Status**: Valid; single migration `001_v2_base_schema.py` created by T3, new migrations use same pattern.

## Test structure

```
tests/
├── conftest.py — root fixtures (db session, jwks_verifier, keycloak_client, create_test_org)
├── isolation/
│   ├── conftest.py — fixtures for multi-org/multi-principal scenarios
│   ├── test_cross_tenant_matrix.py — access matrix (Operator/Tenant × Org A/Org B) on all org-scoped endpoints
│   └── test_route_coverage.py — introspection guard: all /v2/ routes in isolation matrix (auto-fail if route missing)
├── test_suite_quality.py — meta-tests: org_id on all tables, no select() outside tenancy layer, no empty tests
├── orgs/
│   ├── conftest.py — org-specific fixtures
│   └── test_*.py — org CRUD, KC Admin API mock
├── apikeys/
│   └── test_*.py — key creation/revocation, hash validation
├── agents/
│   └── test_*.py — agent CRUD, soft delete, org-scoping
└── knowledge/
    └── test_*.py — KB CRUD, document upload (file on disk check), org-scoped paths
```

**Test database**: Separate `chatbot_test` database (auto-created/dropped per run by `tests/conftest.py`). Config from `.env` (defaults work with compose setup).

## Git workflow

Two protected branches on GitHub:

- **`develop`** — day-to-day work. Push directly allowed (fast-forward or merge commits); force-push and deletion blocked. No PR required.
- **`main`** — release branch. PR required for every change (enforced for admins too); no force-push, no deletion. No required-approval count (solo repo) — PR requirement itself is the gate.

Typical flow:

```bash
git checkout develop && git pull
git checkout -b feature/my-task
# ... commit work ...
git push -u origin feature/my-task
gh pr create --base develop            # land day-to-day work into develop
```

When ready to release: open a `develop` → `main` PR as the release gate.

## Progress & Status

`progress.md` tracks project status and change log. Update it in the same commit as significant work (add row to status table, move backlog items, log the change). Current milestone: **M0 (Tenancy & Identity)** — test cách ly cross-tenant xanh; Keycloak realm working; org/apikey/agent/KB modules org-scoped and isolated. See `docs/plans/M0.md` for detailed task breakdown and DoD.

## Known gaps (deferred to M1+)

- **Document ingestion** — M0 has upload + DB row `pending`, no runtime processing. Ingest job belongs to M1 (Postgres-native scheduler, ADR-1).
- **Chat & Embed** — webhook, SSE, widget, token exchange (FR-C1..C4) — all M2.
- **Run engine** — durable Run record, event sourcing, lease+heartbeat scheduling, RunEvents (FR-R1..R8) — M1.
- **Conversations** — server-managed history (FR-C2) — M2.
- **End-user directory & privacy** — end-user CRUD, block, data erasure (FR-O7, O8, O9) — M2/M3.
- **Control plane observability** — Run list, trace viewer, conversation viewer, usage dashboard, quota (FR-O1..O5) — M3.
- **Channel adapters** — Telegram, Slack, Zalo (M2+ after embed surface stable).
- **MCP server registration** — schema/model exist, admin UI for `/mcp-servers` deferred to M3.

## .env configuration

See `.env.example` for all variables. Key ones for local dev:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://chatbot:chatbot@localhost:5432/chatbot
REDIS_URL=redis://localhost:6379/0

# Keycloak
KEYCLOAK_ISSUER=http://localhost:8080/realms/harness
KEYCLOAK_JWKS_URL=http://keycloak:8080/realms/harness/protocol/openid-connect/certs
KEYCLOAK_AUDIENCE=backend

# Document storage
UPLOAD_DIR=data/uploads

# CORS
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

`docker compose` reads these and passes them to containers. Frontend reads `NEXT_PUBLIC_API_URL` from `frontend/.env.local`.

