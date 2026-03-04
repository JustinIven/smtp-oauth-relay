import asyncio
from dataclasses import dataclass
from time import monotonic

import config


# Basic token bucket for per-mailbox rate limiting.
class TokenBucket:
    def __init__(self, capacity: float, refill_rate: float, time_fn=monotonic):
        self._capacity = float(capacity)
        self._refill_rate = float(refill_rate)
        self._time_fn = time_fn
        self._tokens = float(capacity)
        self._last_refill = self._time_fn()

    # Add tokens based on elapsed time, capped at capacity.
    def _refill(self) -> None:
        now = self._time_fn()
        elapsed = max(0.0, now - self._last_refill)
        if elapsed <= 0:
            return
        self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    # Attempt to consume tokens for a request.
    def consume(self, amount: float = 1.0) -> bool:
        self._refill()
        if self._tokens >= amount:
            self._tokens -= amount
            return True
        return False

    # Return tokens if a request is rejected by concurrency checks.
    def refund(self, amount: float = 1.0) -> None:
        self._tokens = min(self._capacity, self._tokens + amount)


# Combines a token bucket with a concurrency cap per mailbox.
class MailboxLimiter:
    def __init__(
        self,
        max_concurrency: int,
        capacity: float,
        refill_rate: float,
        time_fn=monotonic,
    ):
        self._max_concurrency = max_concurrency
        self._bucket = TokenBucket(capacity, refill_rate, time_fn=time_fn)
        self._inflight = 0
        self._lock = asyncio.Lock()

    # Reserve capacity for a send attempt.
    async def try_acquire(self) -> bool:
        async with self._lock:
            if not self._bucket.consume():
                return False
            if self._inflight >= self._max_concurrency:
                self._bucket.refund()
                return False
            self._inflight += 1
            return True

    # Release a reserved slot after a send completes.
    async def release(self) -> None:
        async with self._lock:
            if self._inflight > 0:
                self._inflight -= 1


# Lightweight holder for the effective rate limit configuration.
@dataclass(frozen=True)
class RateLimitConfig:
    mailbox_concurrency: int
    per_ten_seconds: float
    limiter_ttl_seconds: float


# Mailbox limiter registry plus last-used timestamp for cleanup.
_limiters: dict[str, tuple[MailboxLimiter, float]] = {}
# Registry lock to avoid races during creation and cleanup.
_lock = asyncio.Lock()


# Read the current configuration values.
def _rate_limit_config() -> RateLimitConfig:
    per_ten_seconds = config.GRAPH_RATE_LIMIT_PER_10_SECONDS
    return RateLimitConfig(
        mailbox_concurrency=config.GRAPH_MAILBOX_CONCURRENCY,
        per_ten_seconds=per_ten_seconds,
        limiter_ttl_seconds=config.GRAPH_LIMITER_TTL_SECONDS,
    )


# Resolve or create the limiter for a mailbox, evicting stale entries.
async def get_mailbox_limiter(mailbox: str) -> MailboxLimiter:
    key = mailbox.lower()
    now = monotonic()
    if key in _limiters:
        limiter, _last_used = _limiters[key]
        _limiters[key] = (limiter, now)
        return limiter
    async with _lock:
        limits = _rate_limit_config()
        now = monotonic()
        # Cleanup is intentionally lazy to keep the registry lightweight.
        if limits.limiter_ttl_seconds > 0:
            expired = [
                mailbox_key
                for mailbox_key, (_, last_used) in _limiters.items()
                if (now - last_used) > limits.limiter_ttl_seconds
            ]
            for mailbox_key in expired:
                _limiters.pop(mailbox_key, None)
        if key in _limiters:
            limiter, _last_used = _limiters[key]
            _limiters[key] = (limiter, now)
            return limiter
        # Clamp to avoid negative values and ensure fractional rates still work.
        per_ten_seconds = max(0.0, limits.per_ten_seconds)
        bucket_capacity = max(1.0, per_ten_seconds) if per_ten_seconds > 0 else 0.0
        limiter = MailboxLimiter(
            max_concurrency=limits.mailbox_concurrency,
            capacity=bucket_capacity,
            refill_rate=per_ten_seconds / 10.0,
            time_fn=monotonic,
        )
        _limiters[key] = (limiter, now)
        return limiter


# Convenience helper that returns a limiter only when capacity is available.
async def try_acquire_mailbox(mailbox: str) -> MailboxLimiter | None:
    limiter = await get_mailbox_limiter(mailbox)
    if await limiter.try_acquire():
        return limiter
    return None
