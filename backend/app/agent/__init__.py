"""Provider-agnostic agent framework.

Pure library: nothing here imports FastAPI, SQLAlchemy, ``app.core``, or
``app.modules``. External capabilities (LLM, embeddings, vector search)
are injected via :class:`AgentBuilder` / tool constructors.
"""

from __future__ import annotations

from app.agent import providers
from app.agent.core import types
from app.agent.core.agent import Agent
from app.agent.core.builder import AgentBuilder
from app.agent.core.types import (
    AgentResponse,
    Citation,
    LLMResponse,
    Message,
    ModelParams,
    Role,
    ToolCall,
    ToolResult,
)
from app.agent.prompts.loader import PromptLoader
from app.agent.skills.base import Skill
from app.agent.tools.base import FunctionTool, Tool, ToolOutput
from app.agent.tools.knowledge_search import KnowledgeHit, KnowledgeSearcher, KnowledgeSearchTool

__all__ = [
    "Agent",
    "AgentBuilder",
    "AgentResponse",
    "Citation",
    "LLMResponse",
    "Message",
    "ModelParams",
    "Role",
    "ToolCall",
    "ToolResult",
    "Tool",
    "ToolOutput",
    "FunctionTool",
    "KnowledgeSearchTool",
    "KnowledgeSearcher",
    "KnowledgeHit",
    "Skill",
    "PromptLoader",
    "providers",
    "types",
]
