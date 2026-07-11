# Progress

Living document tracking project status. Update this file in the same commit as the work it describes (add a row to the log, move backlog items when picked up).

## Status

| Area | State | Notes |
|---|---|---|
| Infra (docker compose) | ✅ Done | postgres+pgvector :5432, pgadmin :5050, redis :6379, arq worker container |
| Backend core (config/db/auth) | ✅ Done | basic auth admin/admin via env |
| Domain CRUD | ✅ Done | `/api/domains`, uuid + slug |
| Document ingestion | ✅ Done | PDF/DOCX/TXT/MD → extract → chunk → embed → pgvector (HNSW cosine), async via arq |
| Agent framework (`app/agent/`) | ✅ Done | pure library: builder, dynamic tool loop, prompt templates, skills, Ollama + OpenAI-compatible adapters |
| Webhook + jobs (async AI branch) | ✅ Done | `POST /api/webhooks/{platform}` → queue → worker → `GET /api/jobs/{id}` polling |
| Webhook auth + rate limiting | ✅ Done | `app/modules/apikey/` (admin CRUD, `X-API-Key`), fixed-window Redis rate limit per key + per session (Phase A of webhook-auth/memory/OpenAI-provider plan) |
| Conversation memory | ✅ Done | `app/modules/conversation/` (`chat_messages` table, migration `e717eccd3cad`), worker loads last `CHAT_HISTORY_LIMIT` turns and persists each turn after the agent replies (Phase B of same plan) |
| Channels | ✅ Generic only | `GenericAdapter`; real platforms not integrated yet |
| Frontend admin | ✅ Done | login, domains CRUD, documents upload + status, chat playground (Next.js 16), API keys management |
| Tests | ✅ 135 passing | TDD, LLM/embedding fully mocked |
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
7. ~~Conversation memory~~ — done (see Phase B log entry below).
8. ~~Phase C of webhook-auth/memory/OpenAI-provider plan~~ — done (see log below).

## Log

| Date | Change |
|---|---|
| 2026-07-08 | Kickoff: full platform built (BE 100 tests, FE build green, worker container running); repo pushed to `leqtrungit/chatbot-agent` |
| 2026-07-08 | Docs: README, CLAUDE.md, 4 project skills (`verify`, `add-channel-adapter`, `extend-agent`, `db-migration`) |
| 2026-07-08 | Added this progress tracker |
| 2026-07-11 | Phase A of webhook-auth/memory/OpenAI-provider plan: `app/modules/apikey/` (model+migration `e272b45380b3`, admin CRUD), `require_api_key` on webhook + job-status endpoints, `app/core/ratelimit.py` fixed-window Redis limiter (per-key + per-session, 429 + Retry-After), FE `api-keys` page + nav + playground API key input. BE 117 tests passing, FE build green. Not yet committed. |
| 2026-07-11 | Phase B of same plan: `app/modules/conversation/` (`ChatMessage` model + migration `e717eccd3cad`, `load_history`/`append_turn`), new setting `CHAT_HISTORY_LIMIT` (default 20), `process_chat_job` now loads history before `agent.run(text, history=...)` and persists the user+assistant turn after a successful reply (nothing persisted if the agent raises). `app/agent/` untouched. BE 122 tests passing. Not yet committed. |
| 2026-07-11 | Phase C of same plan: `app/agent/providers/openai_compat.py` (`OpenAICompatProvider`, OpenAI Chat Completions mapping — Bearer auth, tool_calls with JSON-string arguments and real echoed ids, tool-result messages, `ModelParams`→temperature/top_p/max_tokens/stop/seed+extra, `prompt_tokens`/`completion_tokens` usage), exported from `app/agent/providers/__init__.py`. New settings `LLM_PROVIDER` (`ollama`\|`openai`), `OPENAI_BASE_URL`, `OPENAI_API_KEY`; `build_llm_provider` branches on `LLM_PROVIDER` and raises `ValueError` on an unknown value. `.env.example`/`.env` updated (default stays `ollama`). `app/agent/core/agent.py` and `builder.py` untouched. BE 135 tests passing. Not yet committed. |
