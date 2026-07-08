"""Platform adapter abstraction for inbound/outbound chat messages.

Pure library: no FastAPI/SQLAlchemy/arq imports here. Webhook routers and
worker tasks depend on this package, not the other way around.
"""

from __future__ import annotations

from app.channels.base import (
    ChannelAdapter,
    ChannelParseError,
    IncomingMessage,
    OutgoingMessage,
)
from app.channels.generic import GenericAdapter
from app.channels.registry import (
    ChannelNotRegisteredError,
    ChannelRegistry,
    default_registry,
    get_channel_registry,
)

__all__ = [
    "ChannelAdapter",
    "ChannelParseError",
    "IncomingMessage",
    "OutgoingMessage",
    "GenericAdapter",
    "ChannelRegistry",
    "ChannelNotRegisteredError",
    "default_registry",
    "get_channel_registry",
]
