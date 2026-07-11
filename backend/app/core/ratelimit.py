"""Fixed-window rate limiting backed by Redis ``INCR``/``EXPIRE``.

Takes any redis-like client (the arq pool is a real ``redis.asyncio`` client,
so it can be reused directly) — kept dependency-free so tests can pass a
tiny in-memory fake instead of spinning up real Redis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

DEFAULT_WINDOW_SECONDS = 60


class RedisLike(Protocol):
    async def incr(self, key: str) -> int: ...
    async def expire(self, key: str, seconds: int) -> object: ...
    async def ttl(self, key: str) -> int: ...


@dataclass
class RateLimitResult:
    allowed: bool
    retry_after: int


async def check_rate_limit(
    redis: RedisLike,
    key: str,
    limit: int,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> RateLimitResult:
    """Increment the counter for ``key`` and report whether ``limit`` (per
    ``window_seconds``) has been exceeded. The window starts on the first
    increment (fixed window, not sliding)."""
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)

    if count > limit:
        ttl = await redis.ttl(key)
        retry_after = ttl if ttl and ttl > 0 else window_seconds
        return RateLimitResult(allowed=False, retry_after=retry_after)

    return RateLimitResult(allowed=True, retry_after=0)
