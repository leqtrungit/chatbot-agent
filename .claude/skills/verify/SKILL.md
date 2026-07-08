---
name: verify
description: Verify the chatbot-agent stack end-to-end after a change — backend tests, frontend build, worker container, and a live webhook→job smoke test. Use before declaring any nontrivial change done.
---

# Verify the stack

Run the layers relevant to what changed; run everything before a commit that touches both sides. `uv` and `gh` live in `~/.local/bin` (add to PATH if missing).

## 1. Backend tests (any backend change)

```bash
cd backend && uv run pytest -q
```

- Requires docker postgres up: `docker compose up -d postgres redis`.
- Must be fully green — never commit with failing tests.
- Tests must never call Ollama; if a new test needs an LLM/embedding, inject `MockLLMProvider`/`MockEmbeddingProvider` from `tests/conftest.py`.

## 2. Frontend build (any frontend change)

```bash
cd frontend && npm run build && npm run lint
```

Build failure = type error; fix before done.

## 3. Worker container (changes under `backend/app/worker/`, `app/agent/`, pipeline, or deps)

```bash
docker compose build worker && docker compose up -d worker
docker logs chatbot-worker --tail 5   # expect "Starting worker for 2 functions: ingest_document, process_chat_job"
```

## 4. Live smoke test (API/webhook/worker flow changes)

Start the API (`cd backend && uv run uvicorn app.main:app --port 8000 &`), then:

```bash
curl -s http://localhost:8000/health                                   # {"status":"ok"}
curl -s -u admin:admin -X POST http://localhost:8000/api/domains \
  -H 'Content-Type: application/json' -d '{"name":"Smoke Test"}'       # 200, note the id
curl -s -X POST http://localhost:8000/api/webhooks/generic \
  -H 'Content-Type: application/json' \
  -d '{"domain_id":"smoke-test","message":"hello"}'                    # 202 {"job_id": ...}
curl -s http://localhost:8000/api/jobs/<job_id>                        # poll status
```

- With Ollama installed on the host (`ollama pull qwen2.5 nomic-embed-text`): expect `complete` with a reply.
- Without Ollama: `failed` with a connection error is the EXPECTED outcome and still proves webhook→queue→worker→polling works. Say so honestly in the report.
- Clean up: DELETE the smoke domain (`curl -u admin:admin -X DELETE .../api/domains/<id>`), kill the uvicorn you started.

## 5. Migrations (schema changes)

```bash
cd backend && uv run alembic upgrade head && uv run alembic current
```
