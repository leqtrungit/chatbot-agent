---
name: extend-agent
description: Extend the generic agent framework — add an LLM provider (OpenAI, Anthropic, ...), a tool, a skill, or a system prompt template. Use for any change under backend/app/agent/ or when swapping/adding LLM vendors.
---

# Extend the agent framework

`app/agent/` is a pure library: no imports from FastAPI, SQLAlchemy, `app.core`, or `app.modules`. All additions below leave `core/agent.py` and `core/builder.py` untouched — if your change requires touching the loop or builder, stop and reconsider the design.

## New LLM provider (e.g. OpenAI, Anthropic)

1. Tests first: `tests/agent/test_<vendor>_provider.py`, mirroring `test_ollama_provider.py` — assert request payload mapping (messages incl. tool results, tools definitions, `ModelParams` → vendor params) and response parsing (text, tool_calls with ids, usage). Use httpx `MockTransport`; zero network.
2. Implement `app/agent/providers/<vendor>.py` satisfying the `LLMProvider` protocol (`providers/base.py`): `async chat(messages, *, model, tools, params) -> LLMResponse`. Normalize everything to the types in `core/types.py`; vendor quirks stay inside the adapter.
3. Export from `app/agent/providers/__init__.py` and `app/agent/__init__.py`.
4. To make it the runtime default: wire it in `app/worker/tasks.py` `build_llm_provider()` behind a `Settings` value — worker tests monkeypatch this factory, so they stay green.
5. New SDK dependency? Add to `backend/pyproject.toml` and run `uv sync` (this is the one allowed reason to touch pyproject).

## New tool

1. Tests first in `tests/agent/`: correct `to_definition()` schema; `execute` behavior including error/empty cases (an "empty result" message matters — the prompt relies on it for honesty).
2. Subclass `Tool` (`tools/base.py`) or use `FunctionTool` for simple cases. External resources (DB, HTTP) come in via constructor injection as a Protocol, concrete impl lives outside `app/agent/` (see `KnowledgeSearcher` / `PgVectorKnowledgeSearcher` for the pattern).
3. Wire into the runtime agent in `app/worker/tasks.py` `build_domain_agent()` if it should be available in chat.

## New skill

A `Skill` (`skills/base.py`) bundles a prompt fragment + tools. Compose via `AgentBuilder.with_skills([...])`. Duplicate tool names across skills/tools raise at build time — pick unique names.

## New/changed system prompt

- Templates live in `app/agent/prompts/templates/*.md` (jinja2, `StrictUndefined` — every `{{ var }}` must be supplied).
- Add a file, then point `AGENT_SYSTEM_PROMPT_TEMPLATE` in `.env` at its basename. No Python changes.
- Keep the grounding contract of `domain_qa.md`: always search before answering, admit "I don't know" on NO_RESULTS, answer in the user's language.
- Test render via `PromptLoader` in `tests/agent/test_prompt_loader.py` style if the template takes new variables.

## Done when

`uv run pytest tests/agent -q` green, full suite green, and `grep -rn "fastapi\|sqlalchemy\|app\.core\|app\.modules" backend/app/agent/` shows no real imports (docstrings mentioning them are fine).
