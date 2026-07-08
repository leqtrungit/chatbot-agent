"""Loads system prompt templates from disk.

Prompts are plain jinja2 markdown files, one per template name. Swapping a
system prompt is a matter of adding/editing a ``.md`` file — never touching
agent code.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"


class PromptLoader:
    def __init__(self, templates_dir: Path | None = None):
        self.templates_dir = templates_dir or DEFAULT_TEMPLATES_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )

    def render(self, name: str, /, **variables: object) -> str:
        try:
            template = self._env.get_template(f"{name}.md")
        except TemplateNotFound as exc:
            raise ValueError(f"Unknown prompt template: {name!r}") from exc
        return template.render(**variables)

    def list_templates(self) -> list[str]:
        return sorted(p.stem for p in self.templates_dir.glob("*.md"))
