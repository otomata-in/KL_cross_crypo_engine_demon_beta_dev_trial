"""
app/lib/rate_limiter.py — Token Bucket Rate Limiter
=====================================================
Prevents IP bans by throttling API request weight.
"""

import asyncio
import time
import structlog

log = structlog.get_logger(__name__)


class TokenBucket:
    """
    Token bucket rate limiter.
    capacity    = max tokens (e.g. 5800 weight/min)
    refill_rate = tokens per second (e.g. 5800/60 ≈ 96.7/s)
    """

    def __init__(self, name: str, capacity: int, refill_rate: float):
        self._name = name
        self._capacity = capacity
        self._tokens = float(capacity)
        self._refill_rate = refill_rate
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def consume(self, weight: int = 1) -> None:
        """Wait until enough tokens available, then consume weight."""
        async with self._lock:
            self._refill()
            if self._tokens < weight:
                wait_s = (weight - self._tokens) / self._refill_rate
                log.debug("rate_limit_wait",
                          exchange=self._name,
                          wait_ms=round(wait_s * 1000, 1))
                await asyncio.sleep(wait_s)
                self._refill()

            self._tokens -= weight
            usage_pct = round((1 - self._tokens / self._capacity) * 100, 1)
            if usage_pct > 80:
                log.warning("rate_limit_high_usage",
                            exchange=self._name,
                            usage_pct=usage_pct)

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now
