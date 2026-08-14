"""Fluent builder for assembling an :class:`Agent`.

This is the single place that wires together an LLM provider, a system
prompt (raw text or a rendered template), tools, and skills. Swapping any
of those pieces never requires touching :mod:`app.agent.core.agent`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.core.agent import Agent
from app.agent.core.types import ModelParams
from app.agent.prompts.loader import PromptLoader
from app.agent.providers.base import LLMProvider
from app.agent.skills.base import Skill
from app.agent.tools.base import Tool

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful, honest assistant. Use the tools available to you "
    "when they would help answer the user's request, and answer clearly "
    "and concisely otherwise."
)


class AgentBuilder:
    def __init__(self) -> None:
        self._llm: LLMProvider | None = None
        self._model: str | None = None
        self._system_prompt: str | None = None
        self._tools: list[Tool] = []
        self._skills: list[Skill] = []
        self._params: ModelParams = ModelParams()
        self._max_iterations: int = 10

    def with_llm(self, provider: LLMProvider) -> "AgentBuilder":
        self._llm = provider
        return self

    def with_model(self, name: str) -> "AgentBuilder":
        self._model = name
        return self

    def with_params(self, params: ModelParams | None = None, **kwargs: Any) -> "AgentBuilder":
        if params is not None and kwargs:
            raise ValueError("Pass either a ModelParams instance or kwargs, not both.")
        self._params = params if params is not None else ModelParams(**kwargs)
        return self

    def with_system_prompt(self, text: str) -> "AgentBuilder":
        self._system_prompt = text
        return self

    def with_prompt_template(
        self, name: str, loader: PromptLoader | None = None, **variables: Any
    ) -> "AgentBuilder":
        loader = loader or PromptLoader()
        self._system_prompt = loader.render(name, **variables)
        return self

    def with_tools(self, tools: list[Tool]) -> "AgentBuilder":
        self._tools.extend(tools)
        return self

    def add_tool(self, tool: Tool) -> "AgentBuilder":
        self._tools.append(tool)
        return self

    def with_skills(self, skills: list[Skill]) -> "AgentBuilder":
        self._skills.extend(skills)
        return self

    def add_skill(self, skill: Skill) -> "AgentBuilder":
        self._skills.append(skill)
        return self

    def with_max_iterations(self, n: int) -> "AgentBuilder":
        self._max_iterations = n
        return self

    def build(self) -> Agent:
        if self._llm is None:
            raise ValueError("AgentBuilder requires with_llm(...) before build().")
        if self._model is None:
            raise ValueError("AgentBuilder requires with_model(...) before build().")

        system_prompt = self._system_prompt or DEFAULT_SYSTEM_PROMPT

        all_tools: list[Tool] = []
        seen_names: dict[str, str] = {}
        fragments: list[str] = []

        for tool in self._tools:
            if tool.name in seen_names:
                raise ValueError(
                    f"Duplicate tool name {tool.name!r} "
                    f"(already provided by {seen_names[tool.name]})"
                )
            seen_names[tool.name] = "base tools"
            all_tools.append(tool)
            if tool.prompt_fragment and tool.prompt_fragment not in fragments:
                fragments.append(tool.prompt_fragment)

        for skill in self._skills:
            fragments.append(skill.prompt_fragment)
            for tool in skill.tools:
                if tool.name in seen_names:
                    raise ValueError(
                        f"Duplicate tool name {tool.name!r} "
                        f"(already provided by {seen_names[tool.name]}, "
                        f"also provided by skill {skill.name!r})"
                    )
                seen_names[tool.name] = f"skill {skill.name!r}"
                all_tools.append(tool)

        if fragments:
            system_prompt = "\n\n".join([system_prompt, *fragments])

        return Agent(
            llm=self._llm,
            model=self._model,
            system_prompt=system_prompt,
            tools=all_tools,
            params=self._params,
            max_iterations=self._max_iterations,
        )
