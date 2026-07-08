from __future__ import annotations

from typing import Any

import pytest

from app.channels.base import ChannelAdapter, IncomingMessage
from app.channels.registry import ChannelNotRegisteredError, ChannelRegistry


class _FakeAdapter(ChannelAdapter):
    def __init__(self, slug: str):
        self._slug = slug

    @property
    def platform(self) -> str:
        return self._slug

    async def parse_incoming(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> IncomingMessage:
        return IncomingMessage(domain_id="d", session_id="s", text="t")


def test_register_and_get() -> None:
    registry = ChannelRegistry()
    adapter = _FakeAdapter("fake")
    registry.register(adapter)
    assert registry.get("fake") is adapter


def test_get_unregistered_raises() -> None:
    registry = ChannelRegistry()
    with pytest.raises(ChannelNotRegisteredError):
        registry.get("unknown")


def test_list_platforms() -> None:
    registry = ChannelRegistry()
    registry.register(_FakeAdapter("b"))
    registry.register(_FakeAdapter("a"))
    assert registry.list_platforms() == ["a", "b"]


def test_default_registry_has_generic() -> None:
    from app.channels.registry import get_channel_registry

    registry = get_channel_registry()
    assert "generic" in registry.list_platforms()
