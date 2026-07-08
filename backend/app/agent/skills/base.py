"""Skills bundle a prompt fragment with the tools that back it.

Multiple skills can be composed onto a single agent: their tools are
merged (tool names must be unique across the whole agent) and their
prompt fragments are appended to the base system prompt.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.agent.tools.base import Tool


class Skill(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    prompt_fragment: str
    tools: list[Tool] = []
