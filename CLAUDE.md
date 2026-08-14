# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Generic domain-knowledge chatbot agent platform. Monorepo: `backend/` (FastAPI, Python 3.12, managed by `uv`) and `frontend/` (Next.js 16 admin UI). Admins create *domains* (knowledge bases, fed by uploaded documents) and *agents* (provider/model/credentials/system-prompt/tools, created and managed entirely via the admin UI — nothing hardcoded at deploy time), assign agents to the domains they should answer for, and external platforms talk to a specific agent through a generic webhook + async job queue.

## Commands

Infra (postgres+pgvector :5432, pgadmin :5050, redis :6379, arq worker container):

```bash
docker compose up -d                 # worker is built from backend/Dockerfile
docker compose build worker          # rebuild worker after backend changes
```

Backend (from `backend/`; `uv` lives in `~/.local/bin`):

```bash
uv sync                              # install deps (incl. dev group)
uv run pytest -q                     # full suite — must stay green
uv run pytest tests/agent -q         # one package
uv run pytest tests/modules/test_domain_api.py -k create   # single test
uv run alembic upgrade head          # migrate the docker postgres
uv run alembic revision --autogenerate -m "..."
uv run uvicorn app.main:app --port 8000        # API (worker runs in docker)
uv run arq app.worker.settings.WorkerSettings  # worker locally instead of container
```

Frontend (from `frontend/`):

```bash
npm run dev      # http://localhost:3000, login admin/admin
npm run build    # must pass before considering FE work done
npm run lint
```

DB-backed tests require the docker postgres to be running; they create/drop a separate `chatbot_test` database (see `tests/modules/conftest.py`). Config comes from `.env` at repo root (copy `.env.example`); defaults work with the compose setup.

## Hard rules

- **TDD**: write failing tests first, then implement. All backend work ships with tests.
- **Never call a real LLM/embedding service in tests.** Inject `MockLLMProvider` / `MockEmbeddingProvider` from `backend/tests/conftest.py` (scriptable response queues). Ollama is runtime-only and may not even be installed on the host.
- **`app/agent/` is a pure library**: it must not import FastAPI, SQLAlchemy, `app.core`, or `app.modules`. External capabilities (LLM, vector search) enter via the protocols in `app/agent/providers/base.py` and `app/agent/tools/knowledge_search.py` (`KnowledgeSearcher`). Concrete implementations live outside the package and are injected.
- Swapping LLM provider = add one adapter in `app/agent/providers/`; never touch agent loop/builder. System prompts are per-agent free text (`Agent.system_prompt`, set via the admin UI/API, used verbatim — no domain name/description auto-injected); never hard-code prompts in Python. `AgentBuilder`'s own `DEFAULT_SYSTEM_PROMPT` (`app/agent/core/builder.py`) is the fallback when an agent's `system_prompt` is empty.

## Architecture

Three request paths share one database:

**Ingestion (admin, basic auth from `Settings.ADMIN_USERNAME/PASSWORD`):**
`POST /api/domains/{id}/documents` (multipart) → `app/modules/document/router.py` stores the file under `backend/data/uploads/` + a `pending` row, then enqueues arq job `ingest_document` (`app/modules/document/jobs.py`). The worker (`app/worker/tasks.py`) calls `app/modules/document/pipeline/ingest.py`: extract (pypdf/python-docx/plain) → chunk (char-based, overlap) → embed (`EmbeddingProvider`) → `document_chunks` rows with `Vector(768)` + status transitions pending→processing→completed/failed. Pipeline steps are pure functions, individually tested.

**Agent management (admin, basic auth):**
`app/modules/agent/` — `Agent` CRUD (`/api/agents`): provider (`ollama`/`openai`), model, base_url/api_key, free-text `system_prompt`, sampling params, `enable_knowledge_search`, many-to-many to `Domain` (`domain_agents`) and to `McpServer` (`agent_mcp_servers`, via `app/modules/mcp/`). Assignment can be set from either side: `PUT /api/agents/{id}/domains` or `PUT /api/domains/{id}/agents`. None of this touches `app/agent/` — it's pure config that `app/worker/tasks.py::build_agent` reads at chat time.

