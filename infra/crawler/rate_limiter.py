"""AiolimiterRateLimiter — leaky-bucket rate limiter backed by aiolimiter."""

from __future__ import annotations

from aiolimiter import AsyncLimiter

from domain.ports import RateLimiter


class AiolimiterRateLimiter(RateLimiter):
    """Implements RateLimiter using aiolimiter's AsyncLimiter.

    Args:
        rate: Maximum number of requests per second.
    """

    def __init__(self, rate: float = 2.0) -> None:
        # AsyncLimiter(max_rate, time_period) — one token per (time_period/max_rate)s
        self._limiter = AsyncLimiter(max_rate=rate, time_period=1.0)

    async def acquire(self) -> None:
        async with self._limiter:
            pass
