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
docker logs chatbot-worker --tail 5   # expect "Starting worker for 3 functions: ingest_document, process_chat_job, process_chat_job_stream"
```

## 4. Live smoke test (API/webhook/worker flow changes)

Start the API on a free port so you don't touch whatever the user may already have running on :8000 (`cd backend && uv run uvicorn app.main:app --port 8001 &`), then:

```bash
BASE=http://localhost:8001
curl -s $BASE/health                                                    # {"status":"ok"}
DOMAIN=$(curl -s -u admin:admin -X POST $BASE/api/domains \
  -H 'Content-Type: application/json' -d '{"name":"Smoke Test"}')       # 201, note the id
DOMAIN_ID=$(echo "$DOMAIN" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
AGENT=$(curl -s -u admin:admin -X POST $BASE/api/agents \
  -H 'Content-Type: application/json' \
  -d "{\"name\":\"Smoke Agent\",\"provider\":\"ollama\",\"model_name\":\"qwen2.5\",\"domain_ids\":[\"$DOMAIN_ID\"]}")  # 201, note the id
AGENT_ID=$(echo "$AGENT" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
APIKEY=$(curl -s -u admin:admin -X POST $BASE/api/api-keys \
  -H 'Content-Type: application/json' -d '{"name":"Smoke App"}')        # 201, note the raw "key"
KEY=$(echo "$APIKEY" | python3 -c "import sys,json;print(json.load(sys.stdin)['key'])")
curl -s -X POST $BASE/api/webhooks/generic \
  -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
  -d "{\"agent_id\":\"$AGENT_ID\",\"message\":\"hello\"}"               # 202 {"job_id": ...} — no domain_id, agent resolves its own domains
curl -s -H "X-API-Key: $KEY" $BASE/api/jobs/<job_id>                    # poll status
```

- With Ollama installed on the host (`ollama pull qwen2.5 nomic-embed-text`): expect `complete` with a reply.
- Without Ollama: `failed` with a connection error is the EXPECTED outcome and still proves webhook→queue→worker→polling works. Say so honestly in the report.
- Clean up: DELETE the smoke agent and domain (`curl -u admin:admin -X DELETE $BASE/api/agents/<id>` / `.../api/domains/<id>`), revoke the smoke API key, kill the uvicorn you started.

## 5. Migrations (schema changes)

```bash
cd backend && uv run alembic upgrade head && uv run alembic current
```
