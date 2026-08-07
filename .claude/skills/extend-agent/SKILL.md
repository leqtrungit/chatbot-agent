---
name: extend-agent
description: Extend the generic agent framework — add an LLM provider (OpenAI, Anthropic, ...), a tool, or a skill. Use for any change under backend/app/agent/ or when swapping/adding LLM vendors.
---

# Extend the agent framework

`app/agent/` is a pure library: no imports from FastAPI, SQLAlchemy, `app.core`, or `app.modules`. All additions below leave `core/agent.py` and `core/builder.py` untouched — if your change requires touching the loop or builder, stop and reconsider the design.

## New LLM provider (e.g. OpenAI, Anthropic)

1. Tests first: `tests/agent/test_<vendor>_provider.py`, mirroring `test_ollama_provider.py` — assert request payload mapping (messages incl. tool results, tools definitions, `ModelParams` → vendor params) and response parsing (text, tool_calls with ids, usage). Use httpx `MockTransport`; zero network.
2. Implement `app/agent/providers/<vendor>.py` satisfying the `LLMProvider` protocol (`providers/base.py`): `async chat(messages, *, model, tools, params) -> LLMResponse`. Normalize everything to the types in `core/types.py`; vendor quirks stay inside the adapter.
3. Export from `app/agent/providers/__init__.py` and `app/agent/__init__.py`.
4. To make it selectable per-agent: add it to `VALID_PROVIDERS` (`app/modules/agent/schemas.py`) and branch on it in `app/worker/tasks.py` `build_llm_provider(agent, settings)` — it already reads `agent.provider`/`agent.base_url`/`agent.api_key` with a `Settings` fallback; worker tests monkeypatch this factory, so they stay green.
5. New SDK dependency? Add to `backend/pyproject.toml` and run `uv sync` (this is the one allowed reason to touch pyproject).

## New tool

1. Tests first in `tests/agent/`: correct `to_definition()` schema; `execute` behavior including error/empty cases (an "empty result" message matters — the prompt relies on it for honesty).
2. Subclass `Tool` (`tools/base.py`) or use `FunctionTool` for simple cases. External resources (DB, HTTP) come in via constructor injection as a Protocol, concrete impl lives outside `app/agent/` (see `KnowledgeSearcher` / `PgVectorKnowledgeSearcher` for the pattern, and `app/agent/tools/mcp.py` for a remote-MCP-backed tool — `app/modules/mcp/client.py` glues registered `McpServer` rows to live connections).
3. Wire into the runtime agent in `app/worker/tasks.py` `build_agent()` if it should be available in chat by default (built-in tools), or make it attachable per-agent through `app/modules/agent/` + `app/modules/mcp/` if it should be admin-configurable instead of hard-wired.

## New skill

A `Skill` (`skills/base.py`) bundles a prompt fragment + tools. Compose via `AgentBuilder.with_skills([...])`. Duplicate tool names across skills/tools raise at build time — pick unique names.

## Changing a system prompt

There is no template-picker anymore. `Agent.system_prompt` (`app/modules/agent/models.py`) is free text, set per-agent via `/api/agents` or the `/agents` admin page, used verbatim by `build_agent()` in `app/worker/tasks.py` (no domain name/description auto-injected — the agent has `KnowledgeSearchTool` to look up domain content on demand instead). An empty `system_prompt` falls back to `AgentBuilder.DEFAULT_SYSTEM_PROMPT` (`app/agent/core/builder.py`) — don't add a forced default elsewhere. `app/agent/prompts/loader.py` (`PromptLoader`, jinja2 `.md` files under `app/agent/prompts/templates/`) still exists as infrastructure but nothing in the agent module references it anymore; only reach for it if you're deliberately building a new template-driven prompt for some other purpose.

## Done when

`uv run pytest tests/agent -q` green, full suite green, and `grep -rn "fastapi\|sqlalchemy\|app\.core\|app\.modules" backend/app/agent/` shows no real imports (docstrings mentioning them are fine).