**Chat (external, requires `X-API-Key` — `app/modules/apikey/`):**
`POST /api/webhooks/{platform}` → `ChannelRegistry` (`app/channels/registry.py`) resolves a `ChannelAdapter` which normalizes the payload to `IncomingMessage` (`agent_id`, `session_id`, `text`, `metadata`, optional `history` — **no `domain_id`**); the agent is resolved directly via `app.modules.agent.service.get_agent`; job `process_chat_job` enqueued → `202 {job_id}`. Client polls `GET /api/jobs/{job_id}` (wraps arq job status) or streams via `POST /api/chat/stream` (SSE, same contract, same optional `history`). The worker builds the agent via `build_agent` (`app/worker/tasks.py`): `AgentBuilder` + provider adapter (from `agent.provider`/`agent.base_url`/`agent.api_key`) + `KnowledgeSearchTool` scoped to **every domain the agent is assigned to** (`agent.domains`) — backed by `PgVectorKnowledgeSearcher` (`app/modules/knowledge/searcher.py`, cosine distance, only `completed` docs). An agent with exactly one domain gets the tool's original single-domain behavior; 2+ domains adds an LLM-selectable `domain` enum parameter (domain slugs) so the model picks which knowledge base to query per call — there is no domain param in the request at all, the agent decides. `agent.system_prompt` is used verbatim (no domain name/description auto-injected); empty falls back to `AgentBuilder`'s `DEFAULT_SYSTEM_PROMPT`. Conversation history (`app/modules/conversation/`) is keyed by `(agent_id, session_id)`, not domain, and is server-managed by default (loaded before the agent run, appended after). A caller can instead go **client-managed** by sending a `history` array (`[{role, content}]`, `role` restricted to `user`/`assistant`, capped at `Settings.MAX_CLIENT_HISTORY_MESSAGES`) with the request: the worker then uses that list verbatim and skips `chat_messages` entirely for that call (no load, no append) — `GET /api/conversations/{agent_id}/{session_id}/messages` will return nothing for such a session, since nothing was ever persisted. Omitting `history` is a no-op — the field's absence (not an empty array) is the signal for server-managed mode, so every existing caller is unaffected. `knowledge_search` results carry `[n]` markers that the agent cites inline in its answer; the referenced sources come back as `citations` on the job result and the SSE `done` event, and are persisted on the assistant `chat_messages` row. Adapter `send_response()` is a no-op today (polling/SSE is the response channel); future platforms implement it for push.

**Agent loop** (`app/agent/core/agent.py`): dynamic Claude-style loop — call LLM, execute any tool_calls concurrently (tool errors become `is_error` results, never crash the loop), append results, repeat until plain-text answer or `max_iterations`. No hard-coded tool sequences.

Adding a platform = one `ChannelAdapter` subclass registered in the registry; nothing else changes.

## Project skills

Reusable playbooks live in `.claude/skills/` — prefer them over improvising:

- `/verify` — layered stack verification (pytest, FE build, worker container, live webhook smoke test)
- `/add-channel-adapter` — integrate a new platform (Telegram/Slack/...) via `ChannelAdapter`
- `/extend-agent` — add an LLM provider, tool, skill, or prompt template without touching agent logic
- `/db-migration` — Alembic workflow incl. pgvector pitfalls autogenerate misses

## Git workflow

Two protected branches — `develop` (day-to-day, direct push allowed, no force-push/deletion) and `main` (release, PR-only, enforced for admins too, no required-approval count since it's a solo repo). Feature branches land in `develop` via PR and get deleted; cut a release by PR'ing `develop` → `main`. Full detail in [README.md](README.md#git-workflow). Don't push directly to `main` — it will be rejected.

## Progress tracking

`progress.md` tracks status, backlog, and a change log. When completing significant work, update it in the same commit (status table + log row; pull backlog items when picking them up).

## Gotchas

- Frontend is **Next.js 16** — conventions differ from training data (`src/proxy.ts` replaces `middleware.ts`; dynamic route `params` are async). See `frontend/AGENTS.md` and `node_modules/next/dist/docs/` before writing FE code. shadcn components here are base-ui based (`render={...}` composition), not Radix.
- arq job kwargs must be JSON-serializable — worker tests inject fakes by monkeypatching `app.worker.tasks` symbols (`build_llm_provider`, `PgVectorKnowledgeSearcher`), not via job args.
- Don't edit root `tests/conftest.py` casually; test-package-local fixtures go in `tests/<pkg>/conftest.py`.
- Embedding dimension is fixed at 768 (`Vector(768)` column + HNSW index); changing `EMBEDDING_DIM` requires a migration.
