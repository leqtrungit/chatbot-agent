from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.prompts.loader import PromptLoader


def test_renders_domain_qa_with_variables():
    loader = PromptLoader()
    rendered = loader.render(
        "domain_qa", domain_name="Acme HR", domain_description="Company policies"
    )
    assert "Acme HR" in rendered
    assert "Company policies" in rendered
    assert "knowledge_search" in rendered
    assert "I don't have information about that in my knowledge base" in rendered


def test_renders_domain_qa_without_optional_description():
    loader = PromptLoader()
    rendered = loader.render("domain_qa", domain_name="Acme HR")
    assert "Acme HR" in rendered


def test_missing_variable_raises():
    loader = PromptLoader()
    with pytest.raises(Exception):
        loader.render("domain_qa")


def test_unknown_template_raises():
    loader = PromptLoader()
    with pytest.raises(Exception):
        loader.render("does_not_exist", domain_name="X")


def test_list_templates_includes_domain_qa():
    loader = PromptLoader()
    names = loader.list_templates()
    assert "domain_qa" in names


def test_custom_templates_dir(tmp_path: Path):
    (tmp_path / "custom.md").write_text("Hello {{ name }}!")
    loader = PromptLoader(templates_dir=tmp_path)
    assert loader.render("custom", name="World") == "Hello World!"
    assert loader.list_templates() == ["custom"]
