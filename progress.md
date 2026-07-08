# Progress

Living document tracking project status. Update this file in the same commit as the work it describes (add a row to the log, move backlog items when picked up).

## Status

| Area | State | Notes |
|---|---|---|
| Infra (docker compose) | ✅ Done | postgres+pgvector :5432, pgadmin :5050, redis :6379, arq worker container |
| Backend core (config/db/auth) | ✅ Done | basic auth admin/admin via env |
| Domain CRUD | ✅ Done | `/api/domains`, uuid + slug |
| Document ingestion | ✅ Done | PDF/DOCX/TXT/MD → extract → chunk → embed → pgvector (HNSW cosine), async via arq |
| Agent framework (`app/agent/`) | ✅ Done | pure library: builder, dynamic tool loop, prompt templates, skills, Ollama adapter |
| Webhook + jobs (async AI branch) | ✅ Done | `POST /api/webhooks/{platform}` → queue → worker → `GET /api/jobs/{id}` polling |
| Channels | ✅ Generic only | `GenericAdapter`; real platforms not integrated yet |
| Frontend admin | ✅ Done | login, domains CRUD, documents upload + status, chat playground (Next.js 16) |
| Tests | ✅ 100 passing | TDD, LLM/embedding fully mocked |
| Real-LLM e2e | ⏳ Blocked | Ollama not installed on host yet |
| CI | ❌ Not started | |
| Deployment | ❌ Not started | local docker compose only |

## Backlog (rough priority)

1. Install Ollama on host (`ollama pull qwen2.5 nomic-embed-text`) and run a real chat e2e through the playground.
2. First real channel adapter (Telegram or Slack) — follow `.claude/skills/add-channel-adapter/`.
3. CI: GitHub Actions running `uv run pytest -q` (postgres+redis services) and `npm run build`.
4. Push-based responses: implement `send_response()` for platforms that support it (today: polling only).
5. Replace hardcoded basic auth with real user accounts when multi-admin is needed.
6. Ingestion niceties: re-ingest/retry failed documents from the UI, chunk size tuning per domain.
7. Conversation memory: persist chat history per `session_id` and feed it to the agent as `history`.

## Log

| Date | Change |
|---|---|
| 2026-07-08 | Kickoff: full platform built (BE 100 tests, FE build green, worker container running); repo pushed to `leqtrungit/chatbot-agent` |
| 2026-07-08 | Docs: README, CLAUDE.md, 4 project skills (`verify`, `add-channel-adapter`, `extend-agent`, `db-migration`) |
| 2026-07-08 | Added this progress tracker |
