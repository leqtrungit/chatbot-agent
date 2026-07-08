# Chatbot Agent Platform

A generic, domain-knowledge chatbot agent platform. Admins create **domains**, feed them documents (embedded into Postgres/pgvector), and any external platform can talk to a domain-scoped RAG agent through a generic webhook with async job processing.

## Features

- **Admin UI** (Next.js 16 + shadcn/ui): basic-auth login, domain CRUD, document upload with live ingestion status, chat playground.
- **Document ingestion pipeline**: PDF / DOCX / TXT / MD → extract → chunk → embed → pgvector (HNSW, cosine).
- **Generic agent framework** (`backend/app/agent/`): provider-agnostic pure library —
  - fluent `AgentBuilder` (llm, model, sampling params, prompt template, tools, skills, max iterations)
  - dynamic tool-calling loop (the model decides which tools to call and when to stop)
  - prompts are jinja2 template files, swappable without code changes
  - LLM vendors are adapters (`Ollama` today; adding another touches nothing else)
  - domain-grounded answers with an honest "I don't know" when retrieval finds nothing
- **Async AI branch**: webhook → Redis queue (arq) → agent worker (docker container) → client polls job status. Platform adapters (`ChannelAdapter`) normalize incoming payloads; a push-based `send_response` hook is ready for future platforms.

## Architecture

```
                    ┌────────────┐  basic auth   ┌─────────────────────────┐
  Admin (Next.js) ──►  FastAPI   ├───────────────► domains / documents CRUD│
                    │            │               └───────────┬─────────────┘
                    │  /api/...  │                     upload│ enqueue "ingest_document"
                    └─────┬──────┘                           ▼
 External platform        │                        ┌──────────────────┐
  POST /api/webhooks/{platform}                    │  Redis (arq)     │
        │  ChannelAdapter normalizes               └───────┬──────────┘
        ▼                                                  ▼
   202 {job_id}  ◄──── enqueue "process_chat_job"   arq worker (docker)
        │                                                  │
  GET /api/jobs/{id} ◄──── result ──── agent loop ── LLM (Ollama)
        (polling)                          │
                                           └─ knowledge_search tool ──► pgvector
```

## Quickstart

Requirements: Docker, Python 3.12 + [uv](https://docs.astral.sh/uv/), Node.js, and [Ollama](https://ollama.com) for real chat (tests don't need it).

```bash
cp .env.example .env
docker compose up -d                # postgres+pgvector, pgadmin, redis, agent worker

# backend
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --port 8000

# frontend (new terminal)
cd frontend
npm install
npm run dev                         # http://localhost:3000 — login admin/admin

# LLM (for real chat; the worker container reaches the host's Ollama)
ollama pull qwen2.5 && ollama pull nomic-embed-text
```

pgAdmin: http://localhost:5050 (`admin@local.dev` / `admin`).

## API overview

Admin routes (HTTP Basic, `ADMIN_USERNAME`/`ADMIN_PASSWORD`, default `admin`/`admin`):

| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/domains` | list / create domain |
| GET/PUT/DELETE | `/api/domains/{id}` | read / update / delete (cascades documents) |
| POST | `/api/domains/{id}/documents` | multipart upload (`.pdf .docx .txt .md`) → 202, async ingestion |
| GET | `/api/domains/{id}/documents` | list documents with status |
| DELETE | `/api/documents/{id}` | delete document + chunks + file |

Public routes (no auth):

| Method | Path | Description |
|---|---|---|
| POST | `/api/webhooks/{platform}` | e.g. `generic`: `{"domain_id": "<uuid or slug>", "message": "...", "session_id?": "..."}` → `202 {"job_id"}` |
| GET | `/api/jobs/{job_id}` | `{"status": queued\|in_progress\|complete\|failed, "result": {"reply", ...}}` |

## Development

```bash
cd backend && uv run pytest -q     # 100 tests, TDD, LLM/embedding fully mocked (no Ollama needed)
cd frontend && npm run build       # type-checks the admin UI
```

Key extension points:

- **New LLM provider**: implement `LLMProvider` (`app/agent/providers/base.py`) — agent logic untouched.
- **New platform**: subclass `ChannelAdapter` (`app/channels/base.py`) and register it (`app/channels/registry.py`).
- **New system prompt**: drop a jinja2 `.md` file in `app/agent/prompts/templates/`, point `AGENT_SYSTEM_PROMPT_TEMPLATE` at it.
- **New tool/skill**: implement `Tool` or compose a `Skill` (`app/agent/tools/`, `app/agent/skills/`).

See [CLAUDE.md](CLAUDE.md) for repo conventions (TDD, mock-only LLM in tests, agent-package purity rules).
