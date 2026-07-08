"""Lookup table from platform slug -> :class:`ChannelAdapter`."""

from __future__ import annotations

from app.channels.base import ChannelAdapter
from app.channels.generic import GenericAdapter


class ChannelNotRegisteredError(KeyError):
    """Raised when looking up an unregistered platform slug."""


class ChannelRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, ChannelAdapter] = {}

    def register(self, adapter: ChannelAdapter) -> None:
        self._adapters[adapter.platform] = adapter

    def get(self, platform: str) -> ChannelAdapter:
        try:
            return self._adapters[platform]
        except KeyError as exc:
            raise ChannelNotRegisteredError(platform) from exc

    def list_platforms(self) -> list[str]:
        return sorted(self._adapters)


default_registry = ChannelRegistry()
default_registry.register(GenericAdapter())


def get_channel_registry() -> ChannelRegistry:
    return default_registry
