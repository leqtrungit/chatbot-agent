from __future__ import annotations

import pytest

from app.agent.core.builder import AgentBuilder
from app.agent.core.types import LLMResponse, ModelParams
from app.agent.skills.base import Skill
from tests.agent.conftest import RecordingTool


def test_fluent_chaining_returns_builder(mock_llm):
    builder = AgentBuilder()
    assert builder.with_llm(mock_llm) is builder
    assert builder.with_model("m") is builder
    assert builder.with_system_prompt("hi") is builder
    assert builder.with_max_iterations(5) is builder


def test_build_without_llm_raises():
    builder = AgentBuilder().with_model("m")
    with pytest.raises(ValueError):
        builder.build()


def test_build_without_model_raises(mock_llm):
    builder = AgentBuilder().with_llm(mock_llm)
    with pytest.raises(ValueError):
        builder.build()


def test_build_uses_default_system_prompt(mock_llm):
    agent = AgentBuilder().with_llm(mock_llm).with_model("m").build()
    assert agent.system_prompt
    assert isinstance(agent.system_prompt, str)


async def test_params_passed_through_to_provider_call(mock_llm):
    mock_llm.queue(LLMResponse(content="ok"))
    agent = (
        AgentBuilder()
        .with_llm(mock_llm)
        .with_model("m")
        .with_params(temperature=0.2, max_tokens=100)
        .build()
    )
    await agent.run("hi")
    params = mock_llm.calls[0]["params"]
    assert isinstance(params, ModelParams)
    assert params.temperature == 0.2
    assert params.max_tokens == 100


async def test_params_accepts_model_params_instance(mock_llm):
    mock_llm.queue(LLMResponse(content="ok"))
    agent = (
        AgentBuilder()
        .with_llm(mock_llm)
        .with_model("m")
        .with_params(ModelParams(temperature=0.9))
        .build()
    )
    await agent.run("hi")
    assert mock_llm.calls[0]["params"].temperature == 0.9


def test_with_prompt_template(mock_llm):
    agent = (
        AgentBuilder()
        .with_llm(mock_llm)
        .with_model("m")
        .with_prompt_template("domain_qa", domain_name="Acme")
        .build()
    )
    assert "Acme" in agent.system_prompt


def test_skills_merge_tools_and_prompt_fragments(mock_llm):
    tool1 = RecordingTool(name="t1")
    tool2 = RecordingTool(name="t2")
    skill1 = Skill(name="s1", prompt_fragment="Fragment one.", tools=[tool1])
    skill2 = Skill(name="s2", prompt_fragment="Fragment two.", tools=[tool2])

    agent = (
        AgentBuilder()
        .with_llm(mock_llm)
        .with_model("m")
        .with_system_prompt("Base prompt.")
        .with_skills([skill1, skill2])
        .build()
    )

    assert "Base prompt." in agent.system_prompt
    assert "Fragment one." in agent.system_prompt
    assert "Fragment two." in agent.system_prompt
    tool_names = {t.name for t in agent.tools}
    assert tool_names == {"t1", "t2"}


def test_add_tool_and_add_skill(mock_llm):
    tool = RecordingTool(name="direct")
    skill = Skill(name="s", prompt_fragment="Frag.", tools=[])
    agent = (
        AgentBuilder()
        .with_llm(mock_llm)
        .with_model("m")
        .add_tool(tool)
        .add_skill(skill)
        .build()
    )
    assert any(t.name == "direct" for t in agent.tools)
    assert "Frag." in agent.system_prompt


def test_duplicate_tool_name_raises(mock_llm):
    tool1 = RecordingTool(name="dup")
    tool2 = RecordingTool(name="dup")
    builder = (
        AgentBuilder()
        .with_llm(mock_llm)
        .with_model("m")
        .with_tools([tool1])
        .add_tool(tool2)
    )
    with pytest.raises(ValueError):
        builder.build()


def test_duplicate_tool_name_across_skills_raises(mock_llm):
    tool1 = RecordingTool(name="dup")
    tool2 = RecordingTool(name="dup")
    skill1 = Skill(name="s1", prompt_fragment="a", tools=[tool1])
    skill2 = Skill(name="s2", prompt_fragment="b", tools=[tool2])
    builder = AgentBuilder().with_llm(mock_llm).with_model("m").with_skills([skill1, skill2])
    with pytest.raises(ValueError):
        builder.build()


def test_with_max_iterations(mock_llm):
    agent = (
        AgentBuilder().with_llm(mock_llm).with_model("m").with_max_iterations(3).build()
    )
    assert agent.max_iterations == 3
