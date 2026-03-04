import asyncio

import pytest

import rate_limiter


def test_token_bucket_consume_refill() -> None:
    now = [0.0]

    def time_fn():
        return now[0]

    bucket = rate_limiter.TokenBucket(capacity=2, refill_rate=1.0, time_fn=time_fn)
    assert bucket.consume() is True
    assert bucket.consume() is True
    assert bucket.consume() is False

    now[0] = 1.0
    assert bucket.consume() is True


def test_mailbox_limiter_refunds_token_on_semaphore_block() -> None:
    now = [0.0]

    def time_fn():
        return now[0]

    limiter = rate_limiter.MailboxLimiter(
        max_concurrency=1,
        capacity=2,
        refill_rate=1.0,
        time_fn=time_fn,
    )
    assert asyncio.run(limiter.try_acquire()) is True
    assert asyncio.run(limiter.try_acquire()) is False
    asyncio.run(limiter.release())
    assert asyncio.run(limiter.try_acquire()) is True


def test_mailbox_limiter_rate_limit_blocks_until_refill() -> None:
    now = [0.0]

    def time_fn():
        return now[0]

    limiter = rate_limiter.MailboxLimiter(
        max_concurrency=2,
        capacity=1,
        refill_rate=1.0,
        time_fn=time_fn,
    )
    assert asyncio.run(limiter.try_acquire()) is True
    asyncio.run(limiter.release())
    assert asyncio.run(limiter.try_acquire()) is False
    now[0] = 1.0
    assert asyncio.run(limiter.try_acquire()) is True


def test_try_acquire_mailbox_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rate_limiter.config, "GRAPH_MAILBOX_CONCURRENCY", 1)
    monkeypatch.setattr(rate_limiter.config, "GRAPH_RATE_LIMIT_PER_10_SECONDS", 1)
    limiter = asyncio.run(rate_limiter.try_acquire_mailbox("user@example.com"))
    assert limiter is not None
    asyncio.run(limiter.release())


def test_mailbox_limiter_registry_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]

    def time_fn():
        return now[0]

    monkeypatch.setattr(rate_limiter, "monotonic", time_fn)
    monkeypatch.setattr(rate_limiter.config, "GRAPH_MAILBOX_CONCURRENCY", 1)
    monkeypatch.setattr(rate_limiter.config, "GRAPH_RATE_LIMIT_PER_10_SECONDS", 1)
    monkeypatch.setattr(rate_limiter.config, "GRAPH_LIMITER_TTL_SECONDS", 5)

    asyncio.run(rate_limiter.get_mailbox_limiter("a@example.com"))
    now[0] = 10.0
    asyncio.run(rate_limiter.get_mailbox_limiter("b@example.com"))

    assert "a@example.com" not in rate_limiter._limiters


def test_low_rate_limit_allows_sparse_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]

    def time_fn():
        return now[0]

    monkeypatch.setattr(rate_limiter, "monotonic", time_fn)
    monkeypatch.setattr(rate_limiter.config, "GRAPH_MAILBOX_CONCURRENCY", 1)
    monkeypatch.setattr(rate_limiter.config, "GRAPH_RATE_LIMIT_PER_10_SECONDS", 0.5)
    monkeypatch.setattr(rate_limiter.config, "GRAPH_LIMITER_TTL_SECONDS", 60)

    limiter = asyncio.run(rate_limiter.get_mailbox_limiter("low@example.com"))
    assert asyncio.run(limiter.try_acquire()) is True
    asyncio.run(limiter.release())
    assert asyncio.run(limiter.try_acquire()) is False
    now[0] = 20.0
    assert asyncio.run(limiter.try_acquire()) is True
