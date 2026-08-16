# Chatbot Agent Platform

A generic, domain-knowledge chatbot agent platform. Admins create **domains** (knowledge bases fed by uploaded documents) and **agents** (provider/model/tools/system-prompt configs, created and managed entirely in the admin UI — nothing hardcoded at deploy time), assign agents to the domains they should answer for, and any external platform talks to a chosen agent through a generic webhook with async job processing.

## Features

- **Admin UI** (Next.js 16 + shadcn/ui): basic-auth login, domain CRUD, document upload with live ingestion status, **agent management** (provider/model/credentials/free-text system prompt/tools, drawer-based create/edit), **MCP server registry**, chat playground.
- **Document ingestion pipeline**: PDF / DOCX / TXT / MD → extract → chunk → embed → pgvector (HNSW, cosine).
- **User-managed agents** (`backend/app/modules/agent/`): admins create agents choosing provider (Ollama / OpenAI-compatible), model, credentials, a free-text system prompt, and which domains + MCP tool servers the agent can use — no code change or redeploy needed to add a new agent.
- **Generic agent framework** (`backend/app/agent/`): provider-agnostic pure library —
  - fluent `AgentBuilder` (llm, model, sampling params, system prompt, tools, skills, max iterations)
  - dynamic tool-calling loop (the model decides which tools to call and when to stop)
  - LLM vendors are adapters (`Ollama`, `OpenAI`-compatible today; adding another touches nothing else)
  - `knowledge_search` tool searches across every domain an agent is assigned to — the model picks which domain per call once an agent covers more than one — with an honest "I don't know" when retrieval finds nothing
  - `app/modules/mcp/`: register remote MCP (HTTP/SSE) servers; their tools become available to any agent attached to them
- **Async AI branch**: webhook → Redis queue (arq) → agent worker (docker container) → client polls job status (or streams via SSE). Platform adapters (`ChannelAdapter`) normalize incoming payloads; a push-based `send_response` hook is ready for future platforms.

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

Admin routes for agents/tools (same Basic auth):

| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/agents` | list / create agent (provider, model, credentials, system prompt, `domain_ids`, `mcp_server_ids`) |
| GET/PUT/DELETE | `/api/agents/{id}` | read / update / delete |
| PUT | `/api/agents/{id}/domains`, `/api/domains/{id}/agents` | set the M2M assignment from either side |
| GET/POST | `/api/mcp-servers` | list / register a remote MCP (HTTP/SSE) server |
| GET/PUT/DELETE | `/api/mcp-servers/{id}` | read / update / delete |

Public routes (require `X-API-Key`, issued via `/api/api-keys`):

| Method | Path | Description |
|---|---|---|
| POST | `/api/webhooks/{platform}` | e.g. `generic`: `{"agent_id": "<uuid>", "message": "...", "session_id?": "..."}` → `202 {"job_id"}`. No `domain_id` — the agent searches across every domain it's assigned to itself. |
| GET | `/api/jobs/{job_id}` | `{"status": queued\|in_progress\|complete\|failed, "result": {"reply", ...}}` |
| POST | `/api/chat/stream` | same shape as the webhook, streams the reply token-by-token over SSE |

## Development

```bash
cd backend && uv run pytest -q     # 213 tests, TDD, LLM/embedding fully mocked (no Ollama needed)
cd frontend && npm run build       # type-checks the admin UI
```

Key extension points:

- **New LLM provider**: implement `LLMProvider` (`app/agent/providers/base.py`) — agent logic untouched.
- **New platform**: subclass `ChannelAdapter` (`app/channels/base.py`) and register it (`app/channels/registry.py`).
- **New system prompt**: agents have a free-text `system_prompt` field, editable per-agent from the `/agents` admin page — no code change or redeploy needed. Leaving it blank falls back to `AgentBuilder`'s built-in default.
- **New tool/skill**: implement `Tool` or compose a `Skill` (`app/agent/tools/`, `app/agent/skills/`), or register a remote MCP server from the `/mcp-servers` admin page and attach it to an agent — no code change needed for MCP tools.

See [CLAUDE.md](CLAUDE.md) for repo conventions (TDD, mock-only LLM in tests, agent-package purity rules).

## Git workflow

Two long-lived branches, both on GitHub with branch protection:

- **`develop`** — day-to-day work. Push directly (fast-forward or merge commits); force-push and branch deletion are blocked, but no PR is required.
- **`main`** — release branch. Protected: every change lands via a **pull request** (direct pushes are rejected, enforced for admins too), no force-push, no deletion. No required-approval count is set (solo-maintainer repo) — the PR requirement itself is the gate, not a review.

Typical flow:

```bash
git checkout develop && git pull
git checkout -b feature/whatever
# ... commit work ...
git push -u origin feature/whatever
gh pr create --base develop            # land day-to-day work into develop first

# when develop is stable and ready to release:
gh pr create --base main --head develop --title "Release: ..."
gh pr merge --squash --delete-branch   # only deletes the feature branch, not develop
```

Feature branches are deleted after merging into `develop`; `develop` itself is never deleted. Cut a release by opening `develop` → `main` as a PR when ready — that PR is the release gate.
