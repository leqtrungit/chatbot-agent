from __future__ import annotations

from app.agent.skills.base import Skill
from tests.agent.conftest import RecordingTool


def test_skill_holds_name_prompt_and_tools():
    tool = RecordingTool(name="t1")
    skill = Skill(name="hr", prompt_fragment="You know about HR policy.", tools=[tool])
    assert skill.name == "hr"
    assert skill.prompt_fragment == "You know about HR policy."
    assert skill.tools == [tool]
